const PipelineTab = {
  render(el) {
    const d = App.DATA;
    const phases = [
      { name: 'Scoping', alloc: 250000, color: '#3B82F6' },
      { name: 'Discovery', alloc: 1000000, color: '#10B981' },
      { name: 'Extraction', alloc: 2250000, color: '#F59E0B' },
      { name: 'Synthesis', alloc: 1250000, color: '#8B5CF6' },
    ];

    const stepColors = ['#3B82F6','#6366F1','#8B5CF6','#10B981','#F59E0B','#EF4444','#EC4899','#F97316','#06B6D4','#84CC16','#E11D48','#7C3AED','#0891B2','#EA580C'];

    el.innerHTML = `
      <div class="chart-card" style="margin-bottom:16px">
        <h3>12步自动化研究管线</h3>
        <div class="pipeline-flow">
          ${d.pipeline.map((s,i) => `
            ${i>0 ? '<span class="pipeline-arrow">→</span>' : ''}
            <div class="pipeline-step" style="border-left:3px solid ${stepColors[i]}">
              <div class="step-id">${s[0]}</div>
              <div class="step-name">${s[1]}</div>
              <div class="step-en">${s[2]}</div>
            </div>
          `).join('')}
        </div>
      </div>
      <div class="chart-row">
        <div class="chart-card"><h3>各项目Token预算消耗</h3><div class="chart-box" id="chart-pipe-budget" style="height:380px"></div></div>
        <div class="chart-card"><h3>预算阶段分配 (总额500万tokens/项目)</h3><div class="chart-box" id="chart-pipe-phases" style="height:380px"></div></div>
      </div>
      <div class="chart-row single">
        <div class="chart-card"><h3>Token用量 vs 证据卡片产出效率</h3><div class="chart-box" id="chart-pipe-efficiency" style="height:350px"></div></div>
      </div>
      <div class="chart-card"><h3>项目预算使用详情</h3>
        <div class="table-wrap"><table><thead><tr><th>项目</th><th>已用Tokens</th><th>使用率</th><th>卡片数</th><th>效率(tok/card)</th><th>进展</th></tr></thead>
          <tbody>${d.projects.map(p => {
            const used = p.budget_used||0;
            const total = 5000000;
            const rate = ((used/total)*100).toFixed(2);
            const eff = p.total_cards > 0 ? (used/p.total_cards).toFixed(0) : '-';
            const pct = p.progress?.percent||0;
            return `<tr>
              <td><strong>${p.name}</strong></td>
              <td>${(used/1000).toFixed(1)}k</td>
              <td><div style="display:flex;align-items:center;gap:8px"><div style="flex:1;height:6px;border-radius:3px;background:var(--bg-alt)"><div style="height:100%;border-radius:3px;background:var(--blue);width:${rate}%"></div></div>${rate}%</div></td>
              <td>${p.total_cards}</td>
              <td>${eff}</td>
              <td><div class="progress-bar" style="width:80px;margin:0"><div class="fill" style="width:${pct}%;background:var(--green)"></div></div>${pct}%</td>
            </tr>`;
          }).join('')}</tbody>
        </table></div>
      </div>`;

    this._renderBudget();
    this._renderPhases();
    this._renderEfficiency();
  },

  _renderBudget() {
    const c = initChart('chart-pipe-budget');
    if (!c) return;
    const used = App.DATA.projects.map(p => p.budget_used||0);
    const reversed = [...used].reverse();
    const getColor = (v) => v > 70000 ? '#EF4444' : v > 30000 ? '#F59E0B' : '#10B981';
    c.setOption({
      tooltip: { trigger: 'axis', formatter: p => `${p.name}<br/>${(p.value/1000).toFixed(1)}k tokens` },
      grid: { left: 140, right: 60, top: 10, bottom: 30 },
      xAxis: { type: 'value', axisLabel: { color: fontColor(), formatter: v => (v/1000).toFixed(0)+'k' } },
      yAxis: { type: 'category', data: App.DATA.projects.map(p => p.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      series: [{
        type: 'bar', data: reversed,
        itemStyle: { color: p => getColor(p.value), borderRadius: [0,4,4,0] },
        label: { show: true, position: 'right', formatter: p => (p.value/1000).toFixed(1)+'k', color: textColor(), fontSize: 11 },
        markLine: { silent: true, data: [{ type: 'average', name: '均值', label: { formatter: p => (p.value/1000).toFixed(0)+'k' } }], lineStyle: { color: '#EF4444', type: 'dashed' } },
      }],
    });
  },

  _renderPhases() {
    const c = initChart('chart-pipe-phases');
    if (!c) return;
    const phases = [
      { value: 250, name: 'Scoping', itemStyle: { color: '#3B82F6' } },
      { value: 1000, name: 'Discovery', itemStyle: { color: '#10B981' } },
      { value: 2250, name: 'Extraction', itemStyle: { color: '#F59E0B' } },
      { value: 1250, name: 'Synthesis', itemStyle: { color: '#8B5CF6' } },
    ];
    c.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c}k tokens ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%','70%'],
        data: phases,
        label: { color: textColor(), formatter: '{b}\n{d}%' },
      }],
    });
  },

  _renderEfficiency() {
    const c = initChart('chart-pipe-efficiency');
    if (!c) return;
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['Token用量(k)','证据卡片数'], bottom: 0, textStyle: { color: fontColor() } },
      grid: { left: 50, right: 50, top: 20, bottom: 50 },
      xAxis: { type: 'category', data: App.DATA.projects.map(p => p.name), axisLabel: { color: textColor(), fontSize: 10, rotate: 30, interval: 0 } },
      yAxis: [
        { type: 'value', name: 'Token用量(k)', axisLabel: { color: fontColor() }, nameTextStyle: { color: fontColor() } },
        { type: 'value', name: '卡片数', axisLabel: { color: fontColor() }, nameTextStyle: { color: fontColor() } },
      ],
      series: [
        { name: 'Token用量(k)', type: 'bar', data: App.DATA.projects.map(p => (p.budget_used||0)/1000), itemStyle: { color: '#3B82F6' }, yAxisIndex: 0 },
        { name: '证据卡片数', type: 'line', data: App.DATA.projects.map(p => p.total_cards), itemStyle: { color: '#10B981' }, yAxisIndex: 1, symbol: 'circle', symbolSize: 8 },
      ],
    });
  },
};
