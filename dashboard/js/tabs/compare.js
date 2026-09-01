const CompareTab = {
  selected: [],

  render(el) {
    const d = App.DATA;
    const projs = d.projects;

    el.innerHTML = `
      <div style="margin-bottom:20px">
        <h3 style="margin-bottom:12px">选择 2-3 个研究方向进行对比</h3>
        <div class="compare-select" id="compare-chips">
          ${projs.map(p => `<div class="compare-chip" data-pid="${p.id}" onclick="CompareTab.toggle('${p.id}')" title="${p.name}">${p.name.length > 30 ? p.name.slice(0, 30) + '...' : p.name}</div>`).join('')}
        </div>
        <span style="font-size:12px;color:var(--text-muted)">已选: <strong id="cmp-count">0</strong> 个</span>
      </div>
      <div id="compare-result" style="display:none">
        <div class="chart-row single">
          <div class="chart-card"><h3>多维度对比雷达图</h3><div class="chart-box" id="chart-cmp-radar" style="height:450px"></div></div>
        </div>
        <div class="compare-grid" id="compare-cards"></div>
      </div>
      <div class="state-empty" id="compare-empty">
        <div class="icon">🔄</div>
        <h3>选择研究方向进行对比</h3>
        <p>勾选上方 2-3 个项目，查看多维度对比分析</p>
      </div>`;

    this._updateChips();
  },

  toggle(pid) {
    const idx = this.selected.indexOf(pid);
    if (idx >= 0) {
      this.selected.splice(idx, 1);
    } else if (this.selected.length < 3) {
      this.selected.push(pid);
    }
    this._updateChips();
    this._renderCompare();
  },

  _updateChips() {
    const chips = document.querySelectorAll('#compare-chips .compare-chip');
    chips.forEach(c => {
      c.classList.toggle('selected', this.selected.includes(c.dataset.pid));
    });
    const countEl = document.getElementById('cmp-count');
    if (countEl) countEl.textContent = this.selected.length;
  },

  _renderCompare() {
    const d = App.DATA;
    const resultEl = document.getElementById('compare-result');
    const emptyEl = document.getElementById('compare-empty');
    if (!resultEl || !emptyEl) return;

    if (this.selected.length < 2) {
      resultEl.style.display = 'none';
      emptyEl.style.display = '';
      return;
    }

    resultEl.style.display = '';
    emptyEl.style.display = 'none';

    const selectedProjs = this.selected.map(id => d.projects.find(p => p.id === id)).filter(Boolean);

    this._renderRadar(selectedProjs);
    this._renderCards(selectedProjs);
  },

  _renderRadar(projs) {
    const c = initChart('chart-cmp-radar');
    if (!c) return;
    const allProjs = App.DATA.projects;
    const maxCards = Math.max(...allProjs.map(p => p.total_cards), 1);
    const maxGaps = Math.max(...allProjs.map(p => p.gap_count), 1);
    const maxLit = Math.max(...allProjs.map(p => p.literature_count||0), 1);

    const indicator = [
      { name: '证据卡片\n(数量)', max: maxCards },
      { name: '文献\n(篇数)', max: maxLit },
      { name: '缺口\n(数量)', max: maxGaps },
      { name: '缺口密度\n(缺口/卡片)', max: 0.5 },
      { name: '创新空间\n(缺口分数)', max: 1 },
      { name: '管线进度\n(%)', max: 100 },
    ];

    const series = projs.map((p, i) => ({
      name: p.name,
      type: 'radar',
      data: [{
        value: [
          p.total_cards,
          p.literature_count||0,
          p.gap_count,
          p.total_cards > 0 ? p.gap_count/p.total_cards : 0,
          this._avgGapScore(p.id),
          p.progress?.percent||0,
        ],
      }],
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: PROJECT_COLORS[i], width: 2 },
      areaStyle: { color: PROJECT_COLORS[i], opacity: .15 },
      itemStyle: { color: PROJECT_COLORS[i] },
    }));

    c.setOption({
      tooltip: {},
      legend: { bottom: 0, data: projs.map(p => p.name), textStyle: { color: fontColor(), fontSize: 10 } },
      radar: {
        center: ['50%', '45%'],
        radius: '65%',
        indicator,
        axisName: { color: textColor(), fontSize: 10 },
      },
      series,
    });
  },

  _avgGapScore(pid) {
    const gaps = App.DATA.all_gaps.filter(g => g.project_id === pid);
    if (!gaps.length) return 0;
    return gaps.reduce((s,g) => s+(g.score||0),0) / gaps.length;
  },

  _renderCards(projs) {
    const container = document.getElementById('compare-cards');
    if (!container) return;

    container.innerHTML = projs.map((p, i) => {
      const color = getArchetypeColor(p.archetype_id);
      const avgNov = p.hypotheses && p.hypotheses.length ? p.hypotheses.reduce((s,h)=>s+(h.novelty_score||0),0)/p.hypotheses.length : 0;
      const avgFea = p.hypotheses && p.hypotheses.length ? p.hypotheses.reduce((s,h)=>s+(h.feasibility_score||0),0)/p.hypotheses.length : 0;

      return `<div class="compare-card" style="border-top:3px solid ${color}">
        <h4 style="color:${color};margin-bottom:8px">${p.name}</h4>
        <table style="font-size:12px">
          <tr><td style="padding:6px 8px;font-weight:600">范式</td><td>${p.archetype}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">证据卡片</td><td><strong style="color:var(--blue)">${p.total_cards}</strong></td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">研究缺口</td><td><strong style="color:var(--red)">${p.gap_count}</strong></td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">缺口分数均值</td><td>${this._avgGapScore(p.id).toFixed(2)}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">假设数</td><td>${p.hypothesis_count}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">平均创新性</td><td style="color:var(--blue)">${avgNov.toFixed(2)}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">平均可行性</td><td style="color:var(--green)">${avgFea.toFixed(2)}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">文献数</td><td>${p.literature_count||0}</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">进度</td><td>${p.progress?.percent||0}%</td></tr>
          <tr><td style="padding:6px 8px;font-weight:600">Token</td><td>${(p.budget_used/1000).toFixed(1)}k</td></tr>
        </table>
      </div>`;
    }).join('');
  },
};
