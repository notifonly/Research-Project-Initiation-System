const HypothesesTab = {
  render(el) {
    const d = App.DATA;
    const avgNov = d.all_hypotheses.length ? (d.all_hypotheses.reduce((s,h) => s+(h.novelty_score||0),0)/d.all_hypotheses.length).toFixed(2) : 'N/A';
    const avgFea = d.all_hypotheses.length ? (d.all_hypotheses.reduce((s,h) => s+(h.feasibility_score||0),0)/d.all_hypotheses.length).toFixed(2) : 'N/A';

    el.innerHTML = `
      <div class="stats-row">
        <div class="stat-card"><div class="label">总假设</div><div class="value">${d.meta.total_hypotheses}</div></div>
        <div class="stat-card" style="border-left:3px solid var(--blue)"><div class="label">平均创新性</div><div class="value">${avgNov}</div></div>
        <div class="stat-card" style="border-left:3px solid var(--green)"><div class="label">平均可行性</div><div class="value">${avgFea}</div></div>
      </div>
      <div class="chart-row triple">
        <div class="chart-card"><h3>创新性 vs 可行性 散点图</h3><div class="chart-box" id="chart-hyp-scatter" style="height:380px"></div></div>
        <div class="chart-card"><h3>预期影响分布</h3><div class="chart-box" id="chart-hyp-impact" style="height:380px"></div></div>
        <div class="chart-card"><h3>各项目假设创新性对比</h3><div class="chart-box" id="chart-hyp-novelty" style="height:380px"></div></div>
      </div>
      <div class="chart-card"><h3>全部研究假设 <span style="font-weight:400;font-size:12px;color:var(--text-muted)">(点击行查看详情)</span></h3>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>假设陈述</th><th>项目</th><th>针对缺口</th><th>创新性</th><th>可行性</th><th>预期影响</th></tr></thead>
          <tbody>${d.all_hypotheses.map((h,i) => this._hypRow(h,i)).join('')}</tbody>
        </table></div>
      </div>`;

    this._renderScatter();
    this._renderImpact();
    this._renderNovelty();
  },

  _hypRow(h, i) {
    const impTag = (h.expected_impact||'').toLowerCase().includes('revolutionary') ? 'impact-rev' :
      (h.expected_impact||'').toLowerCase().includes('transformative') ? 'impact-trans' :
      (h.expected_impact||'').toLowerCase().includes('high') ? 'impact-high' : 'impact-med';
    return `<tr class="cursor" onclick="HypothesesTab.showDetail(${i})">
      <td><code>H${i+1}</code></td>
      <td style="max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${h.statement||''}">${h.statement||''}</td>
      <td style="font-size:11px">${h.project_name||''}</td>
      <td style="font-size:11px"><code>${h.addresses_gap||''}</code></td>
      <td>${(h.novelty_score||0).toFixed(2)}</td>
      <td>${(h.feasibility_score||0).toFixed(2)}</td>
      <td><span class="impact-tag ${impTag}">${h.expected_impact ? h.expected_impact.split(':')[0] : 'N/A'}</span></td>
    </tr>`;
  },

  showDetail(idx) {
    const h = App.DATA.all_hypotheses[idx];
    if (!h) return;

    const hasRationale = h.rationale && h.rationale.length > 10;
    const hasMethods = Array.isArray(h.required_methods) && h.required_methods.length;
    const hasDatasets = Array.isArray(h.required_datasets) && h.required_datasets.length;

    showModal(`
      <button class="close" onclick="closeModal()">✕</button>
      <h3>${h.hypothesis_id||'H'+idx}: 研究假设详情</h3>
      <div class="field"><div class="field-label">项目</div>${h.project_name||''} <span style="font-size:11px;color:var(--text-muted)">(${h.archetype||''})</span></div>
      <div class="field"><div class="field-label">完整陈述</div><div class="field-val" style="font-weight:600">${h.statement||'N/A'}</div></div>
      <div class="field"><div class="field-label">针对缺口</div><code>${h.addresses_gap||'N/A'}</code></div>
      <div class="field"><div class="field-label">理论依据 <span style="font-size:10px">${hasRationale ? '✅ 有文献依据' : '⚠️ AI推断'}</span></div><div class="field-val">${h.rationale||'未提供详细依据'}</div></div>
      <div class="field"><div class="field-label">所需方法</div>${hasMethods ? h.required_methods.map(m => `<span class="badge badge-blue" style="margin:2px">${m}</span>`).join('') : '<span style="color:var(--text-muted);font-size:12px">未指定</span>'}</div>
      <div class="field"><div class="field-label">所需数据集</div>${hasDatasets ? h.required_datasets.map(d => `<span class="badge badge-green" style="margin:2px">${d}</span>`).join('') : '<span style="color:var(--text-muted);font-size:12px">未指定</span>'}</div>
      <div style="display:flex;gap:16px;margin-top:12px">
        <div style="text-align:center;padding:8px 16px;background:var(--bg-alt);border-radius:8px"><div style="font-size:11px;color:var(--text-muted)">创新性</div><div style="font-weight:700;font-size:18px;color:var(--blue)">${(h.novelty_score||0).toFixed(2)}</div></div>
        <div style="text-align:center;padding:8px 16px;background:var(--bg-alt);border-radius:8px"><div style="font-size:11px;color:var(--text-muted)">可行性</div><div style="font-weight:700;font-size:18px;color:var(--green)">${(h.feasibility_score||0).toFixed(2)}</div></div>
        <div style="text-align:center;padding:8px 16px;background:var(--bg-alt);border-radius:8px"><div style="font-size:11px;color:var(--text-muted)">影响</div><div style="font-weight:700;font-size:16px">${h.expected_impact||'N/A'}</div></div>
      </div>
    `);
  },

  _renderScatter() {
    const c = initChart('chart-hyp-scatter');
    if (!c) return;
    const colors = PROJECT_COLORS;
    const projMap = {};
    App.DATA.projects.forEach((p,i) => { projMap[p.id] = { name: p.name_en || p.name, color: colors[i] }; });
    c.setOption({
      tooltip: { formatter: p => `<b>${p.seriesName}</b><br/>创新性: ${p.value[0]}<br/>可行性: ${p.value[1]}<br/>影响: ${p.value[2]}<br/>${p.value[3]||''}` },
      legend: { bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      grid: { left: 50, right: 20, top: 10, bottom: 60 },
      xAxis: { name: '创新性', min: 0, max: 1, axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor() } },
      yAxis: { name: '可行性', min: 0, max: 1, axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor() } },
      series: App.DATA.projects.map(p => ({
        name: p.name_en || p.name,
        type: 'scatter',
        symbolSize: val => Math.max((val[2]||2)*8, 10),
        data: App.DATA.all_hypotheses.filter(h => h.project_id === p.id).map(h => [h.novelty_score||0, h.feasibility_score||0, h.impact_level||2, (h.statement||'').slice(0, 50)]),
        itemStyle: { color: projMap[p.id]?.color || '#6B7280', opacity: .8 },
        emphasis: { focus: 'series' },
      })),
    });
  },

  _renderImpact() {
    const c = initChart('chart-hyp-impact');
    if (!c) return;
    const dist = {};
    App.DATA.all_hypotheses.forEach(h => {
      const w = (h.expected_impact||'').toLowerCase();
      if (w.includes('revolutionary')) dist.Revolutionary = (dist.Revolutionary||0)+1;
      else if (w.includes('transformative')) dist.Transformative = (dist.Transformative||0)+1;
      else if (w.includes('high')) dist.High = (dist.High||0)+1;
      else dist.Medium = (dist.Medium||0)+1;
    });
    const keys = ['Revolutionary','Transformative','High','Medium'];
    const piColors = ['#EF4444','#F97316','#F59E0B','#3B82F6'];
    c.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: ['40%','70%'],
        data: keys.map((k,i) => ({ value: dist[k]||0, name: k, itemStyle: { color: piColors[i] } })),
        label: { color: textColor(), formatter: '{b}: {c}' },
      }],
    });
  },

  _renderNovelty() {
    const c = initChart('chart-hyp-novelty');
    if (!c) return;
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 30, top: 10, bottom: 40 },
      xAxis: { type: 'category', data: App.DATA.projects.map(p => p.name), axisLabel: { color: textColor(), fontSize: 10, rotate: 30, interval: 0 } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { color: fontColor() } },
      series: [{
        type: 'boxplot',
        data: App.DATA.projects.map(p => {
          const scores = App.DATA.all_hypotheses.filter(h => h.project_id === p.id).map(h => h.novelty_score||0).sort((a,b)=>a-b);
          if (!scores.length) return [0,0,0,0,0];
          return [scores[0], scores[Math.floor(scores.length*.25)], scores[Math.floor(scores.length*.5)], scores[Math.floor(scores.length*.75)], scores[scores.length-1]];
        }),
        itemStyle: { color: '#3B82F6' },
      }],
    });
  },
};
