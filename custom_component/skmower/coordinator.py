"""
DataUpdateCoordinator for SK-Mower.

Wraps pyskmover.SkMowerClient and bridges the pyskmover polling thread
into the Home Assistant event loop via coordinator updates.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_SN,
    CONF_POLL_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SkMowerCoordinator(DataUpdateCoordinator):
    """
    Coordinator that owns a pyskmover.SkMowerClient instance.

    pyskmover polls on its own background thread every ``poll_interval``
    seconds.  Each time a new status or setting arrives the coordinator
    callback fires ``async_set_updated_data``, which propagates to all
    registered HA entities without a redundant HTTP round-trip from HA.

    ``async_update_data`` is still implemented so HA can request an
    immediate refresh (e.g. after a service call).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._client: Any = None  # pyskmover.SkMowerClient – imported lazily

        poll_interval = entry.options.get(
            CONF_POLL_INTERVAL,
            entry.data.get(CONF_POLL_INTERVAL, POLL_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Instantiate and start the pyskmover client."""
        from .pyskmover.client import SkMowerClient  # noqa: PLC0415

        entry = self.entry
        poll_interval = entry.options.get(
            CONF_POLL_INTERVAL,
            entry.data.get(CONF_POLL_INTERVAL, POLL_INTERVAL),
        )

        self._client = SkMowerClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            device_sn=entry.data[CONF_DEVICE_SN],
            poll_interval=poll_interval,
            on_status=self._on_status,
            on_setting=self._on_setting,
        )
        self._client.language = self.hass.config.language

        # Start the background connection thread
        await self.hass.async_add_executor_job(self._client.start)

        # Wait for authentication to complete (up to 10 seconds)
        for _ in range(10):
            if await self.hass.async_add_executor_job(self._client.is_connected):
                break
            await asyncio.sleep(1)

        # Do an initial forced poll so entities have data immediately
        try:
            await self.async_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Initial poll failed – will retry automatically")

    async def async_shutdown(self) -> None:
        """Stop the pyskmover client."""
        if self._client is not None:
            await self.hass.async_add_executor_job(self._client.stop)

    # ------------------------------------------------------------------
    # DataUpdateCoordinator implementation
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """
        Called by the coordinator on its own schedule AND after service calls.

        We run force_poll() in the executor (it is blocking I/O) and return
        a snapshot dict that entities can read from ``coordinator.data``.
        """
        from .pyskmover.exceptions import SkMowerError  # noqa: PLC0415

        if self._client is None:
            raise UpdateFailed("Client not initialised")

        try:
            await self.hass.async_add_executor_job(self._client.force_poll)
        except SkMowerError as exc:
            raise UpdateFailed(f"SK-Mower poll failed: {exc}") from exc

        return self._build_data_snapshot()

    # ------------------------------------------------------------------
    # pyskmover callbacks (called from the pyskmover background thread)
    # ------------------------------------------------------------------

    def _on_status(self, status: Any) -> None:
        """Called by pyskmover when a new DeviceStatus arrives."""
        asyncio.run_coroutine_threadsafe(
            self._async_push_update(),
            self.hass.loop,
        )

    def _on_setting(self, setting: Any) -> None:
        """Called by pyskmover when a new DeviceSetting arrives."""
        asyncio.run_coroutine_threadsafe(
            self._async_push_update(),
            self.hass.loop,
        )

    async def _async_push_update(self) -> None:
        """Push fresh data to all listeners without a new HTTP call."""
        self.async_set_updated_data(self._build_data_snapshot())

    # ------------------------------------------------------------------
    # Data snapshot
    # ------------------------------------------------------------------

    def _build_data_snapshot(self) -> dict:
        """Return a plain dict snapshot of the current client state."""
        if self._client is None:
            return {}

        status = self._client.get_device_status()
        setting = self._client.get_device_setting()

        # Log data availability for debugging
        _LOGGER.debug(
            "Building snapshot: status=%s, setting=%s, connected=%s",
            "yes" if status else "no",
            "yes" if setting else "no",
            self._client.is_connected(),
        )

        data: dict = {
            "status": status,
            "setting": setting,
            "connected": self._client.is_connected(),
        }
        return data

    # ------------------------------------------------------------------
    # Convenience accessors used by platform entities
    # ------------------------------------------------------------------

    @property
    def client(self) -> Any:
        """Return the underlying pyskmover.SkMowerClient."""
        return self._client

    @property
    def device_info(self) -> dict:
        """Return HA device-registry info dict."""
        entry = self.entry
        device_sn = entry.data[CONF_DEVICE_SN]

        # Try to get the device name from the latest status/setting
        data = self.data or {}
        name = device_sn
        status = data.get("status")
        setting = data.get("setting")
        if setting and getattr(setting, "device_name", None):
            name = setting.device_name
        elif status and getattr(status, "device_name", None):
            name = status.device_name

        return {
            "identifiers": {(DOMAIN, device_sn)},
            "name": name,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "serial_number": device_sn,
        }