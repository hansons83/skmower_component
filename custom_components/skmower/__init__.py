"""
SK-Mower – Home Assistant integration.

Integrates SK-Robot robotic lawn mowers using the pyskmover library.

Domain: skmover
Platforms: lawn_mower
Services: start_mowing, stop_mowing, start_border, force_poll
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEVICE_SN,
    DOMAIN,
    POLL_INTERVAL,
    SERVICE_FORCE_POLL,
    SERVICE_START_BORDER,
    SERVICE_START_MOWING,
    SERVICE_STOP_MOWING,
)
from .coordinator import SkMowerCoordinator

# Add relative import for pyskmover
from .pyskmover.client import SkMowerClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LAWN_MOWER]

# Service schema – allow targeting entities
_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.comp_entity_ids,
    }
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SK-Mower from a config entry."""
    coordinator = SkMowerCoordinator(
        hass=hass,
        entry=entry,
    )

    await coordinator.async_setup()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Could not connect to SK-Robot server")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---------------------------------------------------------------
    # Custom services
    # ---------------------------------------------------------------

    async def _handle_start_mowing(call: ServiceCall) -> None:
        """Handle skmover.start_mowing service call."""
        await _dispatch_command(hass, call, "start_mowing")

    async def _handle_stop_mowing(call: ServiceCall) -> None:
        """Handle skmover.stop_mowing service call."""
        await _dispatch_command(hass, call, "stop_mowing")

    async def _handle_start_border(call: ServiceCall) -> None:
        """Handle skmover.start_border service call."""
        await _dispatch_command(hass, call, "start_border")

    async def _handle_force_poll(call: ServiceCall) -> None:
        """Handle skmover.force_poll service call."""
        await _dispatch_command(hass, call, "force_poll")

    # Only register services once (shared across all config entries)
    if not hass.services.has_service(DOMAIN, SERVICE_START_MOWING):
        hass.services.async_register(
            DOMAIN, SERVICE_START_MOWING, _handle_start_mowing, schema=_SERVICE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_STOP_MOWING, _handle_stop_mowing, schema=_SERVICE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_START_BORDER, _handle_start_border, schema=_SERVICE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_FORCE_POLL, _handle_force_poll, schema=_SERVICE_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SkMowerCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    # Remove services when the last entry is removed
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_START_MOWING)
        hass.services.async_remove(DOMAIN, SERVICE_STOP_MOWING)
        hass.services.async_remove(DOMAIN, SERVICE_START_BORDER)
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_POLL)

    return unload_ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _dispatch_command(
    hass: HomeAssistant, call: ServiceCall, command: str
) -> None:
    """
    Route a service call to all active SK-Mower coordinators.

    HA services targeting an entity are routed by entity_id, but since these
    services do not require a specific entity we apply the command to every
    loaded coordinator (one per config entry / device).
    """
    coordinators: list[SkMowerCoordinator] = list(hass.data.get(DOMAIN, {}).values())
    if not coordinators:
        raise HomeAssistantError("No SK-Mower devices are configured")

    for coordinator in coordinators:
        client = coordinator.client
        if client is None:
            continue
        try:
            if command == "start_mowing":
                await hass.async_add_executor_job(client.start_mowing)
            elif command == "stop_mowing":
                await hass.async_add_executor_job(client.stop_mowing)
            elif command == "start_border":
                await hass.async_add_executor_job(client.start_border)
            elif command == "force_poll":
                await hass.async_add_executor_job(client.force_poll)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("SK-Mower service '%s' failed: %s", command, exc)
            raise HomeAssistantError(
                f"SK-Mower service '{command}' failed: {exc}"
            ) from exc

        # Refresh coordinator state after any command
        if command != "force_poll":
            await coordinator.async_request_refresh()
        else:
            # force_poll already fetched fresh data; just push it to listeners
            coordinator.async_set_updated_data(coordinator._build_data_snapshot())