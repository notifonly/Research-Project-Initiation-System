const ProposalsTab = {
  render(el) {
    const d = App.DATA;
    el.innerHTML = `
      <div class="chart-row">
        <div class="chart-card"><h3>开题方向评分矩阵 (创新性 vs 可行性)</h3><div class="chart-box" id="chart-prop-scatter" style="height:420px"></div></div>
        <div class="chart-card"><h3>跨领域桥接模式频次</h3><div class="chart-box" id="chart-prop-bridge" style="height:420px"></div></div>
      </div>
      ${(d.thesis_suggestions||[]).map(t => `
        <div class="tier-card" style="border-left:4px solid ${t.tier===1?'#EF4444':t.tier===2?'#F59E0B':'#3B82F6'}">
          <h3>${t.label}</h3>
          <div class="tier-list">
            ${(t.items||[]).map(item => `
              <div class="tier-item">
                <h4>${item.title}</h4>
                <p>${item.reason||''}</p>
                <p style="margin-top:4px"><strong>涉及:</strong> ${item.projects||''}</p>
                <div class="scores">
                  <div class="score-bar"><span>创新性</span><div class="bar-bg"><div class="bar-fill" style="width:${(item.innovation_score||0)*100}%;background:linear-gradient(90deg,#3B82F6,#8B5CF6)"></div></div></div>
                  <div class="score-bar"><span>可行性</span><div class="bar-bg"><div class="bar-fill" style="width:${(item.feasibility_score||0)*100}%;background:linear-gradient(90deg,#10B981,#34D399)"></div></div></div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('')}
      ${(!d.thesis_suggestions||!d.thesis_suggestions.length) ? `<div class="state-empty"><div class="icon">⭐</div><h3>暂无开题建议</h3><p>需要更多假设数据来生成建议</p></div>` : ''}`;

    this._renderScatter();
    this._renderBridge();
  },

  _renderScatter() {
    const c = initChart('chart-prop-scatter');
    if (!c) return;
    const allItems = (App.DATA.thesis_suggestions||[]).flatMap(t => t.items||[]);
    if (!allItems.length) return;
    const tierColors = ['#EF4444','#F59E0B','#3B82F6'];
    const series = (App.DATA.thesis_suggestions||[]).map(t => ({
      name: `Tier ${t.tier}`,
      type: 'scatter',
      symbolSize: 18,
      data: (t.items||[]).map(item => [item.innovation_score, item.feasibility_score, item.title]),
      itemStyle: { color: tierColors[(t.tier||1)-1], opacity: .85 },
      label: { show: true, formatter: p => p.value[2], position: 'right', color: textColor(), fontSize: 11 },
      emphasis: { focus: 'series' },
    }));
    c.setOption({
      tooltip: { formatter: p => `<b>${p.value[2]}</b><br/>创新性: ${p.value[0]}<br/>可行性: ${p.value[1]}` },
      legend: { bottom: 0, textStyle: { color: fontColor() } },
      grid: { left: 60, right: 180, top: 10, bottom: 50 },
      xAxis: { name: '创新性', min: 0, max: 1, axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor() } },
      yAxis: { name: '可行性', min: 0, max: 1, axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor() } },
      series,
    });
  },

  _renderBridge() {
    const c = initChart('chart-prop-bridge');
    if (!c) return;
    const cp = App.DATA.cross_patterns;
    if (!cp || !cp.length) return;
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      grid: { left: 140, right: 30, top: 10, bottom: 55 },
      xAxis: { type: 'value', axisLabel: { color: fontColor() } },
      yAxis: { type: 'category', data: cp.map(r => r.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      series: App.DATA.projects.map((p,i) => ({
        name: p.name_en || p.name, type: 'bar', stack: 'total',
        data: cp.map(r => r[p.id]||0).reverse(),
        itemStyle: { color: PROJECT_COLORS[i] },
        emphasis: { focus: 'series' },
      })),
    });
  },
};
