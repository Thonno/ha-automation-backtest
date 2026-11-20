/*
 * Automation Backtest – sidebar panel.
 * Plain web component: no build step, no external dependencies.
 * Talks to the integration through the automation_backtest/* websocket commands
 * and to the recorder through history/history_during_period.
 */

const STR = {
  en: {
    title: "Automation Backtest",
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
    editYaml: "Edit YAML (test a draft)",
    resetYaml: "Reset to saved",
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
    noDiff: "No difference: both versions run at exactly the same moments.",
    restartBand: "Home Assistant was restarting: automations were not listening",
    dayShort: "d",
    selectFirst: "Choose an automation first.",
    nothingInView: "Nothing in this part of the chart.",
    status: { executed: "Executed", blocked: "Blocked", uncertain: "Uncertain" },
  },
  it: {
    title: "Automation Backtest",
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
    editYaml: "Modifica YAML (prova una bozza)",
    resetYaml: "Ripristina salvata",
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
    noDiff: "Nessuna differenza: le due versioni partono esattamente negli stessi momenti.",
    restartBand: "Home Assistant si stava riavviando: le automazioni non erano in ascolto",
    dayShort: "g",
    selectFirst: "Scegli prima un'automazione.",
    nothingInView: "Niente in questa parte del grafico.",
    status: { executed: "Eseguita", blocked: "Bloccata", uncertain: "Incerta" },
  },
};

const ICON = { executed: "✓", blocked: "✕", uncertain: "?" };
const PERIODS = [1, 3, 7, 14];
const LIST_PAGE = 200;
const MAX_ENTITY_LANES = 8;

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const PALETTE = ["#5b8def", "#e8a33d", "#9b6bd6", "#3fb6a8", "#d9667a", "#7a9e3b", "#c77c3a", "#4fa3d1"];
function stateColor(state) {
  const s = String(state);
  if (["on", "home", "open", "playing", "heat", "cleaning", "unlocked"].includes(s)) return "#f2b134";
  if (["off", "not_home", "closed", "idle", "docked", "locked", "standby"].includes(s)) return "#8f9aa5";
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
      yamlMode: false,
      yaml: "",
      yamlSaved: "",
      yamlB: "",
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
    if (first) this._init();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._root) this._root.classList.toggle("narrow", !!value);
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
          <button class="menu" title="Menu">☰</button>
          <h1>${esc(t.title)}</h1>
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

    this.shadowRoot.querySelector(".menu").addEventListener("click", () =>
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

    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("automation");
    if (fromUrl && this._hass.states[fromUrl]) {
      this._s.automation = fromUrl;
      this._renderAll();
      this._loadYaml().then(() => this._runBacktest());
      return;
    }
    this._renderAll();
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
    this._renderChartOnly();
  }

  _yamlEditor() {
    const t = this._t;
    const s = this._s;
    if (!s.automation) return "";
    return `<div class="card yaml">
      <label class="check"><input type="checkbox" class="yaml-toggle" ${s.yamlMode ? "checked" : ""}> ${esc(t.editYaml)}</label>
      ${s.yamlMode ? `
        <textarea class="code yaml-a" spellcheck="false">${esc(s.yaml)}</textarea>
        <div class="row">
          ${s.yaml !== s.yamlSaved ? `<span class="badge warn">${esc(t.draft)}</span>` : ""}
          <button class="flat reset-yaml">${esc(t.resetYaml)}</button>
        </div>` : ""}
    </div>`;
  }

  _runTab() {
    const s = this._s;
    const t = this._t;
    let html = this._yamlEditor();
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
    let html = `<div class="ab">
      <div class="card"><h3>${esc(t.versionA)}</h3><textarea class="code" readonly>${esc(s.yamlSaved)}</textarea></div>
      <div class="card"><h3>${esc(t.versionB)}</h3><textarea class="code yaml-b" spellcheck="false">${esc(s.yamlB)}</textarea></div>
    </div>`;
    const c = s.cmp;
    if (!c) return html;
    const d = c.diff.summary;
    html += `<div class="chips">
      <span class="chip plain">A <b>${d.a_executed}</b> · B <b>${d.b_executed}</b></span>
      <span class="chip plain"><b>${d.both}</b> ${esc(t.both)}</span>
      <span class="chip only-a"><b>${d.only_a}</b> ${esc(t.onlyA)}</span>
      <span class="chip only-b"><b>${d.only_b}</b> ${esc(t.onlyB)}</span>
    </div>`;
    html += this._notices(c.a) + this._notices(c.b);
    html += `<div class="card chart-card">
      <div class="row between"><span class="hint">${esc(t.zoomHint)}</span>
      ${s.view ? `<button class="flat reset-zoom">${esc(t.resetZoom)}</button>` : ""}</div>
      <div class="chart"></div></div>`;
    if (!d.only_a && !d.only_b) {
      html += `<div class="card empty">${esc(t.noDiff)}</div>`;
    } else {
      const list = (items, cls) =>
        items.length
          ? `<table><tbody>${items
              .map((x) => `<tr><td><span class="dot ${cls}">●</span></td><td class="time">${esc(this._fmtFull(Date.parse(x.time)))}</td><td class="desc">${esc(x.trigger)}</td></tr>`)
              .join("")}</tbody></table>`
          : `<div class="empty">—</div>`;
      html += `<div class="split"><div class="card list"><h3>${esc(t.onlyA)}</h3>${list(c.diff.only_a, "only-a")}</div>
        <div class="card list"><h3>${esc(t.onlyB)}</h3>${list(c.diff.only_b, "only-b")}</div></div>`;
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
      this._renderAll();
      if (s.tab === "compare" && s.automation && !s.yamlB) this._loadYaml();
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
    } else if (el.classList.contains("reset-yaml")) {
      s.yaml = s.yamlSaved;
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
    } else if (el.classList.contains("yaml-b")) {
      s.yamlB = el.value;
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
      s.yaml = s.yamlSaved = s.yamlB = "";
      s.yamlMode = false;
      s.error = "";
      const url = new URL(window.location.href);
      if (s.automation) url.searchParams.set("automation", s.automation);
      else url.searchParams.delete("automation");
      window.history.replaceState(window.history.state, "", url);
      this._renderAll();
      if (s.automation) this._loadYaml();
    } else if (el.classList.contains("start")) {
      s.start = el.value;
    } else if (el.classList.contains("end")) {
      s.end = el.value;
    } else if (el.classList.contains("yaml-toggle")) {
      s.yamlMode = el.checked;
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

  async _loadYaml() {
    const s = this._s;
    if (!s.automation) return;
    try {
      const res = await this._ws({ type: "automation_backtest/config", automation: s.automation });
      s.yamlSaved = res.yaml;
      if (!s.yaml) s.yaml = res.yaml;
      if (!s.yamlB) s.yamlB = res.yaml;
    } catch (err) {
      s.error = err?.message || String(err);
    }
    this._renderBody();
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
      if (s.yamlMode && s.yaml && s.yaml !== s.yamlSaved) msg.config_yaml = s.yaml;
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
    if (!s.automation) {
      s.error = this._t.selectFirst;
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
        config_b_yaml: s.yamlB,
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
:host { display:block; height:100%; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); }
.root { display:flex; flex-direction:column; min-height:100%; }
header { display:flex; align-items:center; gap:8px; height:56px; padding:0 16px; position:sticky; top:0; z-index:2;
  background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff);
  border-bottom:1px solid var(--app-header-border-bottom, transparent); }
header h1 { font-size:20px; font-weight:400; margin:0; }
.menu { display:none; background:none; border:0; color:inherit; font-size:22px; cursor:pointer; padding:6px; }
.narrow .menu { display:block; }
main { padding:16px; max-width:1400px; width:100%; box-sizing:border-box; margin:0 auto; }
.card { background:var(--card-background-color, #fff); border-radius:var(--ha-card-border-radius, 12px);
  box-shadow:var(--ha-card-box-shadow, none); border:1px solid var(--divider-color, #e0e0e0); padding:16px; margin-bottom:16px; }
.controls { display:flex; flex-wrap:wrap; gap:16px 24px; align-items:flex-end; }
.field { display:flex; flex-direction:column; gap:6px; min-width:0; }
.field.grow { flex:1 1 320px; }
.field label { font-size:12px; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.04em; }
.pick { display:flex; gap:8px; }
.pick .filter { flex:0 0 140px; }
.pick select { flex:1; min-width:0; width:100%; }
.narrow .pick { flex-direction:column; }
.narrow .pick .filter { flex:none; }
.narrow td.time { white-space:normal; width:72px; font-size:12px; }
.narrow td.desc { overflow-wrap:anywhere; }
input, select, textarea { font:inherit; color:var(--primary-text-color); background:var(--secondary-background-color, #f5f5f5);
  border:1px solid var(--divider-color, #ccc); border-radius:8px; padding:8px 10px; }
.range { display:flex; gap:8px; flex-wrap:wrap; }
.range label { text-transform:none; letter-spacing:0; display:flex; gap:6px; align-items:center; }
.seg { display:flex; border:1px solid var(--divider-color); border-radius:8px; overflow:hidden; }
.seg button { border:0; border-right:1px solid var(--divider-color); background:none; color:inherit; padding:8px 12px; cursor:pointer; font:inherit; }
.seg button:last-child { border-right:0; }
.seg button.on, .tabs button.on { background:var(--primary-color); color:var(--text-primary-color, #fff); }
button.primary { background:var(--primary-color); color:var(--text-primary-color, #fff); border:0; border-radius:8px; padding:10px 18px; font:inherit; font-weight:500; cursor:pointer; }
button.primary[disabled] { opacity:.5; cursor:default; }
button.flat { background:none; border:0; color:var(--primary-color); font:inherit; cursor:pointer; padding:6px 8px; }
.link { font-size:13px; color:var(--primary-color); text-decoration:none; }
.tabs { display:flex; gap:8px; margin-bottom:16px; }
.tabs button { border:1px solid var(--divider-color); background:var(--card-background-color); color:inherit; border-radius:999px; padding:6px 16px; font:inherit; cursor:pointer; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }
.chip { border:1px solid var(--divider-color); background:var(--card-background-color); color:inherit; border-radius:999px; padding:6px 14px; font:inherit; cursor:pointer; }
.chip.plain { cursor:default; }
.chip b { font-weight:600; }
.chip.executed b { color:var(--success-color, #43a047); } .chip.blocked b { color:var(--error-color, #db4437); } .chip.uncertain b { color:var(--warning-color, #ffa600); }
.chip.on { border-color:var(--primary-color); box-shadow:0 0 0 1px var(--primary-color) inset; }
.chip.only-a b { color:#e8833a; } .chip.only-b b { color:#4f8fe8; }
.chip.restart b { color:var(--secondary-text-color); }
.banner { border-radius:10px; padding:10px 14px; margin-bottom:16px; font-size:14px; line-height:1.4; }
.banner.error { background:rgba(219,68,55,.12); color:var(--error-color, #db4437); }
.banner.warn { background:rgba(255,166,0,.12); }
.banner.info { background:rgba(3,169,244,.10); }
.badge.warn { background:rgba(255,166,0,.18); border-radius:6px; padding:3px 8px; font-size:13px; }
.row { display:flex; gap:12px; align-items:center; margin-top:8px; }
.row.between { justify-content:space-between; margin-top:0; }
.hint { font-size:12px; color:var(--secondary-text-color); }
.check { display:flex; gap:8px; align-items:center; cursor:pointer; }
textarea.code { width:100%; min-height:220px; box-sizing:border-box; margin-top:10px;
  font-family:var(--code-font-family, ui-monospace, SFMono-Regular, Menlo, monospace); font-size:13px; line-height:1.45; resize:vertical; }
.ab { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.ab .card { margin-bottom:16px; } .ab h3 { margin:0; }
.narrow .ab { grid-template-columns:1fr; }
.chart { width:100%; overflow:hidden; user-select:none; margin-top:6px; }
.chart svg { display:block; }
.split { display:grid; grid-template-columns:minmax(0, 3fr) minmax(0, 2fr); gap:16px; align-items:start; }
.narrow .split { grid-template-columns:1fr; }
.list { max-height:560px; overflow:auto; padding:8px; }
.list h3 { margin:6px 8px 10px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
tr[data-run] { cursor:pointer; }
tr[data-run]:hover { background:var(--secondary-background-color, rgba(0,0,0,.04)); }
tr.sel { background:rgba(3,169,244,.12) !important; }
td { padding:7px 8px; border-bottom:1px solid var(--divider-color); vertical-align:top; }
td.time { white-space:nowrap; color:var(--secondary-text-color); font-variant-numeric:tabular-nums; }
td.desc { word-break:break-word; }
.why { font-size:12px; color:var(--secondary-text-color); margin-top:3px; }
.dot { display:inline-flex; width:20px; height:20px; border-radius:50%; align-items:center; justify-content:center; font-size:12px; font-weight:700; color:#fff; }
.dot.big { width:34px; height:34px; font-size:17px; }
.dot.executed { background:var(--success-color, #43a047); } .dot.blocked { background:var(--error-color, #db4437); border-radius:5px; }
.dot.uncertain { background:var(--warning-color, #ffa600); }
.dot.only-a { background:none; color:#e8833a; } .dot.only-b { background:none; color:#4f8fe8; }
.detail { position:sticky; top:72px; }
.det-head { display:flex; gap:12px; align-items:center; }
.det-head .centre { margin-left:auto; }
.det-status { font-weight:600; }
.detail h3 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--secondary-text-color); margin:18px 0 6px; }
.detail p { margin:4px 0; line-height:1.45; }
.reason { padding:8px 10px; border-radius:8px; }
.reason.blocked { background:rgba(219,68,55,.10); } .reason.uncertain { background:rgba(255,166,0,.12); }
.trace { list-style:none; padding:0; margin:0; }
.trace li { display:flex; gap:8px; align-items:flex-start; padding:5px 6px; border-radius:6px; font-size:14px; }
.trace li .dot { flex:0 0 20px; }
.trace li.key { background:rgba(219,68,55,.10); }
.muted { color:var(--secondary-text-color); }
code { font-family:var(--code-font-family, ui-monospace, monospace); font-size:13px; }
.empty { color:var(--secondary-text-color); padding:12px; }
.loading { display:flex; gap:12px; align-items:center; justify-content:center; padding:24px; color:var(--secondary-text-color); }
.spinner { width:20px; height:20px; border-radius:50%; border:3px solid var(--divider-color); border-top-color:var(--primary-color); animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
svg .lbl { font-size:12px; fill:var(--primary-text-color); }
svg .tick { font-size:11px; fill:var(--secondary-text-color); }
svg .grid { stroke:var(--divider-color, #ddd); stroke-width:1; opacity:.6; }
svg .laneline { stroke:var(--divider-color, #ddd); }
svg .laneBg { fill:var(--secondary-background-color, #f5f5f5); opacity:.5; }
svg .series { fill:none; stroke:var(--primary-color, #03a9f4); stroke-width:1.6; }
svg .thr { stroke:var(--error-color, #db4437); stroke-dasharray:5 4; stroke-width:1.2; }
svg .thrlbl { font-size:11px; fill:var(--error-color, #db4437); }
svg .band { opacity:.85; }
svg .bandtxt { font-size:11px; fill:#1c1c1c; pointer-events:none; }
svg .restart { fill:var(--secondary-text-color, #888); opacity:.16; }
svg .mk { cursor:pointer; stroke:var(--card-background-color, #fff); stroke-width:1.5; }
svg .mk.executed { fill:var(--success-color, #43a047); } svg .mk.blocked { fill:var(--error-color, #db4437); } svg .mk.uncertain { fill:var(--warning-color, #ffa600); }
svg .mk.sel { stroke:var(--primary-text-color); stroke-width:2.5; }
svg .ring { fill:none; stroke-width:2; } svg .ring.a { stroke:#e8833a; } svg .ring.b { stroke:#4f8fe8; }
svg .cursor { stroke:var(--primary-text-color); stroke-width:1; stroke-dasharray:3 3; opacity:.7; }
svg .brush { fill:var(--primary-color, #03a9f4); opacity:.15; }
`;

customElements.define("automation-backtest-panel", AutomationBacktestPanel);
