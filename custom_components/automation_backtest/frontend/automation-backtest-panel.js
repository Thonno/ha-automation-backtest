/*
 * Automation Backtest – sidebar panel.
 * Plain web component: no build step, no external dependencies.
 * Talks to the integration through the automation_backtest/* websocket commands
 * and to the recorder through history/history_during_period.
 */

const STR = {
  en: {
    title: "Automation Backtest",
    subtitle: "Replay automations on your history",
    newDraft: "＋ New automation (draft)",
    newHint: "Build the triggers and conditions of an automation you have not created yet: you will see when it would have run if it had existed.",
    draftFromEditor: "Unsaved changes from the automation editor",
    compareNeedsSaved: "Compare needs a saved automation to use as version A.",
    automation: "Automation",
    search: "Search…",
    period: "Period",
    custom: "Custom",
    from: "From",
    to: "To",
    run: "Run backtest",
    running: "Replaying history…",
    tabRun: "Backtest",
    tabCompare: "Compare",
    editYaml: "Try a change (draft)",
    resetYaml: "Reset to saved",
    visual: "Visual",
    yamlMode: "YAML",
    when: "When",
    andIf: "And if",
    openInHa: "Open in the HA editor",
    createInHa: "Create in the HA editor",
    unsaved: "Unsaved draft",
    loadingEditor: "Loading the editor…",
    visualUnavailable: "The visual editor is not available in this Home Assistant version: using YAML.",
    draft: "Testing an unsaved draft",
    triggered: "Triggered",
    executed: "Executed",
    blocked: "Blocked",
    uncertain: "Uncertain",
    restarts: "HA restarts",
    unsupported: "Not simulated",
    warnings: "Warnings",
    noRuns: "The automation would not have triggered in this period.",
    pickRun: "Select a run on the chart or in the list to see why it ran or not.",
    noConditions: "No conditions: it runs every time it triggers.",
    trigger: "Trigger",
    conditions: "Conditions",
    blockedBy: "Blocked by",
    uncertainBecause: "Uncertain because",
    centre: "Zoom here",
    resetZoom: "Reset zoom",
    zoomHint: "Drag on the chart to zoom · double-click to reset",
    showMore: "Show more",
    of: "of",
    truncated: "Only the first {n} runs are shown.",
    openAutomation: "Open automation",
    versionA: "A · current",
    versionB: "B · your edit",
    compare: "Compare A and B",
    comparing: "Replaying both versions…",
    both: "In both",
    onlyA: "Only A",
    onlyB: "Only B",
    shifted: "Shifted",
    shiftedHint: "Same event, different time",
    earlier: "earlier",
    later: "later",
    noDiff: "No difference: both versions run at exactly the same moments.",
    restartBand: "Home Assistant was restarting: automations were not listening",
    dayShort: "d",
    selectFirst: "Choose an automation first.",
    nothingInView: "Nothing in this part of the chart.",
    status: { executed: "Executed", blocked: "Blocked", uncertain: "Uncertain" },
  },
  it: {
    title: "Automation Backtest",
    subtitle: "Rigioca le automazioni sul tuo storico",
    newDraft: "＋ Nuova automazione (bozza)",
    newHint: "Componi trigger e condizioni di un'automazione che non hai ancora creato: vedrai quando sarebbe partita se fosse esistita.",
    draftFromEditor: "Modifiche non salvate dall'editor dell'automazione",
    compareNeedsSaved: "Il confronto richiede un'automazione salvata da usare come versione A.",
    automation: "Automazione",
    search: "Cerca…",
    period: "Periodo",
    custom: "Personalizzato",
    from: "Dal",
    to: "Al",
    run: "Avvia backtest",
    running: "Rigioco lo storico…",
    tabRun: "Backtest",
    tabCompare: "Confronta",
    editYaml: "Prova una modifica (bozza)",
    resetYaml: "Ripristina salvata",
    visual: "Visuale",
    yamlMode: "YAML",
    when: "Quando",
    andIf: "E se",
    openInHa: "Apri nell'editor di HA",
    createInHa: "Crea nell'editor di HA",
    unsaved: "Bozza non salvata",
    loadingEditor: "Carico l'editor…",
    visualUnavailable: "L'editor visuale non è disponibile in questa versione di Home Assistant: uso lo YAML.",
    draft: "Stai provando una bozza non salvata",
    triggered: "Scattata",
    executed: "Eseguita",
    blocked: "Bloccata",
    uncertain: "Incerta",
    restarts: "Riavvii di HA",
    unsupported: "Non simulato",
    warnings: "Avvisi",
    noRuns: "In questo periodo l'automazione non sarebbe mai scattata.",
    pickRun: "Seleziona un'esecuzione sul grafico o nella lista per vedere perché è partita o no.",
    noConditions: "Nessuna condizione: parte ogni volta che scatta.",
    trigger: "Trigger",
    conditions: "Condizioni",
    blockedBy: "Bloccata da",
    uncertainBecause: "Incerta perché",
    centre: "Zoom qui",
    resetZoom: "Annulla zoom",
    zoomHint: "Trascina sul grafico per lo zoom · doppio clic per annullare",
    showMore: "Mostra altre",
    of: "di",
    truncated: "Sono mostrate solo le prime {n} esecuzioni.",
    openAutomation: "Apri automazione",
    versionA: "A · attuale",
    versionB: "B · la tua modifica",
    compare: "Confronta A e B",
    comparing: "Rigioco entrambe le versioni…",
    both: "In entrambe",
    onlyA: "Solo A",
    onlyB: "Solo B",
    shifted: "Spostate",
    shiftedHint: "Stesso evento, orario diverso",
    earlier: "prima",
    later: "dopo",
    noDiff: "Nessuna differenza: le due versioni partono esattamente negli stessi momenti.",
    restartBand: "Home Assistant si stava riavviando: le automazioni non erano in ascolto",
    dayShort: "g",
    selectFirst: "Scegli prima un'automazione.",
    nothingInView: "Niente in questa parte del grafico.",
    status: { executed: "Eseguita", blocked: "Bloccata", uncertain: "Incerta" },
  },
};

const NEW = "__new__";
const DRAFT_KEY = "automation_backtest_draft";
const TEMPLATE = `triggers:
  - trigger: state
    entity_id: binary_sensor.example
    to: "on"
conditions: []
`;
const LOGO = `<svg viewBox="0 0 64 64" class="logo-ic" aria-hidden="true"><defs><linearGradient id="abt-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fbb04f"/><stop offset="1" stop-color="#e5762f"/></linearGradient></defs><rect x="4" y="4" width="56" height="56" rx="16" fill="url(#abt-g)"/><path d="M32 15a17 17 0 1 1-16.1 11.6" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/><path d="M12 17v11h11" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 23v10l7 5" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const MENU_PATH = "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";
const ICON = { executed: "✓", blocked: "✕", uncertain: "?" };
const PERIODS = [1, 3, 7, 14];
const LIST_PAGE = 200;
const MAX_ENTITY_LANES = 8;

function findDeep(root, selector, depth = 0) {
  if (!root || depth > 12) return null;
  const hit = root.querySelector?.(selector);
  if (hit) return hit;
  for (const el of root.querySelectorAll?.("*") || []) {
    if (el.shadowRoot) {
      const found = findDeep(el.shadowRoot, selector, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

const asList = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);
const normalise = (cfg) => ({
  triggers: asList(cfg?.triggers ?? cfg?.trigger),
  conditions: asList(cfg?.conditions ?? cfg?.condition),
});

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const PALETTE = ["#5b8def", "#e8a33d", "#9b6bd6", "#3fb6a8", "#d9667a", "#7a9e3b", "#c77c3a", "#4fa3d1"];
function stateColor(state) {
  const s = String(state);
  if (["on", "home", "open", "playing", "heat", "cleaning", "unlocked"].includes(s)) return "rgba(246,162,58,.75)";
  if (["off", "not_home", "closed", "idle", "docked", "locked", "standby"].includes(s)) return "rgba(var(--fgr),.14)";
  if (["unavailable", "unknown"].includes(s)) return "transparent";
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

class AutomationBacktestPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._s = {
      tab: "run",
      automation: "",
      filter: "",
      days: 3,
      custom: false,
      start: "",
      end: "",
      saved: null, // {yaml, config, id} of the stored automation
      editing: false, // a draft is being tried
      mode: "visual", // visual | yaml
      draft: null, // {triggers, conditions} (visual source of truth)
      yaml: "", // yaml source of truth in yaml mode
      dirty: false,
      fromEditor: false,
      visualOk: null, // null = not tried yet
      loading: false,
      error: "",
      result: null,
      cmp: null,
      history: {},
      view: null,
      selected: -1,
      statusFilter: null,
      listLimit: LIST_PAGE,
    };
    this._drag = null;
  }

  // --- HA plumbing --------------------------------------------------------

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._applyTheme();
    if (this._vis) {
      this._vis.tr.hass = hass;
      this._vis.co.hass = hass;
    }
    if (this._code && this._code.tagName !== "TEXTAREA") this._code.hass = hass;
    if (first) this._init();
  }

  _applyTheme() {
    const ha = this._hass?.themes?.darkMode;
    const dark = typeof ha === "boolean" ? ha : !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    const mode = dark ? "dark" : "light";
    if (this.getAttribute("theme") !== mode) this.setAttribute("theme", mode);
  }

  set narrow(value) {
    this._narrow = value;
    if (this._root) this._root.classList.toggle("narrow", !!value);
    if (this._vis) {
      this._vis.tr.narrow = !!value;
      this._vis.co.narrow = !!value;
    }
  }

  set panel(_value) {}

  get _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return STR[lang] || STR.en;
  }

  get _tz() {
    return this._hass?.config?.time_zone;
  }

  _fmt(ms, opts) {
    try {
      return new Intl.DateTimeFormat(this._hass?.locale?.language || "en", { timeZone: this._tz, ...opts }).format(ms);
    } catch (_e) {
      return new Date(ms).toLocaleString();
    }
  }

  _fmtFull(ms) {
    return this._fmt(ms, { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  _automations() {
    return Object.values(this._hass.states)
      .filter((s) => s.entity_id.startsWith("automation."))
      .map((s) => ({ id: s.entity_id, name: s.attributes.friendly_name || s.entity_id, cfgId: s.attributes.id, state: s.state }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  async _ws(msg) {
    return this._hass.callWS(msg);
  }

  // --- lifecycle -----------------------------------------------------------

  _init() {
    const t = this._t;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="root${this._narrow ? " narrow" : ""}">
        <header>
          <button class="ib menu" aria-label="Menu"><svg viewBox="0 0 24 24"><path d="${MENU_PATH}"/></svg></button>
          <div class="tt">
            <h1 class="logo" aria-label="${esc(t.title)}">${LOGO}<span>Automation<b>Backtest</b></span></h1>
            <div class="who">${esc(t.subtitle)}</div>
          </div>
        </header>
        <main>
          <section class="card controls"></section>
          <nav class="tabs"></nav>
          <div class="body"></div>
        </main>
      </div>`;
    this._root = this.shadowRoot.querySelector(".root");
    this._controls = this.shadowRoot.querySelector(".controls");
    this._tabs = this.shadowRoot.querySelector(".tabs");
    this._body = this.shadowRoot.querySelector(".body");

    this.shadowRoot.querySelector(".ib.menu").addEventListener("click", () =>
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
    this.shadowRoot.addEventListener("dblclick", (e) => {
      if (e.target.closest(".chart")) this._setView(null);
    });
    this._bindDrag();
    window.addEventListener("resize", () => this._renderChartOnly());

    window.addEventListener("location-changed", () => {
      if (window.location.pathname.startsWith("/automation-backtest")) setTimeout(() => this._fromUrl(), 0);
    });
    this._renderAll();
    this._fromUrl();
  }

  _fromUrl() {
    // Deep links: ?automation=automation.x  (from the ⋮ menu of the list)
    //             ?automation=automation.x&draft=1 / ?draft=1  (from the editor, unsaved config)
    const search = window.location.search;
    if (search === this._lastSearch) return;
    this._lastSearch = search;
    const params = new URLSearchParams(search);
    const fromUrl = params.get("automation");
    const known = fromUrl && this._hass.states[fromUrl] ? fromUrl : null;
    if (!params.get("draft") && !known) return;
    const s = this._s;
    Object.assign(s, {
      tab: "run", result: null, cmp: null, selected: -1, view: null, error: "",
      saved: null, editing: false, draft: null, yaml: "", dirty: false, fromEditor: false, statusFilter: null,
    });
    if (params.get("draft")) {
      this._loadDraft(known);
      return;
    }
    s.automation = known;
    this._renderAll();
    this._loadSaved().then(() => this._runBacktest());
  }

  // --- rendering -----------------------------------------------------------

  _renderAll() {
    this._renderControls();
    this._renderTabs();
    this._renderBody();
  }

  _renderControls() {
    const t = this._t;
    const s = this._s;
    const autos = this._automations();
    const q = s.filter.toLowerCase();
    const shown = autos.filter((a) => !q || a.name.toLowerCase().includes(q) || a.id.includes(q) || a.id === s.automation);
    const current = autos.find((a) => a.id === s.automation);
    const openLink = current?.cfgId
      ? `<a class="link" href="/config/automation/edit/${encodeURIComponent(current.cfgId)}" target="_top">${esc(t.openAutomation)} ↗</a>`
      : "";
    this._controls.innerHTML = `
      <div class="field grow">
        <label>${esc(t.automation)}</label>
        <div class="pick">
          <input class="filter" type="search" placeholder="${esc(t.search)}" value="${esc(s.filter)}">
          <select class="auto">
            <option value="">—</option>
            <option value="${NEW}"${s.automation === NEW ? " selected" : ""}>${esc(t.newDraft)}</option>
            ${shown.map((a) => `<option value="${esc(a.id)}"${a.id === s.automation ? " selected" : ""}>${esc(a.name)}${a.state === "off" ? " (off)" : ""}</option>`).join("")}
          </select>
        </div>
        ${openLink}
      </div>
      <div class="field">
        <label>${esc(t.period)}</label>
        <div class="seg">
          ${PERIODS.map((d) => `<button data-days="${d}" class="${!s.custom && s.days === d ? "on" : ""}">${d}${esc(t.dayShort)}</button>`).join("")}
          <button data-custom="1" class="${s.custom ? "on" : ""}">${esc(t.custom)}</button>
        </div>
        ${s.custom ? `<div class="range">
          <label>${esc(t.from)} <input type="datetime-local" class="start" value="${esc(s.start)}"></label>
          <label>${esc(t.to)} <input type="datetime-local" class="end" value="${esc(s.end)}"></label>
        </div>` : ""}
      </div>
      <div class="field actions">
        <button class="primary go" ${s.loading ? "disabled" : ""}>${esc(s.tab === "run" ? t.run : t.compare)}</button>
      </div>`;
  }

  _renderTabs() {
    const t = this._t;
    this._tabs.innerHTML = ["run", "compare"]
      .map((k) => `<button data-tab="${k}" class="${this._s.tab === k ? "on" : ""}">${esc(k === "run" ? t.tabRun : t.tabCompare)}</button>`)
      .join("");
  }

  _renderBody() {
    const s = this._s;
    const t = this._t;
    let html = "";
    if (s.error) html += `<div class="banner error">${esc(s.error)}</div>`;
    html += s.tab === "run" ? this._runTab() : this._compareTab();
    if (s.loading) html += `<div class="loading"><span class="spinner"></span>${esc(s.tab === "run" ? t.running : t.comparing)}</div>`;
    this._body.innerHTML = html;
    this._mountEditor();
    this._renderChartOnly();
  }

  _draftEditor(forCompare = false) {
    const t = this._t;
    const s = this._s;
    if (!s.automation) return "";
    const isNew = s.automation === NEW;
    const cfgId = s.saved?.id;
    const haLink = isNew
      ? `<a class="link" href="/config/automation/edit/new" target="_top">${esc(t.createInHa)} ↗</a>`
      : cfgId ? `<a class="link" href="/config/automation/edit/${encodeURIComponent(cfgId)}" target="_top">${esc(t.openInHa)} ↗</a>` : "";
    const open = isNew || forCompare || s.editing;
    let html = `<div class="card draft">`;
    if (forCompare) html += `<h3>${esc(t.versionB)}</h3>`;
    if (isNew) html += `<p class="muted hint-p">${esc(t.newHint)}</p>`;
    if (s.fromEditor) html += `<div class="badge warn">${esc(t.draftFromEditor)}</div>`;
    if (!isNew && !forCompare) {
      html += `<label class="check"><input type="checkbox" class="draft-toggle" ${s.editing ? "checked" : ""}> ${esc(t.editYaml)}</label>`;
    }
    if (open) {
      html += `<div class="draft-bar">
        <div class="seg small">
          <button data-mode="visual" class="${s.mode === "visual" ? "on" : ""}">${esc(t.visual)}</button>
          <button data-mode="yaml" class="${s.mode === "yaml" ? "on" : ""}">${esc(t.yamlMode)}</button>
        </div>
        <span class="badge warn dirty-badge"${s.dirty && !isNew ? "" : " hidden"}>${esc(t.unsaved)}</span>
        <span class="grow"></span>
        ${!isNew ? `<button class="flat reset-draft">${esc(t.resetYaml)}</button>` : ""}
        ${haLink}
      </div>
      ${s.visualOk === false && s.mode === "yaml" ? `<div class="banner info">${esc(t.visualUnavailable)}</div>` : ""}
      <div class="ve-slot"><div class="empty">${esc(t.loadingEditor)}</div></div>`;
    }
    return html + `</div>`;
  }

  _runTab() {
    const s = this._s;
    const t = this._t;
    let html = this._draftEditor(false);
    const r = s.result;
    if (!r) return html;
    html += this._summary(r);
    html += this._notices(r);
    if (!r.runs.length) {
      html += `<div class="card empty">${esc(t.noRuns)}</div>`;
    }
    html += `<div class="card chart-card">
      <div class="row between"><span class="hint">${esc(t.zoomHint)}</span>
      ${s.view ? `<button class="flat reset-zoom">${esc(t.resetZoom)}</button>` : ""}</div>
      <div class="chart"></div></div>`;
    if (r.runs.length) {
      html += `<div class="split"><div class="card list">${this._runList(r)}</div><div class="card detail">${this._detail(r)}</div></div>`;
    }
    return html;
  }

  _summary(r) {
    const t = this._t;
    const f = this._s.statusFilter;
    const chip = (key, label, n) =>
      `<button class="chip ${key}${f === key ? " on" : ""}" data-filter="${key}"><b>${n}</b> ${esc(label)}</button>`;
    return `<div class="chips">
      <span class="chip plain"><b>${r.summary.triggered}</b> ${esc(t.triggered)}</span>
      ${chip("executed", t.executed, r.summary.executed)}
      ${chip("blocked", t.blocked, r.summary.blocked)}
      ${chip("uncertain", t.uncertain, r.summary.uncertain)}
      ${r.restarts?.length ? `<span class="chip plain restart">↻ <b>${r.restarts.length}</b> ${esc(t.restarts)}</span>` : ""}
    </div>`;
  }

  _notices(r) {
    const t = this._t;
    let html = "";
    if (r.unsupported_triggers?.length) {
      html += `<div class="banner info"><b>${esc(t.unsupported)}:</b> ${r.unsupported_triggers
        .map((u) => `#${u.index} ${esc(u.platform || "")} – ${esc(u.reason)}`)
        .join("<br>")}</div>`;
    }
    if (r.warnings?.length) {
      html += `<div class="banner warn"><b>${esc(t.warnings)}:</b> ${r.warnings.map(esc).join("<br>")}</div>`;
    }
    if (r.truncated) html += `<div class="banner info">${esc(t.truncated.replace("{n}", r.runs.length))}</div>`;
    return html;
  }

  _visibleRuns(r) {
    const s = this._s;
    return r.runs
      .map((run, idx) => ({ run, idx, ms: Date.parse(run.time) }))
      .filter((x) => !s.statusFilter || x.run.status === s.statusFilter)
      .filter((x) => !s.view || (x.ms >= s.view[0] && x.ms <= s.view[1]));
  }

  _reason(run) {
    const why = run.blocked_by || run.uncertain_because;
    return why ? `${why.condition}: ${why.detail}` : "";
  }

  _runList(r) {
    const t = this._t;
    const s = this._s;
    const rows = this._visibleRuns(r);
    if (!rows.length) return `<div class="empty">${esc(t.nothingInView)}</div>`;
    const page = rows.slice(0, s.listLimit);
    return `<table><tbody>${page
      .map(
        ({ run, idx, ms }) => `<tr data-run="${idx}" class="${idx === s.selected ? "sel" : ""}">
          <td><span class="dot ${run.status}" title="${esc(t.status[run.status])}">${ICON[run.status]}</span></td>
          <td class="time">${esc(this._fmtFull(ms))}</td>
          <td class="desc">${esc(run.trigger.description)}${run.status !== "executed" ? `<div class="why">${esc(this._reason(run))}</div>` : ""}</td>
        </tr>`
      )
      .join("")}</tbody></table>
      ${rows.length > page.length ? `<button class="flat more">${esc(t.showMore)} (${page.length} ${esc(t.of)} ${rows.length})</button>` : ""}`;
  }

  _detail(r) {
    const t = this._t;
    const run = r.runs[this._s.selected];
    if (!run) return `<div class="empty">${esc(t.pickRun)}</div>`;
    const ms = Date.parse(run.time);
    const key = run.blocked_by?.path || run.uncertain_because?.path;
    const conds = run.conditions.length
      ? run.conditions
          .map((c) => {
            const depth = c.path.split("/").length - 2;
            const st = c.result === true ? "executed" : c.result === false ? "blocked" : "uncertain";
            return `<li class="${c.path === key ? "key" : ""}" style="margin-left:${Math.max(0, depth) * 14}px">
              <span class="dot ${st}">${ICON[st]}</span>
              <code>${esc(c.condition)}</code> <span class="muted">${esc(c.detail)}</span></li>`;
          })
          .join("")
      : `<li class="muted">${esc(t.noConditions)}</li>`;
    return `<div class="det-head">
        <span class="dot big ${run.status}">${ICON[run.status]}</span>
        <div><div class="det-status">${esc(t.status[run.status])}</div>
        <div class="muted">${esc(this._fmtFull(ms))}</div></div>
        <button class="flat centre" data-ms="${ms}">${esc(t.centre)}</button>
      </div>
      <h3>${esc(t.trigger)}</h3>
      <p><code>${esc(run.trigger.platform)}</code> · id <code>${esc(run.trigger.id)}</code><br>${esc(run.trigger.description)}</p>
      ${run.blocked_by ? `<p class="reason blocked"><b>${esc(t.blockedBy)}</b> ${esc(run.blocked_by.condition)} — ${esc(run.blocked_by.detail)}</p>` : ""}
      ${run.uncertain_because ? `<p class="reason uncertain"><b>${esc(t.uncertainBecause)}</b> ${esc(run.uncertain_because.detail)}</p>` : ""}
      <h3>${esc(t.conditions)}</h3><ul class="trace">${conds}</ul>`;
  }

  _compareTab() {
    const t = this._t;
    const s = this._s;
    if (!s.automation) return `<div class="card empty">${esc(t.selectFirst)}</div>`;
    if (s.automation === NEW) return `<div class="card empty">${esc(t.compareNeedsSaved)}</div>`;
    let html = `<div class="ab">
      <div class="card"><h3>${esc(t.versionA)}</h3><textarea class="code" readonly>${esc(s.saved?.yaml || "")}</textarea></div>
      ${this._draftEditor(true)}
    </div>`;
    const c = s.cmp;
    if (!c) return html;
    const d = c.diff.summary;
    html += `<div class="chips">
      <span class="chip plain">A <b>${d.a_executed}</b> · B <b>${d.b_executed}</b></span>
      <span class="chip plain"><b>${d.both}</b> ${esc(t.both)}</span>
      <span class="chip only-a"><b>${d.only_a}</b> ${esc(t.onlyA)}</span>
      <span class="chip only-b"><b>${d.only_b}</b> ${esc(t.onlyB)}</span>
      ${d.shifted ? `<span class="chip shifted"><b>${d.shifted}</b> ${esc(t.shifted)}</span>` : ""}
    </div>`;
    html += this._notices(c.a) + this._notices(c.b);
    html += `<div class="card chart-card">
      <div class="row between"><span class="hint">${esc(t.zoomHint)}</span>
      ${s.view ? `<button class="flat reset-zoom">${esc(t.resetZoom)}</button>` : ""}</div>
      <div class="chart"></div></div>`;
    if (!d.only_a && !d.only_b && !d.shifted) {
      html += `<div class="card empty">${esc(t.noDiff)}</div>`;
    } else {
      const list = (items, cls) =>
        items.length
          ? `<table><tbody>${items
              .map((x) => `<tr><td><span class="dot ${cls}">●</span></td><td class="time">${esc(this._fmtFull(Date.parse(x.time)))}</td><td class="desc">${esc(x.trigger)}</td></tr>`)
              .join("")}</tbody></table>`
          : `<div class="empty">—</div>`;
      if (c.diff.shifted?.length) {
        const fmtDelta = (sec) => {
          const a = Math.abs(sec);
          const txt = a >= 3600 ? `${Math.floor(a / 3600)} h ${Math.round((a % 3600) / 60)} min` : a >= 60 ? `${Math.round(a / 60)} min` : `${a} s`;
          return `${txt} ${sec < 0 ? t.earlier : t.later}`;
        };
        html += `<div class="card list"><h3>${esc(t.shifted)} <span class="muted hint">· ${esc(t.shiftedHint)}</span></h3><table><tbody>${c.diff.shifted
          .map((x) => `<tr><td><span class="dot shifted">↔</span></td>
            <td class="time">A ${esc(this._fmtFull(Date.parse(x.a_time)))}<br>B ${esc(this._fmtFull(Date.parse(x.b_time)))}</td>
            <td class="desc">${esc(x.trigger)}<div class="why">B ${esc(fmtDelta(x.delta_seconds))}</div></td></tr>`)
          .join("")}</tbody></table></div>`;
      }
      if (d.only_a || d.only_b) {
        html += `<div class="split"><div class="card list"><h3>${esc(t.onlyA)}</h3>${list(c.diff.only_a, "only-a")}</div>
          <div class="card list"><h3>${esc(t.onlyB)}</h3>${list(c.diff.only_b, "only-b")}</div></div>`;
      }
    }
    return html;
  }

  // --- chart -----------------------------------------------------------------

  _renderChartOnly() {
    const host = this.shadowRoot?.querySelector(".chart");
    if (!host) return;
    const s = this._s;
    const t = this._t;
    let data;
    if (s.tab === "run" && s.result) {
      data = {
        period: s.result.period,
        lanes: [{ label: t.tabRun, runs: s.result.runs, key: "run" }],
        entities: s.result.entities,
        thresholds: s.result.thresholds,
        restarts: s.result.restarts || [],
      };
    } else if (s.tab === "compare" && s.cmp) {
      const onlyA = new Set(s.cmp.diff.only_a.map((x) => Date.parse(x.time)));
      const onlyB = new Set(s.cmp.diff.only_b.map((x) => Date.parse(x.time)));
      data = {
        period: s.cmp.a.period,
        lanes: [
          { label: "A", runs: s.cmp.a.runs, key: "a", highlight: onlyA },
          { label: "B", runs: s.cmp.b.runs, key: "b", highlight: onlyB },
        ],
        entities: s.cmp.entities,
        thresholds: s.cmp.thresholds,
        restarts: s.cmp.a.restarts || [],
      };
    } else {
      host.innerHTML = "";
      return;
    }
    host.innerHTML = this._chartSvg(data, host.clientWidth || 900);
  }

  _chartSvg(data, width) {
    const s = this._s;
    const t = this._t;
    const full = [Date.parse(data.period.start), Date.parse(data.period.end)];
    const [t0, t1] = s.view || full;
    const left = this._narrow ? 92 : 170;
    const right = 12;
    const plotW = Math.max(120, width - left - right);
    const x = (ms) => left + ((ms - t0) / (t1 - t0)) * plotW;
    this._chartGeom = { left, plotW, t0, t1 };

    const parts = [];
    let y = 8;
    const laneTops = [];

    // run marker lanes
    for (const lane of data.lanes) {
      const h = 28;
      const cy = y + h / 2;
      laneTops.push(y);
      parts.push(`<text x="${left - 8}" y="${cy + 4}" class="lbl" text-anchor="end">${esc(lane.label)}</text>`);
      parts.push(`<line x1="${left}" x2="${left + plotW}" y1="${cy}" y2="${cy}" class="laneline"/>`);
      lane.runs.forEach((run, idx) => {
        const ms = Date.parse(run.time);
        if (ms < t0 || ms > t1) return;
        if (s.statusFilter && lane.key === "run" && run.status !== s.statusFilter) return;
        const cx = x(ms);
        const sel = lane.key === "run" && idx === s.selected;
        const hl = lane.highlight?.has(ms);
        const tip = `${t.status[run.status]} · ${this._fmtFull(ms)}\n${run.trigger.description}${this._reason(run) ? "\n" + this._reason(run) : ""}`;
        const cls = `mk ${run.status}${sel ? " sel" : ""}`;
        const data = lane.key === "run" ? ` data-run="${idx}"` : "";
        let shape;
        if (run.status === "executed") shape = `<circle cx="${cx}" cy="${cy}" r="5.5" class="${cls}"${data}/>`;
        else if (run.status === "blocked") shape = `<rect x="${cx - 5}" y="${cy - 5}" width="10" height="10" class="${cls}"${data}/>`;
        else shape = `<path d="M${cx} ${cy - 6}L${cx + 6} ${cy}L${cx} ${cy + 6}L${cx - 6} ${cy}Z" class="${cls}"${data}/>`;
        if (hl) parts.push(`<circle cx="${cx}" cy="${cy}" r="9.5" class="ring ${lane.key}"/>`);
        parts.push(`<g>${shape}<title>${esc(tip)}</title></g>`);
      });
      y += h + 4;
    }

    // entity lanes
    const entities = (data.entities || []).filter((e) => this._s.history[e]).slice(0, MAX_ENTITY_LANES);
    for (const entityId of entities) {
      const series = this._s.history[entityId];
      const name = this._hass.states[entityId]?.attributes?.friendly_name || entityId;
      const nums = series.map((p) => Number(p.s));
      const numericShare = nums.filter((n) => Number.isFinite(n)).length / Math.max(1, series.length);
      const thresholds = (data.thresholds || []).filter((th) => th.entity_id === entityId);
      const short = name.length > (this._narrow ? 12 : 24) ? name.slice(0, this._narrow ? 11 : 23) + "…" : name;
      if (numericShare >= 0.8) {
        const h = 58;
        const vals = nums.filter(Number.isFinite).concat(thresholds.map((th) => th.value));
        let lo = Math.min(...vals);
        let hi = Math.max(...vals);
        if (lo === hi) { lo -= 1; hi += 1; }
        const dataMin = lo;
        const pad = (hi - lo) * 0.08;
        lo -= pad; hi += pad;
        if (dataMin >= 0 && lo < 0) lo = 0;
        const yy = (v) => y + h - ((v - lo) / (hi - lo)) * h;
        let d = "";
        let prev = null;
        series.forEach((p, i) => {
          const v = Number(p.s);
          const next = series[i + 1];
          const a = Math.max(p.t, t0);
          const b = Math.min(next ? next.t : t1, t1);
          if (b < t0 || a > t1 || !Number.isFinite(v)) { prev = null; return; }
          const py = yy(v).toFixed(1);
          d += prev === null ? `M${x(a).toFixed(1)} ${py}` : `L${x(a).toFixed(1)} ${py}`;
          d += `L${x(b).toFixed(1)} ${py}`;
          prev = v;
        });
        parts.push(`<rect x="${left}" y="${y}" width="${plotW}" height="${h}" class="laneBg"/>`);
        parts.push(`<path d="${d}" class="series"/>`);
        thresholds.forEach((th, i) => {
          const ty = yy(th.value).toFixed(1);
          parts.push(`<line x1="${left}" x2="${left + plotW}" y1="${ty}" y2="${ty}" class="thr"/>`);
          parts.push(`<text x="${left + plotW - 4 - i * 48}" y="${Number(ty) - 3}" class="thrlbl" text-anchor="end">${th.kind === "above" ? ">" : "<"} ${th.value}</text>`);
        });
        parts.push(`<text x="${left - 8}" y="${y + h / 2 + 4}" class="lbl" text-anchor="end"><title>${esc(entityId)}</title>${esc(short)}</text>`);
        parts.push(`<text x="${left - 8}" y="${y + 9}" class="tick" text-anchor="end">${+hi.toFixed(1)}</text>`);
        parts.push(`<text x="${left - 8}" y="${y + h}" class="tick" text-anchor="end">${+lo.toFixed(1)}</text>`);
        y += h + 8;
      } else {
        const h = 18;
        series.forEach((p, i) => {
          const next = series[i + 1];
          const a = Math.max(p.t, t0);
          const b = Math.min(next ? next.t : t1, t1);
          if (b <= a) return;
          const w = x(b) - x(a);
          const fill = stateColor(p.s);
          parts.push(`<rect x="${x(a).toFixed(1)}" y="${y}" width="${Math.max(0.5, w).toFixed(1)}" height="${h}" fill="${fill}" class="band"><title>${esc(name)}: ${esc(p.s)}\n${esc(this._fmtFull(p.t))}</title></rect>`);
          if (w > 46) parts.push(`<text x="${(x(a) + 4).toFixed(1)}" y="${y + 13}" class="bandtxt">${esc(String(p.s).slice(0, Math.floor(w / 7)))}</text>`);
        });
        parts.push(`<text x="${left - 8}" y="${y + 13}" class="lbl" text-anchor="end"><title>${esc(entityId)}</title>${esc(short)}</text>`);
        y += h + 8;
      }
    }

    const bottom = y;
    // restarts
    const bands = (data.restarts || []).map((r) => {
      const a = Math.max(Date.parse(r.stopped), t0);
      const b = Math.min(Date.parse(r.started), t1);
      if (b <= a) return "";
      return `<rect x="${x(a)}" y="4" width="${Math.max(3, x(b) - x(a))}" height="${bottom - 4}" class="restart"><title>${esc(t.restartBand)}\n${esc(this._fmtFull(Date.parse(r.stopped)))} → ${esc(this._fmtFull(Date.parse(r.started)))}</title></rect>`;
    });

    // axis
    const span = t1 - t0;
    const H = 3600e3;
    const steps = [5 * 60e3, 15 * 60e3, H, 3 * H, 6 * H, 12 * H, 24 * H, 48 * H, 7 * 24 * H];
    const step = steps.find((st) => span / st <= Math.max(3, plotW / 110)) || steps[steps.length - 1];
    const ticks = [];
    // align ticks to the HA timezone by using the offset of t0
    const offset = this._tzOffset(t0);
    let tk = Math.ceil((t0 + offset) / step) * step - offset;
    for (; tk <= t1; tk += step) {
      const tx = x(tk);
      const label = step >= 24 * H
        ? this._fmt(tk, { weekday: "short", day: "2-digit", month: "2-digit" })
        : this._fmt(tk, step >= 12 * H ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" });
      ticks.push(`<line x1="${tx}" x2="${tx}" y1="4" y2="${bottom}" class="grid"/><text x="${tx}" y="${bottom + 16}" class="tick" text-anchor="middle">${esc(label)}</text>`);
    }

    // selected run cursor
    let cursor = "";
    const selRun = this._s.tab === "run" && this._s.result?.runs[this._s.selected];
    if (selRun) {
      const ms = Date.parse(selRun.time);
      if (ms >= t0 && ms <= t1) cursor = `<line x1="${x(ms)}" x2="${x(ms)}" y1="4" y2="${bottom}" class="cursor"/>`;
    }

    const height = bottom + 26;
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
      ${ticks.join("")}${bands.join("")}${parts.join("")}${cursor}
      <rect class="brush" x="0" y="0" width="0" height="${bottom}" visibility="hidden"/>
    </svg>`;
  }

  _tzOffset(ms) {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: this._tz, hour12: false, year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }).formatToParts(ms);
      const get = (k) => Number(parts.find((p) => p.type === k).value);
      const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second"));
      return asUtc - (ms - (ms % 1000));
    } catch (_e) {
      return 0;
    }
  }

  _bindDrag() {
    const root = this.shadowRoot;
    root.addEventListener("mousedown", (e) => {
      const svg = e.target.closest?.(".chart svg");
      if (!svg || e.button !== 0 || e.target.dataset?.run) return;
      const box = svg.getBoundingClientRect();
      const g = this._chartGeom;
      const px = e.clientX - box.left;
      if (!g || px < g.left) return;
      this._drag = { svg, box, x0: px, x1: px };
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!this._drag) return;
      const d = this._drag;
      const g = this._chartGeom;
      d.x1 = Math.min(Math.max(e.clientX - d.box.left, g.left), g.left + g.plotW);
      const brush = d.svg.querySelector(".brush");
      brush.setAttribute("visibility", "visible");
      brush.setAttribute("x", Math.min(d.x0, d.x1));
      brush.setAttribute("width", Math.abs(d.x1 - d.x0));
    });
    window.addEventListener("mouseup", () => {
      if (!this._drag) return;
      const d = this._drag;
      this._drag = null;
      const g = this._chartGeom;
      if (Math.abs(d.x1 - d.x0) < 6) {
        d.svg.querySelector(".brush")?.setAttribute("visibility", "hidden");
        return;
      }
      const toMs = (px) => g.t0 + ((px - g.left) / g.plotW) * (g.t1 - g.t0);
      const a = toMs(Math.min(d.x0, d.x1));
      const b = toMs(Math.max(d.x0, d.x1));
      if (b - a > 60e3) this._setView([a, b]);
    });
  }

  _setView(view) {
    this._s.view = view;
    this._s.listLimit = LIST_PAGE;
    this._renderBody();
  }

  // --- events ------------------------------------------------------------------

  _onClick(e) {
    const el = e.target.closest("button, [data-run], .mk");
    if (!el) return;
    const s = this._s;
    if (el.dataset.days) {
      s.custom = false;
      s.days = Number(el.dataset.days);
      this._renderControls();
    } else if (el.dataset.custom) {
      s.custom = true;
      if (!s.start) {
        const now = Date.now();
        s.end = this._localInput(now);
        s.start = this._localInput(now - s.days * 86400e3);
      }
      this._renderControls();
    } else if (el.dataset.tab) {
      s.tab = el.dataset.tab;
      s.view = null;
      s.error = "";
      if (s.tab === "compare" && s.automation && s.automation !== NEW) s.editing = true;
      this._renderAll();
    } else if (el.classList.contains("go")) {
      s.tab === "run" ? this._runBacktest() : this._runCompare();
    } else if (el.dataset.filter) {
      s.statusFilter = s.statusFilter === el.dataset.filter ? null : el.dataset.filter;
      s.listLimit = LIST_PAGE;
      this._renderBody();
    } else if (el.dataset.run !== undefined) {
      s.selected = Number(el.dataset.run);
      this._renderBody();
      this.shadowRoot.querySelector(".detail")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else if (el.classList.contains("more")) {
      s.listLimit += LIST_PAGE;
      this._renderBody();
    } else if (el.classList.contains("reset-zoom")) {
      this._setView(null);
    } else if (el.classList.contains("centre")) {
      const ms = Number(el.dataset.ms);
      this._setView([ms - 3600e3, ms + 3600e3]);
    } else if (el.dataset.mode) {
      this._switchMode(el.dataset.mode);
    } else if (el.classList.contains("reset-draft")) {
      this._resetDraft();
      this._renderBody();
    }
  }

  _onInput(e) {
    const s = this._s;
    const el = e.target;
    if (el.classList.contains("filter")) {
      s.filter = el.value;
      const pos = el.selectionStart;
      this._renderControls();
      const again = this.shadowRoot.querySelector(".filter");
      again.focus();
      again.setSelectionRange(pos, pos);
    } else if (el.classList.contains("yaml-a")) {
      s.yaml = el.value;
      this._markDirty();
    }
  }

  _onChange(e) {
    const s = this._s;
    const el = e.target;
    if (el.classList.contains("auto")) {
      s.automation = el.value;
      s.result = null;
      s.cmp = null;
      s.selected = -1;
      s.view = null;
      s.saved = null;
      s.editing = false;
      s.draft = null;
      s.yaml = "";
      s.dirty = false;
      s.fromEditor = false;
      s.error = "";
      const url = new URL(window.location.href);
      url.searchParams.delete("draft");
      if (s.automation && s.automation !== NEW) url.searchParams.set("automation", s.automation);
      else url.searchParams.delete("automation");
      window.history.replaceState(window.history.state, "", url);
      if (s.automation === NEW) {
        s.editing = true;
        s.draft = { triggers: [], conditions: [] };
        s.yaml = TEMPLATE;
        if (s.tab === "compare") s.tab = "run";
      }
      this._renderAll();
      if (s.automation && s.automation !== NEW) this._loadSaved();
    } else if (el.classList.contains("start")) {
      s.start = el.value;
    } else if (el.classList.contains("end")) {
      s.end = el.value;
    } else if (el.classList.contains("draft-toggle")) {
      s.editing = el.checked;
      this._renderBody();
    }
  }

  _localInput(ms) {
    // yyyy-MM-ddTHH:mm in the HA timezone, for <input type=datetime-local>
    const p = new Intl.DateTimeFormat("en-CA", {
      timeZone: this._tz, hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).formatToParts(ms);
    const g = (k) => p.find((x) => x.type === k).value;
    return `${g("year")}-${g("month")}-${g("day")}T${g("hour") === "24" ? "00" : g("hour")}:${g("minute")}`;
  }

  // --- data ----------------------------------------------------------------------

  _periodMsg() {
    const s = this._s;
    if (s.custom && s.start && s.end) return { start: s.start, end: s.end };
    return { days: s.days };
  }

  async _loadDraft(automation) {
    const s = this._s;
    let config = null;
    try {
      config = JSON.parse(window.sessionStorage.getItem(DRAFT_KEY) || "null");
      window.sessionStorage.removeItem(DRAFT_KEY);
    } catch (_e) {
      config = null;
    }
    s.automation = automation || NEW;
    this._renderAll();
    try {
      if (automation) await this._loadSaved();
      if (config) {
        const draft = normalise(config);
        const yaml = (await this._ws({ type: "automation_backtest/to_yaml", config: draft })).yaml;
        const changed = !automation || yaml !== s.saved?.yaml;
        s.draft = draft;
        s.yaml = yaml;
        s.editing = changed;
        s.dirty = changed;
        s.fromEditor = changed && !!automation;
      } else if (!automation) {
        s.editing = true;
        s.draft = { triggers: [], conditions: [] };
        s.yaml = TEMPLATE;
      }
    } catch (err) {
      s.error = err?.message || String(err);
    }
    this._renderAll();
    if (config) this._runBacktest();
  }

  async _loadSaved() {
    const s = this._s;
    if (!s.automation || s.automation === NEW) return;
    try {
      const res = await this._ws({ type: "automation_backtest/config", automation: s.automation });
      s.saved = { yaml: res.yaml, config: res.config, id: res.id };
      if (!s.dirty) this._resetDraft();
    } catch (err) {
      s.error = err?.message || String(err);
    }
    this._renderBody();
  }

  _resetDraft() {
    const s = this._s;
    if (!s.saved) return;
    s.draft = JSON.parse(JSON.stringify(s.saved.config));
    s.yaml = s.saved.yaml;
    s.dirty = false;
    s.fromEditor = false;
    if (this._vis) {
      this._vis.tr.triggers = s.draft.triggers;
      this._vis.co.conditions = s.draft.conditions;
    }
    if (this._code) this._code.value = s.yaml;
  }

  _markDirty() {
    const s = this._s;
    s.dirty = true;
    const badge = this.shadowRoot.querySelector(".dirty-badge");
    if (badge && s.automation !== NEW) badge.hidden = false;
  }

  /** What the backend should replay as "the draft". */
  _draftPayload(objKey, yamlKey) {
    const s = this._s;
    if (s.mode === "yaml") return { [yamlKey]: s.yaml };
    return { [objKey]: s.draft || { triggers: [], conditions: [] } };
  }

  async _switchMode(mode) {
    const s = this._s;
    if (mode === s.mode) return;
    try {
      if (mode === "yaml") {
        s.yaml = (await this._ws({ type: "automation_backtest/to_yaml", config: s.draft || {} })).yaml || TEMPLATE;
        if (this._code) this._code.value = s.yaml;
      } else {
        const res = await this._ws({ type: "automation_backtest/from_yaml", yaml: s.yaml });
        s.draft = res.config;
        if (this._vis) {
          this._vis.tr.triggers = s.draft.triggers;
          this._vis.co.conditions = s.draft.conditions;
        }
      }
      s.mode = mode;
      s.error = "";
    } catch (err) {
      s.error = err?.message || String(err);
    }
    this._renderBody();
  }

  // --- the editor itself (HA's own blocks when available, else YAML) ------------

  async _ensureVisual() {
    if (this._visualPromise) return this._visualPromise;
    this._visualPromise = (async () => {
      const ready = () => customElements.get("ha-automation-trigger") && customElements.get("ha-automation-condition");
      try {
        if (!ready()) {
          // Ask HA to load Settings → Automations (without opening it): it defines the editor blocks.
          const resolver = findDeep(document, "partial-panel-resolver");
          await resolver?.routerOptions?.routes?.config?.load?.();
          const cfgPanel = document.createElement("ha-panel-config");
          await cfgPanel.routerOptions?.routes?.automation?.load?.();
          await Promise.race([
            Promise.all([customElements.whenDefined("ha-automation-trigger"), customElements.whenDefined("ha-automation-condition")]),
            new Promise((r) => setTimeout(r, 8000)),
          ]);
        }
        await this._hass.loadFragmentTranslation?.("config");
      } catch (_e) {
        /* fall back to YAML */
      }
      return !!ready();
    })();
    return this._visualPromise;
  }

  _buildVisual() {
    if (this._vis) return this._vis;
    const t = this._t;
    const wrap = document.createElement("div");
    wrap.className = "visual";
    const h1 = document.createElement("h4");
    h1.textContent = t.when;
    const h2 = document.createElement("h4");
    h2.textContent = t.andIf;
    const tr = document.createElement("ha-automation-trigger");
    const co = document.createElement("ha-automation-condition");
    for (const el of [tr, co]) {
      el.hass = this._hass;
      el.narrow = !!this._narrow;
    }
    tr.addEventListener("value-changed", (e) => {
      e.stopPropagation();
      this._s.draft = { ...(this._s.draft || {}), triggers: e.detail.value };
      tr.triggers = e.detail.value;
      this._markDirty();
    });
    co.addEventListener("value-changed", (e) => {
      e.stopPropagation();
      this._s.draft = { ...(this._s.draft || {}), conditions: e.detail.value };
      co.conditions = e.detail.value;
      this._markDirty();
    });
    wrap.append(h1, tr, h2, co);
    this._vis = { wrap, tr, co };
    return this._vis;
  }

  _buildCode() {
    if (this._code) return this._code;
    let code;
    if (customElements.get("ha-code-editor")) {
      code = document.createElement("ha-code-editor");
      code.mode = "yaml";
      code.hass = this._hass;
      code.autocompleteEntities = true;
      code.addEventListener("value-changed", (e) => {
        e.stopPropagation();
        this._s.yaml = e.detail.value;
        this._markDirty();
      });
    } else {
      code = document.createElement("textarea");
      code.className = "code yaml-a";
      code.spellcheck = false;
    }
    code.classList.add("yaml-editor");
    this._code = code;
    return code;
  }

  async _mountEditor() {
    const slot = this.shadowRoot.querySelector(".ve-slot");
    if (!slot) return;
    const s = this._s;
    if (s.mode === "visual") {
      if (s.visualOk === null) s.visualOk = await this._ensureVisual();
      if (!s.visualOk) {
        s.mode = "yaml";
        if (s.draft) {
          try {
            s.yaml = (await this._ws({ type: "automation_backtest/to_yaml", config: s.draft })).yaml || s.yaml;
          } catch (_e) {
            /* keep the current yaml */
          }
        }
        this._renderBody();
        return;
      }
      const vis = this._buildVisual();
      const draft = s.draft || { triggers: [], conditions: [] };
      if (vis.tr.triggers !== draft.triggers) vis.tr.triggers = draft.triggers;
      if (vis.co.conditions !== draft.conditions) vis.co.conditions = draft.conditions;
      const current = this.shadowRoot.querySelector(".ve-slot");
      if (current) current.replaceChildren(vis.wrap);
    } else {
      const code = this._buildCode();
      code.value = s.yaml;
      slot.replaceChildren(code);
    }
  }

  async _loadHistory(entities, period) {
    const wanted = entities.slice(0, MAX_ENTITY_LANES);
    if (!wanted.length) return {};
    try {
      const res = await this._ws({
        type: "history/history_during_period",
        start_time: period.start,
        end_time: period.end,
        entity_ids: wanted,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      const out = {};
      for (const [entityId, rows] of Object.entries(res || {})) {
        out[entityId] = rows
          .map((r) => ({ s: r.s, t: (r.lu ?? r.lc) * 1000 }))
          .filter((r) => Number.isFinite(r.t))
          .sort((a, b) => a.t - b.t);
      }
      return out;
    } catch (_err) {
      return {};
    }
  }

  async _runBacktest() {
    const s = this._s;
    if (!s.automation) {
      s.error = this._t.selectFirst;
      this._renderBody();
      return;
    }
    s.loading = true;
    s.error = "";
    s.view = null;
    s.selected = -1;
    s.statusFilter = null;
    this._renderControls();
    this._renderBody();
    try {
      const msg = { type: "automation_backtest/run", ...this._periodMsg() };
      if (s.automation === NEW || (s.editing && s.dirty)) Object.assign(msg, this._draftPayload("config", "config_yaml"));
      else msg.automation = s.automation;
      const result = await this._ws(msg);
      s.history = await this._loadHistory(result.entities, result.period);
      s.result = result;
      s.selected = result.runs.findIndex((r) => r.status !== "executed");
    } catch (err) {
      s.error = err?.message || String(err);
    }
    s.loading = false;
    this._renderControls();
    this._renderBody();
  }

  async _runCompare() {
    const s = this._s;
    if (!s.automation || s.automation === NEW) {
      s.error = s.automation === NEW ? this._t.compareNeedsSaved : this._t.selectFirst;
      this._renderBody();
      return;
    }
    s.loading = true;
    s.error = "";
    s.view = null;
    this._renderControls();
    this._renderBody();
    try {
      const cmp = await this._ws({
        type: "automation_backtest/compare",
        automation: s.automation,
        ...this._draftPayload("config_b", "config_b_yaml"),
        ...this._periodMsg(),
      });
      s.history = await this._loadHistory(cmp.entities, cmp.a.period);
      s.cmp = cmp;
    } catch (err) {
      s.error = err?.message || String(err);
    }
    s.loading = false;
    this._renderControls();
    this._renderBody();
  }
}

const STYLE = `
:host{display:block;height:100%;min-height:100vh;color:var(--fg);-webkit-tap-highlight-color:transparent;font-size:14px;line-height:1.4;
  font-family:var(--ha-font-family-body,var(--paper-font-body1_-_font-family,Roboto,system-ui,sans-serif));
  --acc:#f6a23a;--acc2:#ea863c;--accbg:linear-gradient(145deg,rgba(246,162,58,.14),rgba(246,162,58,.04));--accbd:1.5px solid rgba(246,162,58,.65);
  --fg:#fff;--fgr:255,255,255;--acct:#f6a23a;
  --sh:0 14px 34px rgba(0,0,0,.30);
  --bg:radial-gradient(160% 70% at 0% 15%,rgba(112,76,36,.36),transparent 62%),radial-gradient(170% 65% at 100% 100%,rgba(28,50,110,.34),transparent 65%),#0c0f15;
  --panel:rgb(23,27,36);--tile:rgba(var(--fgr),.04);--bd:1px solid rgba(var(--fgr),.07);--line:rgba(var(--fgr),.07);
  --t2:rgba(var(--fgr),.55);--t3:rgba(var(--fgr),.45);--in:#4cd08a;--out:#ff7a6b;--unc:#a78bfa;--r:24px;color-scheme:dark}
:host([theme="light"]){--fg:#171b24;--fgr:23,27,36;--acct:#b9650d;
  --sh:0 8px 24px rgba(23,27,36,.08);
  --bg:radial-gradient(160% 70% at 0% 15%,rgba(246,162,58,.20),transparent 62%),radial-gradient(170% 65% at 100% 100%,rgba(80,120,210,.16),transparent 65%),#f3f1ed;
  --panel:#fff;--tile:rgba(23,27,36,.035);--bd:1px solid rgba(23,27,36,.08);--line:rgba(23,27,36,.08);
  --t2:rgba(23,27,36,.58);--t3:rgba(23,27,36,.45);--in:#1c9a56;--out:#d6402f;--unc:#7c5cd6;
  --accbg:linear-gradient(145deg,rgba(246,162,58,.20),rgba(246,162,58,.07));--accbd:1.5px solid rgba(214,128,30,.7);color-scheme:light}
*{box-sizing:border-box}
[hidden]{display:none!important}
.root{display:flex;flex-direction:column;min-height:100vh;background:var(--bg)}
header{display:flex;align-items:center;gap:8px;padding:12px 16px 4px}
header .tt{flex:1;min-width:0}
h1.logo{display:flex;align-items:center;gap:9px;font-size:22px;font-weight:800;letter-spacing:-.3px;margin:0}
h1.logo b{font-weight:800;color:var(--acc2)}
.logo-ic{width:30px;height:30px;flex:none}
.who{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--t2);margin-top:3px}
.ib{background:rgba(var(--fgr),.06);border:var(--bd);color:rgba(var(--fgr),.88);width:42px;height:42px;border-radius:50%;display:none;place-items:center;cursor:pointer;padding:0;flex:none}
.ib svg{width:22px;height:22px;fill:currentColor}
.narrow .ib{display:grid}
main{padding:10px 16px 40px;max-width:1400px;width:100%;margin:0 auto}
.card{background:var(--panel);border:var(--bd);border-radius:var(--r);box-shadow:var(--sh);padding:14px 16px;margin-bottom:14px}
.controls{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:flex-end}
.field{display:flex;flex-direction:column;gap:7px;min-width:0}
.field.grow{flex:1 1 340px}
.field>label{font-size:11px;color:var(--t2);text-transform:uppercase;letter-spacing:.14em;font-weight:700}
.pick{display:flex;gap:8px}
.pick .filter{flex:0 0 150px}
.pick select{flex:1;min-width:0;width:100%}
.narrow .pick{flex-direction:column} .narrow .pick .filter{flex:none}
input,select,textarea{font:inherit;font-size:14px;color:var(--fg);background:rgba(var(--fgr),.05);border:1px solid rgba(var(--fgr),.08);border-radius:14px;padding:10px 13px;outline:none}
input:focus,select:focus,textarea:focus{border-color:rgba(246,162,58,.6)}
input::placeholder{color:rgba(var(--fgr),.35)}
select{-webkit-appearance:none;appearance:none;padding-right:32px;
  background-image:linear-gradient(45deg,transparent 50%,rgba(var(--fgr),.6) 50%),linear-gradient(135deg,rgba(var(--fgr),.6) 50%,transparent 50%);
  background-position:calc(100% - 18px) 50%,calc(100% - 13px) 50%;background-size:5px 5px;background-repeat:no-repeat}
option{background:var(--panel);color:var(--fg)}
.range{display:flex;gap:8px;flex-wrap:wrap}
.range label{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--t2)}
.link{font-size:12px;color:var(--acct);text-decoration:none;font-weight:600}
.seg{display:flex;background:rgba(var(--fgr),.04);border:var(--bd);border-radius:16px;padding:4px;gap:4px;flex-wrap:wrap}
.seg button{border:0;background:none;color:rgba(var(--fgr),.62);font:inherit;font-size:13px;font-weight:700;padding:7px 12px;border-radius:12px;cursor:pointer}
.seg button.on{background:linear-gradient(90deg,var(--acc),var(--acc2));color:#2b1904}
button.primary{border:0;border-radius:16px;padding:11px 20px;font:inherit;font-weight:700;font-size:14px;cursor:pointer;
  background:linear-gradient(90deg,var(--acc),var(--acc2));color:#2b1904;box-shadow:0 6px 18px rgba(246,162,58,.25)}
button.primary[disabled]{opacity:.5;cursor:default}
button.flat{background:none;border:0;color:var(--acct);font:inherit;font-weight:700;font-size:13px;cursor:pointer;padding:6px 8px}
.tabs{display:flex;gap:8px;margin:2px 0 14px}
.tabs button,.chip{border:var(--bd);background:var(--tile);color:rgba(var(--fgr),.88);border-radius:99px;padding:7px 14px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.tabs button.on,.chip.on{background:var(--accbg);border:var(--accbd);color:var(--acct)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.chip.plain{cursor:default}
.chip b{font-weight:800}
.chip.executed b{color:var(--in)} .chip.blocked b{color:var(--out)} .chip.uncertain b{color:var(--unc)}
.chip.only-a b{color:var(--acc2)} .chip.only-b b{color:#5b8def} .chip.shifted b{color:var(--acct)} .chip.restart b{color:var(--t2)}
.banner{border-radius:16px;padding:10px 14px;margin-bottom:14px;font-size:13px;line-height:1.45;border:var(--bd);background:var(--tile)}
.banner.error{color:var(--out);border-color:rgba(255,122,107,.35)}
.banner.warn{background:var(--accbg);border:var(--accbd)}
.badge.warn{display:inline-block;background:var(--accbg);border:var(--accbd);color:var(--acct);border-radius:99px;padding:4px 11px;font-size:12px;font-weight:700;margin-bottom:8px}
.row{display:flex;gap:12px;align-items:center;margin-top:8px}
.row.between{justify-content:space-between;margin-top:0}
.hint{font-size:11px;color:var(--t3)}
.hint-p{margin:0 0 6px;font-size:13px}
.check{display:flex;gap:9px;align-items:center;cursor:pointer;font-weight:600}
.check input{accent-color:var(--acc2);width:16px;height:16px;padding:0}
.draft h3{margin:0 0 8px;font-size:15px}
.draft-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 8px}
.draft-bar .grow{flex:1}
.draft-bar .badge{margin:0}
.seg.small{padding:3px;border-radius:13px}
.seg.small button{padding:5px 12px;font-size:12px;border-radius:10px}
.visual h4{margin:12px 2px 6px;font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:var(--t2);font-weight:700}
.visual h4:first-child{margin-top:4px}
ha-code-editor.yaml-editor{display:block;border:var(--bd);border-radius:14px;overflow:hidden;--code-mirror-height:auto}
textarea.code{width:100%;min-height:200px;margin-top:10px;font-family:var(--code-font-family,ui-monospace,SFMono-Regular,Menlo,monospace);font-size:13px;line-height:1.5;resize:vertical}
.ab{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,3fr);gap:14px;align-items:start}
.ab h3{margin:0;font-size:15px}
.narrow .ab{grid-template-columns:1fr}
.chart-card{padding:12px 14px}
.chart{width:100%;overflow:hidden;user-select:none;margin-top:4px}
.chart svg{display:block}
.split{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:14px;align-items:start}
.narrow .split{grid-template-columns:1fr}
.list{max-height:560px;overflow:auto;padding:6px 10px}
.list h3{margin:8px 6px 6px;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13px}
tr[data-run]{cursor:pointer}
tr[data-run]:hover td{background:rgba(var(--fgr),.03)}
tr.sel td{background:rgba(246,162,58,.13)!important}
td{padding:9px 6px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.time{white-space:nowrap;color:var(--t2);font-variant-numeric:tabular-nums}
td.desc{word-break:break-word}
.narrow td.time{white-space:normal;width:72px;font-size:12px}
.narrow td.desc{overflow-wrap:anywhere}
.why{font-size:12px;color:var(--t2);margin-top:2px}
.dot{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:9px;font-size:12px;font-weight:800}
.dot.big{width:40px;height:40px;border-radius:14px;font-size:18px}
.dot.executed{background:color-mix(in srgb,var(--in) 18%,transparent);color:var(--in)}
.dot.blocked{background:color-mix(in srgb,var(--out) 18%,transparent);color:var(--out)}
.dot.uncertain{background:color-mix(in srgb,var(--unc) 18%,transparent);color:var(--unc)}
.dot.only-a{color:var(--acc2)} .dot.only-b{color:#5b8def}
.dot.shifted{background:var(--accbg);color:var(--acct)}
.detail{position:sticky;top:12px}
.det-head{display:flex;gap:12px;align-items:center}
.det-head .centre{margin-left:auto}
.det-status{font-weight:700;font-size:16px}
.detail h3{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:var(--t2);margin:16px 0 6px;font-weight:700}
.detail p{margin:4px 0;line-height:1.45}
.reason{padding:9px 12px;border-radius:14px;border:var(--bd)}
.reason.blocked{background:color-mix(in srgb,var(--out) 10%,transparent)}
.reason.uncertain{background:color-mix(in srgb,var(--unc) 10%,transparent)}
.trace{list-style:none;padding:0;margin:0}
.trace li{display:flex;gap:8px;align-items:flex-start;padding:6px;border-radius:12px;font-size:13px}
.trace li .dot{flex:0 0 24px}
.trace li.key{background:color-mix(in srgb,var(--out) 10%,transparent)}
.muted{color:var(--t2)}
code{font-family:var(--code-font-family,ui-monospace,monospace);font-size:12px;background:rgba(var(--fgr),.06);padding:1px 6px;border-radius:6px}
.empty{color:var(--t2);padding:10px 4px}
.loading{display:flex;gap:12px;align-items:center;justify-content:center;padding:24px;color:var(--t2)}
.spinner{width:20px;height:20px;border-radius:50%;border:3px solid rgba(var(--fgr),.1);border-top-color:var(--acc);animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
svg .lbl{font-size:12px;fill:var(--fg);opacity:.85}
svg .tick{font-size:11px;fill:var(--t2)}
svg .grid{stroke:var(--line);stroke-width:1}
svg .laneline{stroke:var(--line)}
svg .laneBg{fill:rgba(var(--fgr),.03)}
svg .series{fill:none;stroke:var(--acc);stroke-width:1.8}
svg .thr{stroke:var(--out);stroke-dasharray:5 4;stroke-width:1.2;opacity:.85}
svg .thrlbl{font-size:11px;fill:var(--out);font-weight:700}
svg .band{opacity:1}
svg .bandtxt{font-size:11px;fill:var(--fg);opacity:.8;pointer-events:none}
svg .restart{fill:rgba(var(--fgr),.10)}
svg .mk{cursor:pointer;stroke:var(--panel);stroke-width:1.5}
svg .mk.executed{fill:var(--in)} svg .mk.blocked{fill:var(--out)} svg .mk.uncertain{fill:var(--unc)}
svg .mk.sel{stroke:var(--fg);stroke-width:2.5}
svg .ring{fill:none;stroke-width:2} svg .ring.a{stroke:var(--acc2)} svg .ring.b{stroke:#5b8def}
svg .cursor{stroke:var(--fg);stroke-width:1;stroke-dasharray:3 3;opacity:.5}
svg .brush{fill:var(--acc);opacity:.15}
`;

customElements.define("automation-backtest-panel", AutomationBacktestPanel);
