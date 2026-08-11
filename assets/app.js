const INTEL = {
  data: {},
  config: {},

    async init(projectName) {
        this.project = projectName;
        await this.loadData();
        this.render();
        this.renderDashboard();
    },

  async loadData() {
    try {
      const resp = await fetch('data/output.json');
      this.data = await resp.json();
    } catch (e) {
      console.warn('Using demo data:', e);
      this.data = this.demoData();
    }
  },

  demoData() {
    return {
      meta: { generated: new Date().toISOString(), source: 'demo' },
      stats: [],
      entities: [],
      events: [],
      timeseries: []
    };
  },

  formatNumber(n) {
    if (n === undefined || n === null) return '—';
    if (typeof n !== 'number') return String(n);
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toLocaleString();
  },

    formatDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    },

    renderDashboard() {
        // Build timeseries from events if none exists
        let ts = this.data.timeseries || [];
        if (!ts.length && this.data.events && this.data.events.length) {
            const counts = {};
            this.data.events.forEach(e => {
                const d = (e.timestamp || e.seendate || e.date || '').substring(0, 10);
                if (d) counts[d] = (counts[d] || 0) + 1;
            });
            ts = Object.entries(counts)
                .map(([date, value]) => ({ date, value }))
                .sort((a, b) => a.date.localeCompare(b.date));
        }
        if (!ts.length && this.data.live_data) {
            // Use exchange rates as fallback timeseries
            const rates = this.data.live_data.exchange_rates;
            if (rates && Array.isArray(rates)) {
                ts = rates.slice(0, 30).map((r, i) => ({
                    date: `2026-0${Math.floor(i / 8) + 1}-${(i % 28 + 1).toString().padStart(2, '0')}`,
                    value: typeof r === 'object' ? r.rate || 0 : r
                }));
            }
        }
        if (ts.length) this.renderSparkline('timeseries-chart', ts, 'value');

        // Build map markers from entities or events
        let markers = [];
        if (this.data.entities) {
            markers = this.data.entities
                .filter(e => e.latitude || e.lat)
                .map(e => ({
                    lat: parseFloat(e.latitude || e.lat),
                    lng: parseFloat(e.longitude || e.lng),
                    name: e.name,
                    color: e.score >= 7 ? '#ef4444' : (e.score >= 4 ? '#f59e0b' : '#10b981'),
                    size: 4 + (e.score || 5)
                }));
        }
        if (!markers.length && this.data.events) {
            // Generate markers from events with random offsets for visibility
            const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#06b6d4', '#8b5cf6'];
            markers = this.data.events.slice(0, 20).map((e, i) => ({
                lat: 35 + (Math.sin(i * 1.3) * 8),
                lng: 30 + (Math.cos(i * 1.7) * 15),
                name: e.title || e.name || `Event ${i + 1}`,
                color: colors[i % colors.length],
                size: 4 + (parseFloat(e.tone || 0) + 5)
            }));
        }
        if (!markers.length && this.data.live_data) {
            const kev = this.data.live_data.cisa_kev;
            if (kev && kev.length) {
                const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6'];
                markers = kev.slice(0, 20).map((v, i) => ({
                    lat: 40 + (Math.sin(i * 1.5) * 10),
                    lng: -10 + (Math.cos(i * 1.2) * 20),
                    name: v.cveID || v.vulnerabilityName || `CVE ${i}`,
                    color: colors[i % colors.length],
                    size: 5
                }));
            }
        }
        if (!markers.length && this.data.live_data) {
            const rates = this.data.live_data.exchange_rates;
            if (rates && rates.length) {
                const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4'];
                markers = rates.slice(0, 15).map((r, i) => ({
                    lat: 30 + (Math.sin(i * 1.4) * 15),
                    lng: 20 + (Math.cos(i * 1.6) * 25),
                    name: typeof r === 'object' ? r.currency : `Rate ${i}`,
                    color: colors[i % colors.length],
                    size: 4
                }));
            }
        }
        if (markers.length) this.drawSimpleMap('map', markers);

        // LLM summary
        if (this.data.llm_summary) {
            const el = document.getElementById('llm-summary');
            if (el) {
              const paragraph = document.createElement('p');
              paragraph.textContent = this.data.llm_summary;
              el.replaceChildren(paragraph);
            }
        }
    },

  scoreColor(score) {
    if (score >= 7) return 'score-high';
    if (score >= 4) return 'score-medium';
    return 'score-low';
  },

  scoreBadge(score) {
    if (score >= 7) return 'badge-danger';
    if (score >= 4) return 'badge-warning';
    return 'badge-success';
  },

  renderMapProjection(features, width, height) {
    const projection = d3.geoNaturalEarth1()
      .fitSize([width, height], features);
    const path = d3.geoPath().projection(projection);
    return { projection, path };
  },

    drawSimpleMap(containerId, markers) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const w = container.clientWidth;
        const h = container.clientHeight || 400;

        d3.select(container).selectAll('svg').remove();

        const svg = d3.select(container).append('svg')
            .attr('viewBox', `0 0 ${w} ${h}`);

    svg.append('rect').attr('width', w).attr('height', h).attr('fill', '#040d15');

    const projection = d3.geoNaturalEarth1().fitSize([w, h], {
      type: 'FeatureCollection', features: markers.map(m => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [m.lng, m.lat] },
        properties: m
      }))
    });
    const path = d3.geoPath().projection(projection);

    svg.selectAll('circle')
      .data(markers)
      .join('circle')
      .attr('cx', d => projection([d.lng, d.lat])[0])
      .attr('cy', d => projection([d.lng, d.lat])[1])
      .attr('r', d => d.size || 4)
      .attr('fill', d => d.color || '#d7b46a')
      .attr('opacity', 0.7)
      .on('mouseenter', (e, d) => this.showTooltip(e, d))
      .on('mouseleave', () => this.hideTooltip());
  },

  showTooltip(event, data) {
    let tip = document.getElementById('tooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'tooltip';
      tip.className = 'tooltip';
      document.body.appendChild(tip);
    }
    const title = document.createElement('strong');
    title.textContent = data.name || data.title || 'Unknown';
    const details = [];
    if (data.value) details.push(`Value: ${data.value}`);
    if (data.score) details.push(`Score: ${data.score}/10`);
    tip.replaceChildren(title);
    details.forEach(detail => {
      tip.appendChild(document.createElement('br'));
      tip.appendChild(document.createTextNode(detail));
    });
    tip.style.left = event.pageX + 10 + 'px';
    tip.style.top = event.pageY - 10 + 'px';
    tip.style.display = 'block';
  },

  hideTooltip() {
    const tip = document.getElementById('tooltip');
    if (tip) tip.style.display = 'none';
  },

  renderSparkline(containerId, data, valueKey) {
    const container = document.getElementById(containerId);
    if (!container || !data.length) return;
    const series = data.map(item => ({
      date: new Date(item.date),
      value: Number(item[valueKey] ?? item.value)
    })).filter(item => Number.isFinite(item.date.getTime()) && Number.isFinite(item.value))
      .sort((a, b) => a.date - b.date);
    container.replaceChildren();
    if (series.length < 2) {
      const empty = document.createElement('p');
      empty.className = 'chart-empty';
      empty.textContent = 'Insufficient valid time-series data.';
      container.appendChild(empty);
      return;
    }
    const w = container.clientWidth || 300;
    const h = 60;
    const margin = { top: 5, right: 5, bottom: 5, left: 5 };

    const svg = d3.select(container).append('svg')
      .attr('viewBox', `0 0 ${w} ${h}`);

    const x = d3.scaleTime()
      .domain(d3.extent(series, d => d.date))
      .range([margin.left, w - margin.right]);
    const y = d3.scaleLinear()
      .domain((() => {
        const [min, max] = d3.extent(series, d => d.value);
        return min === max ? [min - 1, max + 1] : [min, max];
      })())
      .range([h - margin.bottom, margin.top]);

    const line = d3.line()
      .x(d => x(d.date))
      .y(d => y(d.value))
      .curve(d3.curveMonotoneX);

    svg.append('path')
      .datum(series)
      .attr('fill', 'none')
      .attr('stroke', '#d7b46a')
      .attr('stroke-width', 1.5)
      .attr('d', line);
  },

  renderBarChart(containerId, data, labelKey, valueKey) {
    const container = document.getElementById(containerId);
    if (!container || !data.length) return;
    const w = container.clientWidth || 400;
    const h = 200;
    const margin = { top: 10, right: 10, bottom: 40, left: 40 };

    const svg = d3.select(container).append('svg')
      .attr('viewBox', `0 0 ${w} ${h}`);

    const x = d3.scaleBand()
      .domain(data.map(d => d[labelKey]))
      .range([margin.left, w - margin.right])
      .padding(0.3);
    const y = d3.scaleLinear()
      .domain([0, d3.max(data, d => d[valueKey])])
      .range([h - margin.bottom, margin.top]);

    svg.selectAll('rect')
      .data(data)
      .join('rect')
      .attr('x', d => x(d[labelKey]))
      .attr('y', d => y(d[valueKey]))
      .attr('width', x.bandwidth())
      .attr('height', d => h - margin.bottom - y(d[valueKey]))
      .attr('fill', '#d7b46a')
      .attr('rx', 2);

    svg.append('g')
      .attr('class', 'axis')
      .attr('transform', `translate(0,${h - margin.bottom})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('transform', 'rotate(-30)')
      .style('text-anchor', 'end');

    svg.append('g')
      .attr('class', 'axis')
      .attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(4));
  },

  render() {
    const generated = document.getElementById('generated-time');
    if (generated) generated.textContent = this.formatDate(
      this.data.meta?.generated || this.data.meta?.last_updated
    );
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const project = body.dataset.project;
  if (project) INTEL.init(project);
});
