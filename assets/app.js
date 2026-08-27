'use strict';

const escapeHTML = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmtDate = value => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : new Intl.DateTimeFormat('en-GB', {dateStyle:'medium', timeStyle:'short', timeZone:'UTC'}).format(date) + ' UTC';
};

class Dashboard {
  constructor(data) {
    this.data = data || {};
    this.warning = this.data.early_warning || {};
    this.components = this.warning.components || [];
  }

  component(id) { return this.components.find(row => row.id === id) || {}; }
  set(id, value) { const node = document.getElementById(id); if (node) node.textContent = value; }

  renderHeader() {
    const meta = this.data.meta || {};
    this.set('data-mode', `${String(meta.mode || 'unavailable').toUpperCase()} · 6h refresh`);
    this.set('generated-time', fmtDate(meta.generated));
  }

  renderWarning() {
    this.set('warning-score', number(this.warning.score).toFixed(1));
    this.set('warning-level', this.warning.level || 'UNAVAILABLE');
    this.set('warning-confidence', `${this.warning.confidence || 'LOW'} · ${number(this.warning.confidence_score).toFixed(0)}%`);
    this.set('warning-horizon', this.warning.horizon || '0–30 days');
    this.set('warning-concurrence', this.warning.concurrence?.active ? `ACTIVE · +${number(this.warning.concurrence.score_bonus).toFixed(0)}` : 'NOT ACTIVE');
    const health = this.warning.data_health || {};
    this.set('warning-health', `${number(health.available_components)}/4 components`);
    const level = document.getElementById('warning-level');
    if (level) level.dataset.level = String(this.warning.level || '').toLowerCase();
    const container = document.getElementById('warning-components');
    if (!container) return;
    container.innerHTML = this.components.map(row => `
      <article class="component-card ${row.available ? '' : 'unavailable'}">
        <div><span>${escapeHTML(row.label)}</span><strong>${row.available ? number(row.score).toFixed(1) : 'N/A'}</strong></div>
        <div class="component-bar"><i style="width:${row.available ? Math.min(100, number(row.score)) : 0}%"></i></div>
        <small>${row.retained ? 'Retained source · ' : ''}${row.available ? 'included in model' : 'awaiting prior snapshot'}</small>
      </article>`).join('');
  }

  renderStats() {
    const grid = document.getElementById('stat-grid');
    if (!grid) return;
    grid.innerHTML = (this.data.stats || []).map(row => `<article class="stat-card"><div class="stat-value">${escapeHTML(row.value)}</div><div class="stat-label">${escapeHTML(row.label)}</div><div class="stat-delta">${escapeHTML(row.delta)}</div></article>`).join('');
  }

  renderRadar() {
    const action = this.component('ofac_action_velocity');
    const posture = this.component('official_posture_shift');
    const releases = this.data.live_data?.ofac_releases?.releases || [];
    const target = document.getElementById('ofac-radar');
    if (!target) return;
    const rows = [
      ['Current official actions', action.current_7d_designation_releases ?? 0, `prior weekly median ${number(action.baseline_weekly_median).toFixed(1)}`],
      ['Action-theme breadth', (action.themes || []).length, 'predeclared sanctions programs/themes'],
      ['Posture term rate', posture.current_weighted_term_rate ?? 0, `${number(posture.baseline_weeks)} baseline weeks`],
      ['Official release archive', releases.length, `${this.data.live_data?.ofac_releases?.pages || 0} source pages`],
    ];
    const max = Math.max(1, ...rows.map(row => number(row[1])));
    target.innerHTML = rows.map(([label, value, note]) => `<div class="radar-row"><div><strong>${escapeHTML(label)}</strong><span>${escapeHTML(note)}</span></div><b>${escapeHTML(value)}</b><div class="radar-bar"><i style="width:${Math.max(4, number(value) / max * 100)}%"></i></div></div>`).join('');
  }

  renderDelta() {
    const delta = this.component('sdn_delta_breadth');
    const target = document.getElementById('sdn-delta');
    if (!target) return;
    if (!delta.available) {
      target.innerHTML = '<p class="empty-state">Baseline established. Exact additions and removals appear after next accepted official SDN snapshot.</p>';
      return;
    }
    const evidence = [...(delta.added || []), ...(delta.removed || [])];
    target.innerHTML = `<div class="delta-totals"><div><strong>+${number(delta.added_count)}</strong><span>added</span></div><div><strong>−${number(delta.removed_count)}</strong><span>removed</span></div><div><strong>${number(delta.current_count).toLocaleString()}</strong><span>total</span></div></div>` +
      (evidence.length ? `<div class="evidence-list">${evidence.slice(0, 6).map(row => `<div><span>${escapeHTML(row.name || row.id)}</span><small>${escapeHTML(row.program || row.type || '')}</small></div>`).join('')}</div>` : '<p class="empty-state">No entity-ID changes in this accepted snapshot.</p>');
  }

  renderAlerts() {
    const target = document.getElementById('warning-alerts');
    if (!target) return;
    const alerts = this.warning.alerts || [];
    target.innerHTML = alerts.length ? alerts.map(row => `<article class="alert-row"><div><b>${escapeHTML(row.level)}</b><strong>${escapeHTML(row.title)}</strong></div><span>${number(row.score).toFixed(1)}</span><p>${escapeHTML(row.why)}</p></article>`).join('') : '<p class="empty-state">No component exceeds the watch threshold.</p>';
  }

  renderEvents() {
    const target = document.getElementById('event-list');
    if (!target) return;
    const events = this.data.events || [];
    target.innerHTML = events.length ? events.slice(0, 8).map(row => `<article class="event-item"><time>${escapeHTML(row.date || '')}</time><a href="${escapeHTML(row.url || row.link || '#')}" target="_blank" rel="noopener">${escapeHTML(row.title || 'Official action')}</a><small>${escapeHTML(row.action_title || row.source || 'OFAC/Treasury')}</small></article>`).join('') : '<p class="empty-state">No current official actions.</p>';
  }

  renderHistory() {
    const target = document.getElementById('timeseries-chart');
    if (!target) return;
    const rows = this.warning.history || [];
    if (rows.length < 2) {
      target.innerHTML = '<p class="empty-state">History begins with this accepted run.</p>';
      return;
    }
    const width = 900, height = 260, pad = 28;
    const points = rows.map((row, index) => ({x: pad + index * (width - 2 * pad) / Math.max(1, rows.length - 1), y: height - pad - number(row.score) * (height - 2 * pad) / 100, score:number(row.score)}));
    const path = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
    target.innerHTML = `<svg class="history-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Warning score history"><line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"/><line x1="${pad}" y1="${height-pad-35*(height-2*pad)/100}" x2="${width-pad}" y2="${height-pad-35*(height-2*pad)/100}" class="threshold"/><path d="${path}"/><circle cx="${points.at(-1).x}" cy="${points.at(-1).y}" r="5"/><text x="${points.at(-1).x-8}" y="${points.at(-1).y-12}">${points.at(-1).score.toFixed(1)}</text></svg>`;
  }

  render() {
    this.renderHeader(); this.renderWarning(); this.renderStats(); this.renderRadar();
    this.renderDelta(); this.renderAlerts(); this.renderEvents(); this.renderHistory();
  }
}

fetch(`data/output.json?t=${Date.now()}`, {cache:'no-store'})
  .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then(data => new Dashboard(data).render())
  .catch(error => {
    document.body.classList.add('data-error');
    const title = document.getElementById('warning-title');
    if (title) title.textContent = 'Validated data temporarily unavailable';
    console.error('Dashboard data load failed:', error);
  });
