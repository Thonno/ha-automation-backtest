"""Sidebar panel (official panel_custom API) and the ⋮-menu entry script."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_COMPONENT, PANEL_URL_PATH, STATIC_URL

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_MENU_URL = f"{DOMAIN}_menu_url"
FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_register_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(_STATIC_REGISTERED):
        # Static paths cannot be removed again, so register them only once per run.
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[_STATIC_REGISTERED] = True

    integration = await async_get_integration(hass, DOMAIN)
    menu_url = f"{STATIC_URL}/automation-backtest-menu.js?v={integration.version}"
    frontend.add_extra_js_url(hass, menu_url)
    hass.data[_MENU_URL] = menu_url
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{STATIC_URL}/automation-backtest-panel.js?v={integration.version}",
        sidebar_title="Backtest",
        sidebar_icon="mdi:history",
        require_admin=True,
        config={"version": integration.version},
    )


def async_unregister_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    if menu_url := hass.data.pop(_MENU_URL, None):
        frontend.remove_extra_js_url(hass, menu_url)
