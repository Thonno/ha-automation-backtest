/*
 * Automation Backtest – adds "Backtest" to
 *   - the ⋮ menu of each row in Settings → Automations, and
 *   - the automation editor: a toolbar button plus a ⋮ entry (passes the
 *     current, possibly unsaved, config).
 *
 * Home Assistant has no official API for this, so the entries are added from
 * outside. Several frontend generations are supported (ha-dropdown 2025.11+,
 * ha-md-button-menu / ha-md-menu, ha-button-menu). Everything fails silently:
 * if a future frontend changes these menus, the entry simply does not appear
 * and the sidebar panel keeps working.
 */
(() => {
  if (window.__automationBacktestMenu) return;
  window.__automationBacktestMenu = true;

  const VALUE = "automation_backtest";
  const DRAFT_KEY = "automation_backtest_draft";
  const PANEL = "/automation-backtest";
  // mdi:history
  const ICON = "M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3";
  const ITEM_TAGS = ["HA-DROPDOWN-ITEM", "HA-MD-MENU-ITEM", "HA-LIST-ITEM", "MWC-LIST-ITEM"];
  const DIVIDERS = ["WA-DIVIDER", "HA-MD-DIVIDER", "MD-DIVIDER", "LI"];

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

  function closeMenu(menu) {
    try {
      if ("open" in menu) menu.open = false;
      menu.close?.();
    } catch (_e) {
      /* ignore */
    }
  }

  const findDivider = (menu) =>
    [...menu.children].find((c) => DIVIDERS.includes(c.tagName) && (c.tagName !== "LI" || c.hasAttribute("divider"))) || null;

  /** Add an entry to a menu of any supported kind, copying the kind of its items. */
  function addMenuItem(menu, onSelect) {
    if (!menu || menu.querySelector(`[data-abt="${VALUE}"]`)) return;
    const sample = [...menu.children].find((c) => ITEM_TAGS.includes(c.tagName));
    if (!sample) return;
    const tag = sample.tagName.toLowerCase();
    const item = document.createElement(tag);
    item.dataset.abt = VALUE;
    item.setAttribute("value", VALUE);
    const icon = document.createElement("ha-svg-icon");
    icon.path = ICON;
    if (tag === "ha-dropdown-item") {
      icon.setAttribute("slot", "icon");
      item.append(icon, document.createTextNode(" Backtest "));
    } else if (tag === "ha-md-menu-item") {
      icon.setAttribute("slot", "start");
      const label = document.createElement("div");
      label.setAttribute("slot", "headline");
      label.textContent = "Backtest";
      item.append(icon, label);
      item.clickAction = () => onSelect(); // ha-md-menu closes itself
      menu.insertBefore(item, findDivider(menu));
      return;
    } else {
      icon.setAttribute("slot", "graphic");
      item.setAttribute("graphic", "icon");
      item.append(icon, document.createTextNode("Backtest"));
    }
    menu.insertBefore(item, findDivider(menu));
    item.addEventListener("click", () => {
      closeMenu(menu);
      onSelect();
    });
  }

  function entityForConfigId(id) {
    const states = hass()?.states || {};
    return Object.values(states).find((s) => s.entity_id.startsWith("automation.") && s.attributes?.id === id)?.entity_id;
  }

  function patchPicker(picker) {
    const menu = picker.shadowRoot?.querySelector("#overflow-menu");
    addMenuItem(menu, () => {
      const entityId = picker._overflowAutomation?.entity_id;
      navigate(entityId ? `${PANEL}?automation=${encodeURIComponent(entityId)}` : PANEL);
    });
  }

  function openFromEditor(editor) {
    try {
      window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(editor.config || null));
    } catch (_e) {
      /* storage unavailable: the panel falls back to the saved automation */
    }
    const entityId = editor.automationId ? entityForConfigId(editor.automationId) : null;
    navigate(`${PANEL}?${entityId ? `automation=${encodeURIComponent(entityId)}&` : ""}draft=1`);
  }

  function patchEditor(editor) {
    const sr = editor.shadowRoot;
    if (!sr) return;
    const slotted = [...sr.querySelectorAll('[slot="toolbar-icon"]')];
    const menu = slotted.find((el) => /DROPDOWN|BUTTON-MENU|MD-MENU/.test(el.tagName));
    addMenuItem(menu, () => openFromEditor(editor));
    // A visible toolbar button too: easier to find, and works whatever the menu is.
    if (!sr.querySelector(`ha-icon-button[data-abt="${VALUE}"]`) && customElements.get("ha-icon-button")) {
      const anchor = menu || slotted[slotted.length - 1];
      const parent = anchor?.parentNode;
      if (!parent) return;
      const btn = document.createElement("ha-icon-button");
      btn.dataset.abt = VALUE;
      btn.setAttribute("slot", "toolbar-icon");
      btn.label = "Backtest";
      btn.title = "Backtest";
      btn.path = ICON;
      btn.addEventListener("click", () => openFromEditor(editor));
      parent.insertBefore(btn, anchor);
    }
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
