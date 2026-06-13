"""
SkMowerClient – main public API for pyskmover.

Architecture
============
* A single background ``_ConnectionThread`` owns all HTTP I/O.
* On startup it authenticates, fetches user/app info and then polls the
  device state every ``poll_interval`` seconds (default 30 s).
* If the connection is lost (network error, 401, …) the thread backs off
  and re-authenticates automatically.
* All shared state (token, status, settings) is protected by a
  ``threading.RLock`` so callers on any thread see consistent snapshots.

Unique messages observed in sk-mover-komunikacja.log
=====================================================
1.  POST /api/auth/oauth/token              – OAuth2 password grant
2.  GET  /api/admin/user/app/info           – resolve appId after login
3.  GET  /api/app_mower/message-send-logs/count/{appId}
4.  GET  /api/app_mower/device-user/list    – enumerate paired devices
5.  PUT  /api/admin/user/edit               – register FCM token / OS
6.  POST /api/app_mower/device/setWorkStatus – send command (mode 0/1/4)
7.  GET  /api/app_mower/device-setting/{deviceSn}
        – periodic poll; response contains full settings + live status
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Callable, List, Optional

import urllib.request
import urllib.parse
import urllib.error
import json
import ssl

from .exceptions import (
    SkMowerApiError,
    SkMowerAuthError,
    SkMowerConnectionError,
    SkMowerError,
)
from .models import (
    DeviceMap,
    DeviceSetting,
    DeviceStatus,
    SetWorkStatusRequest,
    TokenResponse,
    UpdateUserRequest,
    UserAppInfo,
    WorkMode,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://server.sk-robot.com"
# HTTP Basic credentials for the OAuth client (observed: "app:app")
_OAUTH_BASIC = base64.b64encode(b"app:app").decode()
_DEFAULT_POLL_INTERVAL = 30  # seconds
_DEFAULT_RECONNECT_DELAY = 10  # seconds – initial back-off
_MAX_RECONNECT_DELAY = 300  # seconds – upper cap for back-off
_HTTP_TIMEOUT = 20  # seconds per request


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def _http_request(
    method: str,
    path: str,
    *,
    bearer_token: Optional[str] = None,
    basic_token: Optional[str] = None,
    form_data: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: int = _HTTP_TIMEOUT,
    language: str = "en",
) -> dict:
    """
    Minimal HTTP client using stdlib only (no third-party deps required).

    Returns the parsed JSON body on HTTP 2xx.
    Raises:
        SkMowerConnectionError  – on network-level failure
        SkMowerAuthError        – on HTTP 401
        SkMowerApiError         – when response JSON contains a non-zero code
        SkMowerError            – on other HTTP errors
    """
    url = BASE_URL + path
    headers = {
        "Accept-Language": language,
        "User-Agent": "okhttp/4.8.1",
        "Accept-Encoding": "identity",  # avoid gzip in stdlib
        "Connection": "Keep-Alive",
    }

    if bearer_token:
        headers["Authorization"] = f"bearer {bearer_token}"
    elif basic_token:
        headers["Authorization"] = f"Basic {basic_token}"

    body: Optional[bytes] = None
    if json_data is not None:
        body = json.dumps(json_data).encode()
        headers["Content-Type"] = "application/json; charset=UTF-8"
        headers["Content-Length"] = str(len(body))
    elif form_data is not None:
        body = urllib.parse.urlencode(form_data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = str(len(body))

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            charset = "utf-8"
            ct = resp.headers.get_content_charset()
            if ct:
                charset = ct
            text = raw.decode(charset)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SkMowerAuthError(f"HTTP 401 on {method} {path}") from exc
        raise SkMowerError(f"HTTP {exc.code} on {method} {path}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SkMowerConnectionError(f"Network error on {method} {path}: {exc.reason}") from exc
    except OSError as exc:
        raise SkMowerConnectionError(f"OS error on {method} {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkMowerError(f"Invalid JSON from {method} {path}: {exc}") from exc

    # SK-robot API wraps responses in {"code":0,"msg":null,"data":{...},"ok":true}
    # Token endpoint returns flat OAuth response (no "code" wrapper)
    if isinstance(data, dict) and "code" in data:
        code = data.get("code", 0)
        if code != 0:
            msg = data.get("msg") or ""
            raise SkMowerApiError(int(code), str(msg))
        return data.get("data") or data

    return data


# ---------------------------------------------------------------------------
# Connection / polling thread
# ---------------------------------------------------------------------------


class _ConnectionThread(threading.Thread):
    """
    Background thread that:
      1. Authenticates (POST /api/auth/oauth/token)
      2. Resolves the appId (GET /api/admin/user/app/info)
      3. Polls device state every *poll_interval* seconds
      4. Re-authenticates automatically on connection loss or 401
    """

    def __init__(
        self,
        username: str,
        password: str,
        device_sn: str,
        poll_interval: int,
        lock: threading.RLock,
        stop_event: threading.Event,
        state: "_SharedState",
        client: "SkMowerClient",
    ) -> None:
        super().__init__(name="SkMowerConnectionThread", daemon=True)
        self._username = username
        self._password = password
        self._device_sn = device_sn
        self._poll_interval = poll_interval
        self._lock = lock
        self._stop_event = stop_event
        self._state = state
        self._client = client

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        reconnect_delay = _DEFAULT_RECONNECT_DELAY
        while not self._stop_event.is_set():
            try:
                self._authenticate()
                self._fetch_user_info()
                reconnect_delay = _DEFAULT_RECONNECT_DELAY  # reset on success
                self._poll_loop()
            except SkMowerAuthError as exc:
                logger.error("Authentication failed: %s – retrying in %ds", exc, reconnect_delay)
                self._clear_auth()
                self._wait_or_stop(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, _MAX_RECONNECT_DELAY)
            except (SkMowerConnectionError, SkMowerError) as exc:
                logger.warning("Connection error: %s – retrying in %ds", exc, reconnect_delay)
                self._clear_auth()
                self._wait_or_stop(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, _MAX_RECONNECT_DELAY)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> None:
        logger.debug("Authenticating as %s …", self._username)
        data = _http_request(
            "POST",
            "/api/auth/oauth/token",
            basic_token=_OAUTH_BASIC,
            form_data={
                "username": self._username,
                "password": self._password,
                "grant_type": "password",
                "scope": "server",
            },
            language=self._client.language,
        )
        token = TokenResponse.from_dict(data)
        with self._lock:
            self._state.token = token
        logger.info("Authenticated – token acquired")

    def _fetch_user_info(self) -> None:
        token_resp = None
        with self._lock:
            token_resp = self._state.token

        token = self._client._get_token()
        data = _http_request(
            "GET",
            "/api/admin/user/app/info",
            bearer_token=token,
            language=self._client.language,
        )
        
        # If appId is missing in info but present in token response as user_id,
        # merge it into the info data.
        if "appId" not in data or data["appId"] is None:
            if token_resp and hasattr(token_resp, "extra") and "user_id" in token_resp.extra:
                data["appId"] = token_resp.extra["user_id"]
            # Some versions might have user_id at the top level of token response
            elif token_resp and hasattr(token_resp, "user_id"):
                 data["appId"] = token_resp.user_id

        info = UserAppInfo.from_dict(data)
        with self._lock:
            self._state.user_info = info
        logger.info("App info fetched – appId=%s", info.app_id)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._client._poll_device()
            except SkMowerAuthError:
                logger.warning("Token expired during poll – re-authenticating")
                raise  # bubble up to run() for full re-auth
            except (SkMowerConnectionError, SkMowerApiError, SkMowerError) as exc:
                logger.warning("Poll failed: %s", exc)
                # Keep polling; transient errors are tolerated
            self._wait_or_stop(self._poll_interval)

    def _clear_auth(self) -> None:
        with self._lock:
            self._state.token = None
            self._state.user_info = None

    def _wait_or_stop(self, seconds: float) -> None:
        """Sleep for *seconds* but wake immediately if stop is requested."""
        self._stop_event.wait(timeout=seconds)


# ---------------------------------------------------------------------------
# Shared mutable state (all access through RLock)
# ---------------------------------------------------------------------------


class _SharedState:
    __slots__ = ("token", "user_info", "device_status", "device_setting", "device_map")

    def __init__(self) -> None:
        self.token: Optional[TokenResponse] = None
        self.user_info: Optional[UserAppInfo] = None
        self.device_status: Optional[DeviceStatus] = None
        self.device_setting: Optional[DeviceSetting] = None
        self.device_map: Optional[DeviceMap] = None


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------


class SkMowerClient:
    """
    Thread-safe client for the SK-Robot lawn mower cloud API.
    """

    language: str = "en"
    _poll_counter: int = 0

    def __init__(
        self,
        username: str,
        password: str,
        device_sn: str,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
        on_status: Optional[Callable[[DeviceStatus], None]] = None,
        on_setting: Optional[Callable[[DeviceSetting], None]] = None,
        on_map: Optional[Callable[[DeviceMap], None]] = None,
    ) -> None:
        self._username = username
        self._password = password
        self._device_sn = device_sn
        self._poll_interval = poll_interval
        self._on_status = on_status
        self._on_setting = on_setting
        self._on_map = on_map

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._state = _SharedState()
        self._thread: Optional[_ConnectionThread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the connection/polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = _ConnectionThread(
            username=self._username,
            password=self._password,
            device_sn=self._device_sn,
            poll_interval=self._poll_interval,
            lock=self._lock,
            stop_event=self._stop_event,
            state=self._state,
            client=self,
        )
        self._thread.start()
        logger.info("SkMowerClient started (device_sn=%s, poll_interval=%ds)",
                    self._device_sn, self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the background thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("SkMowerClient stopped")

    def is_connected(self) -> bool:
        """Return True if the connection thread is alive and authenticated."""
        with self._lock:
            return (
                self._thread is not None
                and self._thread.is_alive()
                and self._state.token is not None
            )

    # ------------------------------------------------------------------
    # Polling & Internal state update
    # ------------------------------------------------------------------

    def _poll_device(self) -> None:
        """Perform a single poll cycle of all relevant endpoints."""
        token = self._get_token()
        self._poll_counter += 1

        # 2. Fetch real-time status from device list (crucial for workStatusCode)
        try:
            logger.debug("Polling device list for status of %s", self._device_sn)
            list_data = _http_request(
                "GET",
                "/api/app_mower/device-user/list",
                bearer_token=token,
                language=self.language,
            )
            if isinstance(list_data, list):
                # Find the record for our specific device_sn
                for device_info in list_data:
                    if device_info.get("deviceSn") == self._device_sn:
                        self._update_status(device_info)
                        break
        except Exception as exc:
            logger.warning("Failed to poll device status from list: %s", exc)

        # 3. Fetch newest work map and device settings for area/border statistics (every 10th poll)
        if self._poll_counter % 10 == 1:
            
            # 1. Fetch settings (periodic poll)
            try:
                logger.debug("Polling device settings for %s", self._device_sn)
                setting_data = _http_request(
                    "GET",
                    f"/api/app_mower/device-setting/{self._device_sn}",
                    bearer_token=token,
                    language=self.language,
                )
                # Use specific update method for settings to avoid status override
                self._update_settings(setting_data)
            except Exception as exc:
                logger.warning("Failed to poll device settings: %s", exc)
                
            try:
                logger.debug("Polling work map for statistics of %s", self._device_sn)
                map_data = _http_request(
                    "GET",
                    f"/api/map/work-map/newest/1/{self._device_sn}",
                    bearer_token=token,
                    language=self.language,
                )
                if map_data:
                    self._update_map(map_data)
            except Exception as exc:
                logger.warning("Failed to poll newest work map: %s", exc)

    def _update_settings(self, data: dict) -> None:
        """Parse configuration data and merge into shared state."""
        if "id" not in data:
            return
            
        setting = DeviceSetting.from_dict(data)
        with self._lock:
            self._state.device_setting = setting

        # Fire configuration callback
        if self._on_setting:
            try:
                self._on_setting(setting)
            except Exception:  # noqa: BLE001
                logger.exception("Exception in on_setting callback")

    def _update_status(self, data: dict) -> None:
        """Parse real-time status data and merge into shared state."""
        # We check for deviceSn to ensure it's a valid status payload
        if "deviceSn" not in data:
            return

        status = DeviceStatus.from_dict(data)
        with self._lock:
            self._state.device_status = status

        # Fire status callback (this triggers HA state update)
        if self._on_status:
            try:
                self._on_status(status)
            except Exception:  # noqa: BLE001
                logger.exception("Exception in on_status callback")

    def _update_map(self, data: dict) -> None:
        """Parse map data and merge into shared state."""
        # We check for deviceSn to ensure it's a valid map payload
        if "deviceSn" not in data:
            return

        device_map = DeviceMap.from_dict(data)
        with self._lock:
            self._state.device_map = device_map

        # Fire map callback
        if self._on_map:
            try:
                self._on_map(device_map)
            except Exception:  # noqa: BLE001
                logger.exception("Exception in on_map callback")

    def _get_token(self) -> str:
        with self._lock:
            if self._state.token is None:
                raise SkMowerAuthError("No token available")
            return self._state.token.access_token

    # ------------------------------------------------------------------
    # Status API  (read – updated every poll_interval seconds)
    # ------------------------------------------------------------------

    def get_device_status(self) -> Optional[DeviceStatus]:
        with self._lock:
            return self._state.device_status

    def get_device_setting(self) -> Optional[DeviceSetting]:
        with self._lock:
            return self._state.device_setting

    def get_device_map(self) -> Optional[DeviceMap]:
        with self._lock:
            return self._state.device_map

    def get_electricity(self) -> Optional[int]:
        with self._lock:
            s = self._state.device_status
            return s.electricity if s else None

    def get_work_status_code(self) -> Optional[str]:
        with self._lock:
            s = self._state.device_status
            return s.work_status_code if s else None

    def get_online_flag(self) -> Optional[bool]:
        with self._lock:
            s = self._state.device_status
            return s.online_flag if s else None

    def get_app_id(self) -> Optional[str]:
        with self._lock:
            info = self._state.user_info
            return info.app_id if info else None

    # ------------------------------------------------------------------
    # Command API  (write – executed immediately via HTTP)
    # ------------------------------------------------------------------

    def _require_token(self) -> str:
        with self._lock:
            if self._state.token is None:
                raise SkMowerAuthError("Not authenticated – call start() first")
            return self._state.token.access_token

    def _require_app_id(self) -> str:
        with self._lock:
            info = self._state.user_info
            if info is None or info.app_id is None:
                raise SkMowerError("appId not available yet – wait for connection")
            return info.app_id

    def set_work_mode(self, mode: WorkMode) -> None:
        token = self._require_token()
        app_id = self._require_app_id()
        req = SetWorkStatusRequest(
            app_id=app_id,
            device_sn=self._device_sn,
            mode=mode,
        )
        _http_request(
            "POST",
            "/api/app_mower/device/setWorkStatus",
            bearer_token=token,
            json_data=req.to_dict(),
            language=self.language,
        )
        logger.info("set_work_mode → %s (%d)", mode.name, int(mode))

    def start_mowing(self) -> None:
        self.set_work_mode(WorkMode.MOWING)

    def stop_mowing(self) -> None:
        self.set_work_mode(WorkMode.STOP)

    def return_to_dock(self) -> None:
        self.set_work_mode(WorkMode.DOCK)

    def start_border(self) -> None:
        self.set_work_mode(WorkMode.BORDER)

    def force_poll(self) -> None:
        """Trigger an immediate status and settings refresh."""
        self._poll_device()

    def update_user(self, fb_token: str, os_code: str = "android") -> None:
        token = self._require_token()
        req = UpdateUserRequest(fb_token=fb_token, operating_system_code=os_code)
        _http_request(
            "PUT",
            "/api/admin/user/edit",
            bearer_token=token,
            json_data=req.to_dict(),
            language=self.language,
        )
        logger.info("update_user → os=%s", os_code)

    def get_device_user_list(self) -> list:
        token = self._require_token()
        result = _http_request(
            "GET",
            "/api/app_mower/device-user/list",
            bearer_token=token,
            language=self.language,
        )
        if isinstance(result, list):
            return result
        # Some server versions wrap the list in a data envelope
        if isinstance(result, dict):
            return result.get("list") or result.get("records") or []
        return []

    def get_message_send_log_count(self) -> Optional[int]:
        token = self._require_token()
        app_id = self._require_app_id()
        result = _http_request(
            "GET",
            f"/api/app_mower/message-send-logs/count/{app_id}",
            bearer_token=token,
            language=self.language,
        )
        if isinstance(result, int):
            return result
        if isinstance(result, dict):
            # Try common key names
            for key in ("count", "total", "value"):
                if key in result:
                    return int(result[key])
        return None
