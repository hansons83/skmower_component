"""
Unit tests for pyskmover.client – all HTTP calls are mocked.

Tests cover:
  - _http_request JSON parsing and error handling
  - SkMowerClient state API (thread-safe reads)
  - SkMowerClient command API (set_work_mode, start_mowing, stop_mowing, start_border)
  - SkMowerClient lifecycle (start / stop / context manager)
  - Auto-reconnect behaviour via _ConnectionThread
  - force_poll updates shared state and fires callbacks
"""

import json
import threading
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch, call

from pyskmover.client import (
    BASE_URL,
    SkMowerClient,
    _SharedState,
    _http_request,
)
from pyskmover.exceptions import (
    SkMowerApiError,
    SkMowerAuthError,
    SkMowerConnectionError,
    SkMowerError,
)
from pyskmover.models import (
    DeviceStatus,
    DeviceSetting,
    TokenResponse,
    UserAppInfo,
    WorkMode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEVICE_SN = "2310168001000041843"
APP_ID = "12385068"
TOKEN = "3f21b39e-e845-4c44-aab7-c12191e1a698"

TOKEN_PAYLOAD = json.dumps({
    "access_token": TOKEN,
    "token_type": "bearer",
    "expires_in": 86399,
    "scope": "server",
}).encode()

USER_INFO_PAYLOAD = json.dumps({
    "code": 0,
    "msg": None,
    "data": {
        "appId": APP_ID,
        "username": "kubs83",
        "email": "kubs83@gmail.com",
    },
}).encode()

STATUS_PAYLOAD = json.dumps({
    "code": 0,
    "msg": None,
    "data": {
        "deviceId": "1719580267837460482",
        "deviceSn": DEVICE_SN,
        "deviceName": "Kosiek",
        "workStatusCode": "0",
        "workStatusName": "idle",
        "scheduleAutoFlag": False,
        "rainDelayLeft": 0,
        "rainDelayDuration": "0",
        "rainFlag": True,
        "faultStatusCode": "normal",
        "stationFlag": False,
        "faultStatusName": "normal",
        "electricity": 68,
        "bluetoothFlag": None,
        "wifiFlag": True,
        "rainStatusCode": "0",
        "collectedAt": "2024-06-21 19:42:41",
        "lat": 51.79329,
        "lng": 19.257982,
        "onlineFlag": True,
        "otaFlag": None,
        "area": 72118,
        "onMin": 72654,
        "totalMin": 72654,
        "workArea": None,
        "chargePos": None,
        "robotPos": None,
        "ipAddr": None,
        "livelinessAt": None,
        "appId": None,
        "deviceScheduleList": [],
    },
}).encode()

SETTING_PAYLOAD = json.dumps({
    "code": 0,
    "msg": None,
    "data": {
        "id": "17195802677913231 38",
        "deviceId": "1719580267837460482",
        "deviceSn": DEVICE_SN,
        "deviceName": "Kosiek",
        "rainDelayDuration": "0",
        "rainFlag": True,
        "language": 0,
        "otaFlag": None,
        "onlineFlag": True,
        "otaAutoFlag": False,
        "shareableFlag": True,
        "zoneOpenFlag": True,
        "zoneAutomaticFlag": False,
        "zoneFirstPercentage": 0,
        "zoneSecondPercentage": 2,
        "zoneThirdPercentage": 0,
        "zoneFourthPercentage": 3,
        "zoneExFlag": 0,
        "meterFirst": 1000,
        "meterSecond": 4499,
        "meterThird": 1000,
        "meterFour": 6748,
        "proFirst": 25,
        "proSecond": 25,
        "proThird": 25,
        "proFour": 25,
        "borderLength": 224954,
        "scheduleAutoFlag": False,
        "ledFlag": True,
        "ledColorCode": None,
        "ledModeCode": "true",
        "ledModeName": None,
        "ledStart": None,
        "ledEnd": None,
        "ledNightFlag": False,
        "gpsFlag": False,
        "gpsLong": None,
        "gpsLat": None,
        "timeAutoFlag": True,
        "timeZoneCode": "GMT+1",
        "timeZoneFlag": True,
        "timeZoneId": "Europe/Warsaw",
        "daylightTimeFlag": True,
        "nowTime": "2024-6-21 13:42:59",
        "ultraFlag": True,
        "ultraLv": 1,
        "pause": False,
        "deviceScheduleList": [],
        "createdAt": "2023-11-01 05:00:58",
        "updatedAt": "2024-06-15 21:39:59",
    },
}).encode()

OK_COMMAND_PAYLOAD = json.dumps({"code": 0, "msg": None, "data": None}).encode()


def _fake_response(body: bytes, status: int = 200, charset: str = "utf-8"):
    """Return a mock response object usable as a context manager."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers.get_content_charset.return_value = charset
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Tests for _http_request
# ---------------------------------------------------------------------------


class TestHttpRequest(unittest.TestCase):

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_get_returns_data(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(USER_INFO_PAYLOAD)
        result = _http_request("GET", "/api/admin/user/app/info",
                               bearer_token=TOKEN)
        self.assertEqual(result["appId"], APP_ID)

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_post_form_data(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(TOKEN_PAYLOAD)
        result = _http_request(
            "POST",
            "/api/auth/oauth/token",
            basic_token="YXBwOmFwcA==",
            form_data={"username": "u", "password": "p",
                       "grant_type": "password", "scope": "server"},
        )
        self.assertIn("access_token", result)

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_api_error_non_zero_code(self, mock_urlopen):
        payload = json.dumps({"code": 401, "msg": "Unauthorized", "data": None}).encode()
        mock_urlopen.return_value = _fake_response(payload)
        with self.assertRaises(SkMowerApiError) as ctx:
            _http_request("GET", "/api/some/path", bearer_token=TOKEN)
        self.assertEqual(ctx.exception.code, 401)

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_http_401_raises_auth_error(self, mock_urlopen):
        import urllib.error
        exc = urllib.error.HTTPError(
            url="http://x", code=401, msg="Unauthorized", hdrs=None, fp=None)
        mock_urlopen.side_effect = exc
        with self.assertRaises(SkMowerAuthError):
            _http_request("GET", "/api/path", bearer_token=TOKEN)

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_network_error_raises_connection_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with self.assertRaises(SkMowerConnectionError):
            _http_request("GET", "/api/path", bearer_token=TOKEN)

    @patch("pyskmover.client.urllib.request.urlopen")
    def test_invalid_json_raises_skmower_error(self, mock_urlopen):
        mock_urlopen.return_value = _fake_response(b"not-json")
        with self.assertRaises(SkMowerError):
            _http_request("GET", "/api/path", bearer_token=TOKEN)


# ---------------------------------------------------------------------------
# Helper: build a pre-authenticated client without a real thread
# ---------------------------------------------------------------------------


def _make_client_with_state(status_data=None, setting_data=None):
    """
    Create a SkMowerClient whose _state is pre-populated so command/status
    API methods can be called without starting the background thread.
    """
    client = SkMowerClient(
        username="user@example.com",
        password="pass",
        device_sn=DEVICE_SN,
    )
    client._state.token = TokenResponse(access_token=TOKEN)
    client._state.user_info = UserAppInfo(app_id=APP_ID, username="user")
    if status_data is not None:
        client._state.device_status = DeviceStatus.from_dict(status_data)
    if setting_data is not None:
        client._state.device_setting = DeviceSetting.from_dict(setting_data)
    return client


# ---------------------------------------------------------------------------
# Tests for status API
# ---------------------------------------------------------------------------


class TestStatusApi(unittest.TestCase):

    def setUp(self):
        status_raw = json.loads(STATUS_PAYLOAD)["data"]
        self.client = _make_client_with_state(status_data=status_raw)

    def test_get_electricity(self):
        self.assertEqual(self.client.get_electricity(), 68)

    def test_get_work_status_code(self):
        self.assertEqual(self.client.get_work_status_code(), "0")

    def test_get_work_status_name(self):
        self.assertEqual(self.client.get_work_status_name(), "idle")

    def test_get_fault_status(self):
        self.assertEqual(self.client.get_fault_status(), "normal")

    def test_get_rain_flag(self):
        self.assertTrue(self.client.get_rain_flag())

    def test_get_online_flag(self):
        self.assertTrue(self.client.get_online_flag())

    def test_get_location(self):
        loc = self.client.get_location()
        self.assertIsNotNone(loc)
        self.assertAlmostEqual(loc[0], 51.79329, places=4)
        self.assertAlmostEqual(loc[1], 19.257982, places=4)

    def test_get_area(self):
        self.assertEqual(self.client.get_area(), 72118)

    def test_get_total_minutes(self):
        self.assertEqual(self.client.get_total_minutes(), 72654)

    def test_get_app_id(self):
        self.assertEqual(self.client.get_app_id(), APP_ID)

    def test_get_device_status_returns_object(self):
        s = self.client.get_device_status()
        self.assertIsInstance(s, DeviceStatus)

    def test_returns_none_before_first_poll(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        self.assertIsNone(client.get_device_status())
        self.assertIsNone(client.get_electricity())
        self.assertIsNone(client.get_location())


# ---------------------------------------------------------------------------
# Tests for command API
# ---------------------------------------------------------------------------


class TestCommandApi(unittest.TestCase):

    def setUp(self):
        self.client = _make_client_with_state()

    @patch("pyskmover.client._http_request")
    def test_set_work_mode_stop(self, mock_req):
        mock_req.return_value = {}
        self.client.set_work_mode(WorkMode.STOP)
        mock_req.assert_called_once()
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], "POST")
        self.assertIn("/setWorkStatus", args[1])
        self.assertEqual(kwargs["json_data"]["mode"], 0)

    @patch("pyskmover.client._http_request")
    def test_set_work_mode_mowing(self, mock_req):
        mock_req.return_value = {}
        self.client.set_work_mode(WorkMode.MOWING)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["mode"], 1)

    @patch("pyskmover.client._http_request")
    def test_set_work_mode_border(self, mock_req):
        mock_req.return_value = {}
        self.client.set_work_mode(WorkMode.BORDER)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["mode"], 4)

    @patch("pyskmover.client._http_request")
    def test_start_mowing_convenience(self, mock_req):
        mock_req.return_value = {}
        self.client.start_mowing()
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["mode"], 1)

    @patch("pyskmover.client._http_request")
    def test_stop_mowing_convenience(self, mock_req):
        mock_req.return_value = {}
        self.client.stop_mowing()
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["mode"], 0)

    @patch("pyskmover.client._http_request")
    def test_start_border_convenience(self, mock_req):
        mock_req.return_value = {}
        self.client.start_border()
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["mode"], 4)

    @patch("pyskmover.client._http_request")
    def test_command_includes_app_id_and_device_sn(self, mock_req):
        mock_req.return_value = {}
        self.client.set_work_mode(WorkMode.STOP)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs["json_data"]["appId"], APP_ID)
        self.assertEqual(kwargs["json_data"]["deviceSn"], DEVICE_SN)

    @patch("pyskmover.client._http_request")
    def test_update_user(self, mock_req):
        mock_req.return_value = {}
        self.client.update_user("myFBToken", os_code="android")
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], "PUT")
        self.assertIn("/user/edit", args[1])
        self.assertEqual(kwargs["json_data"]["fbToken"], "myFBToken")
        self.assertEqual(kwargs["json_data"]["operatingSystemCode"], "android")

    def test_command_raises_when_not_authenticated(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        with self.assertRaises(SkMowerAuthError):
            client.set_work_mode(WorkMode.STOP)

    def test_command_raises_when_no_app_id(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        client._state.token = TokenResponse(access_token=TOKEN)
        # user_info is None → no appId
        with self.assertRaises(SkMowerError):
            client.set_work_mode(WorkMode.STOP)


# ---------------------------------------------------------------------------
# Tests for force_poll
# ---------------------------------------------------------------------------


class TestForcePoll(unittest.TestCase):

    @patch("pyskmover.client._http_request")
    def test_force_poll_updates_status(self, mock_req):
        status_raw = json.loads(STATUS_PAYLOAD)["data"]
        mock_req.return_value = status_raw
        client = _make_client_with_state()
        client.force_poll()
        self.assertIsNotNone(client.get_device_status())
        self.assertEqual(client.get_electricity(), 68)

    @patch("pyskmover.client._http_request")
    def test_force_poll_fires_status_callback(self, mock_req):
        status_raw = json.loads(STATUS_PAYLOAD)["data"]
        mock_req.return_value = status_raw
        received = []
        client = _make_client_with_state()
        client._on_status = lambda s: received.append(s)
        client.force_poll()
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], DeviceStatus)

    @patch("pyskmover.client._http_request")
    def test_force_poll_updates_setting(self, mock_req):
        setting_raw = json.loads(SETTING_PAYLOAD)["data"]
        mock_req.return_value = setting_raw
        client = _make_client_with_state()
        client.force_poll()
        self.assertIsNotNone(client.get_device_setting())
        self.assertEqual(client.get_device_setting().border_length, 224954)

    @patch("pyskmover.client._http_request")
    def test_force_poll_fires_setting_callback(self, mock_req):
        setting_raw = json.loads(SETTING_PAYLOAD)["data"]
        mock_req.return_value = setting_raw
        received = []
        client = _make_client_with_state()
        client._on_setting = lambda s: received.append(s)
        client.force_poll()
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], DeviceSetting)


# ---------------------------------------------------------------------------
# Tests for thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety(unittest.TestCase):

    def test_concurrent_reads_do_not_raise(self):
        """Multiple reader threads must not see partial / corrupt state."""
        status_raw = json.loads(STATUS_PAYLOAD)["data"]
        client = _make_client_with_state(status_data=status_raw)
        errors = []

        def reader():
            try:
                for _ in range(100):
                    _ = client.get_electricity()
                    _ = client.get_work_status_name()
                    _ = client.get_location()
                    _ = client.get_device_status()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")

    def test_concurrent_writes_do_not_raise(self):
        """Simulate the background thread writing status while readers poll."""
        status_raw = json.loads(STATUS_PAYLOAD)["data"]
        client = _make_client_with_state(status_data=status_raw)
        errors = []
        stop = threading.Event()

        def writer():
            try:
                while not stop.is_set():
                    with client._lock:
                        client._state.device_status = DeviceStatus.from_dict(
                            json.loads(STATUS_PAYLOAD)["data"]
                        )
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                for _ in range(200):
                    _ = client.get_electricity()
                    _ = client.get_work_status_name()
            except Exception as exc:
                errors.append(exc)

        w = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(5)]
        w.start()
        for r in readers:
            r.start()
        for r in readers:
            r.join()
        stop.set()
        w.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")


# ---------------------------------------------------------------------------
# Tests for client lifecycle
# ---------------------------------------------------------------------------


class TestClientLifecycle(unittest.TestCase):

    def test_stop_without_start_does_not_raise(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        client.stop()  # should not raise

    def test_is_connected_false_before_start(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        self.assertFalse(client.is_connected())

    def test_is_connected_false_when_no_token(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        # Simulate thread alive but token cleared
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        client._thread = mock_thread
        self.assertFalse(client.is_connected())

    def test_context_manager_calls_stop(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        with patch.object(client, "start") as mock_start, \
             patch.object(client, "stop") as mock_stop:
            with client:
                mock_start.assert_called_once()
            mock_stop.assert_called_once()

    def test_double_start_does_not_create_second_thread(self):
        client = SkMowerClient("u", "p", DEVICE_SN)
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        client._thread = mock_thread
        with patch("pyskmover.client._ConnectionThread") as MockThread:
            client.start()
            MockThread.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for exceptions
# ---------------------------------------------------------------------------


class TestExceptions(unittest.TestCase):

    def test_api_error_str(self):
        exc = SkMowerApiError(42, "Something went wrong")
        self.assertIn("42", str(exc))
        self.assertIn("Something went wrong", str(exc))
        self.assertEqual(exc.code, 42)
        self.assertEqual(exc.msg, "Something went wrong")

    def test_auth_error_is_skmower_error(self):
        self.assertTrue(issubclass(SkMowerAuthError, SkMowerError))

    def test_connection_error_is_skmower_error(self):
        self.assertTrue(issubclass(SkMowerConnectionError, SkMowerError))

    def test_api_error_is_skmower_error(self):
        self.assertTrue(issubclass(SkMowerApiError, SkMowerError))


if __name__ == "__main__":
    unittest.main()
