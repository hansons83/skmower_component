"""Lawn mower platform for SK-Mower integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import translation

from .const import (
    ATTR_AREA,
    ATTR_BATTERY,
    ATTR_BORDER_LENGTH,
    ATTR_BOUND_AT,
    ATTR_COLLECTED_AT,
    ATTR_DEVICE_ID,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_TYPE,
    ATTR_FAULT_STATUS,
    ATTR_ON_MINUTES,
    ATTR_RAIN_DELAY_LEFT,
    ATTR_FIRMWARE,
    ATTR_GPS,
    ATTR_IP_ADDRESS,
    ATTR_LAST_SYNCED,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_MODEL_NAME,
    ATTR_ONLINE_STATUS,
    ATTR_RAIN_FLAG,
    ATTR_RAIN_STATUS,
    ATTR_STATION_FLAG,
    ATTR_TIME_ZONE,
    ATTR_TOTAL_MINUTES,
    ATTR_WIFI_FLAG,
    ATTR_WIFI_LEVEL,
    ATTR_WORK_STATUS,
    ATTR_WORK_STATUS_CODE,
    ATTR_WORK_STATUS_NAME,
    DOMAIN,
)
from .coordinator import SkMowerCoordinator
from .entity import SkMowerEntity

_LOGGER = logging.getLogger(__name__)

# Work status code → LawnMowerActivity mapping
# Based on latest observations:
# "0" -> idea (idle/ready)
# "1" -> work (mowing)
# "2" -> return (returning home)
# "3" -> charge (docked/charging)
# "4" -> abnormal (error)
# "5" -> paused
# "7" -> edge (border mowing)
_STATUS_TO_ACTIVITY: dict[str, LawnMowerActivity] = {
    "0": LawnMowerActivity.PAUSED,
    "1": LawnMowerActivity.MOWING,
    "2": LawnMowerActivity.RETURNING,
    "3": LawnMowerActivity.DOCKED,
    "4": LawnMowerActivity.ERROR,
    "5": LawnMowerActivity.PAUSED,
    "7": LawnMowerActivity.MOWING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SK-Mower lawn_mower entity."""
    coordinator: SkMowerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SkMowerLawnMower(coordinator)])


class SkMowerLawnMower(SkMowerEntity, LawnMowerEntity):
    """
    Main lawn-mower entity for SK-Mower integration.
    """

    _attr_translation_key = "lawn_mower"
    _attr_name = None  # use device name directly

    def __init__(self, coordinator: SkMowerCoordinator) -> None:
        super().__init__(coordinator, "lawn_mower")

    @property
    def supported_features(self) -> LawnMowerEntityFeature:
        """Dynamic supported features based on state."""
        status = self._status
        if status is None:
            return LawnMowerEntityFeature(0)

        code = str(status.work_status_code)
        
        # Default features
        features = LawnMowerEntityFeature(0)

        # Kiedy Zatrzymany (0) można tylko wybrać powrót do bazy (DOCK)can start mowing
        if code == "0":
            return LawnMowerEntityFeature.DOCK | LawnMowerEntityFeature.START_MOWING

        # Kiedy błąd (4) można tylko zatrzymać (PAUSE/DOCK)
        if code == "4":
            return LawnMowerEntityFeature.DOCK | LawnMowerEntityFeature.PAUSE

        # Kiedy Powrót (2) można tylko zatrzymać (PAUSE)
        if code == "2":
            return LawnMowerEntityFeature.PAUSE | LawnMowerEntityFeature.DOCK

        # Brzeg (7) można wybrac tylko gdy zadokowany (3). 
        # START_MOWING jest ogólnym startem.
        if code == "3":
            # Docked/Charging - can start mowing
            return LawnMowerEntityFeature.START_MOWING

        # If mowing (1) or border (7), can pause or dock
        if code in ("1", "7"):
            return (
                LawnMowerEntityFeature.PAUSE
            )

        # Fallback to all if state unknown
        return (
            LawnMowerEntityFeature.START_MOWING
            | LawnMowerEntityFeature.DOCK
            | LawnMowerEntityFeature.PAUSE
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current mowing activity."""
        status = self._status
        if status is None or status.work_status_code is None:
            return None

        # Logic for 'Returning home' based on observed pause flag
        if status.pause:
            return LawnMowerActivity.RETURNING

        # Ensure we use string for lookup
        code = str(status.work_status_code)
        return _STATUS_TO_ACTIVITY.get(code, LawnMowerActivity.ERROR)

    @property
    def available(self) -> bool:
        """Return True if we have received at least one status update."""
        return self.coordinator.last_update_success and (self._status is not None or self._setting is not None)

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the lawn mower."""
        status = self._status
        if status is None:
            return None
        return status.electricity

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose additional device state as entity attributes."""
        attrs: dict[str, Any] = {}
        status = self._status
        setting = self._setting

        if status:
            attrs[ATTR_DEVICE_SN] = status.device_sn
            attrs[ATTR_DEVICE_ID] = status.device_id
            attrs[ATTR_BATTERY] = status.electricity
            attrs[ATTR_WORK_STATUS_CODE] = status.work_status_code

            # Use HA translation system for work status mapping
            # This follows the pattern in selector/work_status/options in translations
            code = str(status.work_status_code)
            attrs[ATTR_WORK_STATUS] = translation.async_translate_state(
                self.hass,
                self.entity_id,
                DOMAIN,
                "work_status",
                None,  # device_class
                code,
            )

            attrs[ATTR_WORK_STATUS_NAME] = status.work_status_name
            attrs[ATTR_FAULT_STATUS] = status.fault_status_code
            attrs[ATTR_RAIN_STATUS] = status.rain_status_code
            attrs[ATTR_RAIN_FLAG] = status.rain_flag
            attrs[ATTR_RAIN_DELAY_LEFT] = status.rain_delay_left
            attrs[ATTR_STATION_FLAG] = status.station_flag
            attrs[ATTR_WIFI_FLAG] = status.wifi_flag
            attrs[ATTR_WIFI_LEVEL] = status.wifi_lv
            attrs[ATTR_ONLINE_STATUS] = status.online_flag
            attrs[ATTR_LATITUDE] = status.lat
            attrs[ATTR_LONGITUDE] = status.lng
            attrs[ATTR_GPS] = status.gps
            attrs[ATTR_IP_ADDRESS] = status.ip_addr
            attrs[ATTR_MODEL_NAME] = status.model_name
            attrs[ATTR_FIRMWARE] = status.firmware_version
            attrs[ATTR_DEVICE_TYPE] = status.device_type
            attrs[ATTR_BOUND_AT] = status.bound_at
            attrs[ATTR_ON_MINUTES] = status.on_min
            attrs[ATTR_TOTAL_MINUTES] = status.total_min
            attrs[ATTR_AREA] = status.area
            attrs[ATTR_COLLECTED_AT] = status.collected_at

        if setting:
            attrs[ATTR_BORDER_LENGTH] = setting.border_length
            attrs[ATTR_TIME_ZONE] = setting.time_zone_id
            attrs[ATTR_LAST_SYNCED] = setting.updated_at
            attrs["rain_delay_duration"] = setting.rain_delay_duration
            attrs["schedule_auto"] = setting.schedule_auto_flag
            attrs["zone_open"] = setting.zone_open_flag
            attrs["ultra_flag"] = setting.ultra_flag
            attrs["now_time"] = setting.now_time
            # Capability flags
            attrs["multizone_support"] = setting.multizone_support
            attrs["rain_support"] = setting.rain_support
            attrs["ultra_support"] = setting.ultra_support
            attrs["led_support"] = setting.led_support
            attrs["gps_support"] = setting.gps_support

        return attrs

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_start_mowing(self) -> None:
        """Start mowing – mode 1."""
        await self._async_send_command("start_mowing")

    async def async_dock(self) -> None:
        """Send mower back to dock / stop."""
        await self._async_send_command("return_to_dock")

    async def async_pause(self) -> None:
        """Pause mowing."""
        await self._async_send_command("stop_mowing")

    async def _async_send_command(self, command: str) -> None:
        """Execute a pyskmover command and refresh state."""
        client = self.coordinator.client
        if client is None:
            raise HomeAssistantError("SK-Mower client is not initialised")

        try:
            if command == "start_mowing":
                await self.hass.async_add_executor_job(client.start_mowing)
            elif command == "stop_mowing":
                await self.hass.async_add_executor_job(client.stop_mowing)
            elif command == "return_to_dock":
                await self.hass.async_add_executor_job(client.return_to_dock)
            elif command == "start_border":
                await self.hass.async_add_executor_job(client.start_border)
            else:
                raise HomeAssistantError(f"Unknown command: {command}")
        except HomeAssistantError:
            raise
        except Exception as exc:
            raise HomeAssistantError(
                f"SK-Mower command '{command}' failed: {exc}"
            ) from exc

        # Refresh state after command
        await self.coordinator.async_request_refresh()