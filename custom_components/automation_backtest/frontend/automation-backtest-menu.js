/*
 * Automation Backtest – adds a "Backtest" entry to the ⋮ menus of
 *   - the automation list (Settings → Automations), and
 *   - the automation editor (passes the current, possibly unsaved, config).
 *
 * Home Assistant has no official API for this, so the entry is added to the
 * existing menus from outside. It is written to fail silently: if a future
 * frontend changes these menus, the entry simply does not appear and the
 * sidebar panel keeps working.
 */
(() => {
  if (window.__automationBacktestMenu) return;
  window.__automationBacktestMenu = true;

  const VALUE = "automation_backtest";
  const DRAFT_KEY = "automation_backtest_draft";
  const PANEL = "/automation-backtest";
  // mdi:history
  const ICON = "M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3";

  const hassEl = () => document.querySelector("home-assistant");
  const hass = () => hassEl()?.hass;

  function find(root, selector, depth = 0) {
    if (!root || depth > 14) return null;
    const direct = root.querySelector?.(selector);
    if (direct) return direct;
    for (const el of root.querySelectorAll?.("*") || []) {
      if (el.shadowRoot) {
        const hit = find(el.shadowRoot, selector, depth + 1);
        if (hit) return hit;
      }
    }
    return null;
  }

  function navigate(url) {
    window.history.pushState(null, "", url);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  function makeItem(menu) {
    const item = document.createElement("ha-dropdown-item");
    item.setAttribute("value", VALUE);
    const icon = document.createElement("ha-svg-icon");
    icon.setAttribute("slot", "icon");
    icon.path = ICON;
    item.append(icon, document.createTextNode(" Backtest "));
    const divider = [...menu.children].find((c) => c.tagName === "WA-DIVIDER");
    menu.insertBefore(item, divider || null);
    return item;
  }

  function entityForConfigId(id) {
    const states = hass()?.states || {};
    return Object.values(states).find((s) => s.entity_id.startsWith("automation.") && s.attributes?.id === id)?.entity_id;
  }

  function patchPicker(picker) {
    const menu = picker.shadowRoot?.querySelector("#overflow-menu");
    if (!menu || menu.querySelector(`[value="${VALUE}"]`)) return;
    const item = makeItem(menu);
    item.addEventListener("click", () => {
      const entityId = picker._overflowAutomation?.entity_id;
      menu.open = false;
      navigate(entityId ? `${PANEL}?automation=${encodeURIComponent(entityId)}` : PANEL);
    });
  }

  function patchEditor(editor) {
    const menu = editor.shadowRoot?.querySelector('ha-dropdown[slot="toolbar-icon"]');
    if (!menu || menu.querySelector(`[value="${VALUE}"]`)) return;
    const item = makeItem(menu);
    item.addEventListener("click", () => {
      menu.open = false;
      try {
        window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(editor.config || null));
      } catch (_e) {
        /* storage unavailable: the panel falls back to the saved automation */
      }
      const entityId = editor.automationId ? entityForConfigId(editor.automationId) : null;
      navigate(`${PANEL}?${entityId ? `automation=${encodeURIComponent(entityId)}&` : ""}draft=1`);
    });
  }

  function tick() {
    try {
      if (!window.location.pathname.startsWith("/config/automation")) return;
      if (!hass()?.user?.is_admin) return;
      const picker = find(hassEl()?.shadowRoot, "ha-automation-picker");
      if (picker) patchPicker(picker);
      const editor = find(hassEl()?.shadowRoot, "ha-automation-editor");
      if (editor) patchEditor(editor);
    } catch (_e) {
      /* never break the HA frontend */
    }
  }

  window.addEventListener("location-changed", () => setTimeout(tick, 300));
  window.addEventListener("popstate", () => setTimeout(tick, 300));
  setInterval(tick, 1500);
  tick();
})();
