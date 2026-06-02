"""Base entity class for SK-Mower integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SkMowerCoordinator


class SkMowerEntity(CoordinatorEntity[SkMowerCoordinator]):
    """
    Base class for all SK-Mower entities.

    Provides:
    - coordinator binding via CoordinatorEntity
    - device_info from the coordinator
    - unique_id prefix based on device serial number
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SkMowerCoordinator,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        device_sn = coordinator.entry.data["device_sn"]
        self._attr_unique_id = f"{device_sn}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(**coordinator.device_info)

    # ------------------------------------------------------------------
    # Shortcut helpers
    # ------------------------------------------------------------------

    @property
    def _status(self):
        """Return the latest DeviceStatus or None."""
        data = self.coordinator.data or {}
        return data.get("status")

    @property
    def _setting(self):
        """Return the latest DeviceSetting or None."""
        data = self.coordinator.data or {}
        return data.get("setting")

    @property
    def _connected(self) -> bool:
        """Return True if the mower is reachable."""
        data = self.coordinator.data or {}
        return bool(data.get("connected", False))