const GapsTab = {
  render(el) {
    const d = App.DATA;
    const totalScores = d.all_gaps.map(g => g.score||0).sort((a,b)=>a-b);

    el.innerHTML = `
      <div class="stats-row">
        <div class="stat-card"><div class="label">研究缺口总数</div><div class="value" style="color:var(--red)">${d.meta.total_gaps}</div><div class="sub">${Object.keys(d.gap_patterns).length} 种模式</div></div>
        <div class="stat-card"><div class="label">平均缺口分数</div><div class="value">${totalScores.length ? (totalScores.reduce((a,b)=>a+b,0)/totalScores.length).toFixed(2) : 'N/A'}</div><div class="sub">${totalScores.filter(s=>s>=0.7).length} 个高优先级</div></div>
        <div class="stat-card"><div class="label">最高跨领域模式</div><div class="value">P10</div><div class="sub">${d.projects.filter(p=>p.gap_count>0).length}/7 项目存在</div></div>
      </div>
      <div class="chart-row">
        <div class="chart-card"><h3>各项目缺口数量</h3><div class="chart-box" id="chart-gap-count" style="height:340px"></div></div>
        <div class="chart-card"><h3>缺口分数分布</h3><div class="chart-box" id="chart-gap-score" style="height:340px"></div></div>
      </div>
      <div class="chart-row single">
        <div class="chart-card"><h3>缺口模式热力图 (项目 × 模式)</h3><div class="chart-box" id="chart-gap-heat" style="height:380px"></div></div>
      </div>
      <div class="chart-card"><h3>全部缺口详情 <span style="font-weight:400;font-size:12px;color:var(--text-muted)">(点击行查看详情)</span></h3>
        <div class="table-wrap"><table><thead><tr><th>Gap ID</th><th>模式</th><th>项目</th><th>描述</th><th>分数</th><th>证据卡数</th><th>可行性</th></tr></thead>
          <tbody>${d.all_gaps.slice(0, 50).map((g, i) => this._gapRow(g, i)).join('')}</tbody>
        </table></div>
        ${d.all_gaps.length > 50 ? `<p style="padding:12px;color:var(--text-muted);font-size:12px">显示前50条，共 ${d.all_gaps.length} 条缺口</p>` : ''}
      </div>`;

    this._renderCountBars();
    this._renderScoreDist();
    this._renderHeatmap();
  },

  _gapRow(g, i) {
    const sc = g.score || 0;
    const scoreColor = sc >= 0.7 ? '#10B981' : sc >= 0.5 ? '#F59E0B' : '#EF4444';
    return `<tr class="cursor" onclick="GapsTab.showDetail(${i})">
      <td><code style="font-size:11px">${g.gap_id||''}</code></td>
      <td><span class="badge badge-blue">${g.pattern_id||''}</span></td>
      <td style="font-size:12px">${g.project_name||''}</td>
      <td style="font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${g.description||''}">${g.description||g.axis||''}</td>
      <td><span class="gap-score-bar" style="width:${sc*60}px;background:${scoreColor}"></span>${(sc*100).toFixed(0)}</td>
      <td>${g.supporting_card_count||0}</td>
      <td>${((g.feasibility||0)*100).toFixed(0)}%${g.cross_archetype ? ' 🔗' : ''}</td>
    </tr>`;
  },

  showDetail(idx) {
    const g = App.DATA.all_gaps[idx];
    if (!g) return;

    const sc = g.score || 0;
    const scoreColor = sc >= 0.7 ? '#10B981' : sc >= 0.5 ? '#F59E0B' : '#EF4444';

    let supportingHtml = '';
    const cards = g.supporting_cards;
    if (Array.isArray(cards) && cards.length) {
      supportingHtml = `<div class="field"><div class="field-label">支撑证据卡片 (${cards.length})</div>
        <div style="max-height:200px;overflow-y:auto">${cards.slice(0,10).map(c => {
          const cid = typeof c === 'string' ? c : c.card_id||'';
          const txt = typeof c === 'string' ? '' : c.key_finding||c.description||'';
          return `<div style="font-size:12px;padding:4px 6px;border-bottom:1px solid var(--border)"><code style="font-size:10px">${cid}</code> ${txt}</div>`;
        }).join('')}</div></div>`;
    }

    showModal(`
      <button class="close" onclick="closeModal()">✕</button>
      <h3>${g.gap_id||'Gap'}: 研究缺口详情</h3>
      <div class="field"><div class="field-label">模式</div><span class="badge badge-blue">${g.pattern_id||'N/A'}</span></div>
      <div class="field"><div class="field-label">项目</div>${g.project_name||''} <span style="font-size:11px;color:var(--text-muted)">(${g.archetype||''})</span></div>
      <div class="field"><div class="field-label">描述</div><div class="field-val">${g.description||g.axis||'N/A'}</div></div>
      <div style="display:flex;gap:16px;margin-bottom:10px">
        <div><div class="field-label">缺口分数</div><span style="font-weight:700;color:${scoreColor};font-size:20px">${(sc*100).toFixed(0)}%/100</span></div>
        <div><div class="field-label">可行性</div><span style="font-weight:700">${((g.feasibility||0)*100).toFixed(0)}%</span></div>
        <div><div class="field-label">竞争度</div><span style="font-weight:700">${((g.competition||0)*100).toFixed(0)}%</span></div>
        <div><div class="field-label">跨领域</div><span style="font-weight:700">${((g.cross_archetype||0)*100).toFixed(0)}%</span></div>
      </div>
      ${supportingHtml}
    `);
  },

  _renderCountBars() {
    const c = initChart('chart-gap-count');
    if (!c) return;
    const projs = App.DATA.projects;
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 130, right: 30, top: 10, bottom: 30 },
      xAxis: { type: 'value', axisLabel: { color: fontColor() } },
      yAxis: { type: 'category', data: projs.map(p => p.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      series: [{
        type: 'bar', data: projs.map(p => p.gap_count).reverse(),
        itemStyle: { color: '#EF4444', borderRadius: [0,4,4,0] },
        label: { show: true, position: 'right', color: textColor(), fontSize: 12, fontWeight: 'bold' },
      }],
    });
  },

  _renderScoreDist() {
    const c = initChart('chart-gap-score');
    if (!c) return;
    const projs = App.DATA.projects;
    const colors = PROJECT_COLORS;
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 100, right: 20, top: 10, bottom: 55 },
      legend: { bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      xAxis: { type: 'category', data: ['最低','P25','中位','P75','最高'], axisLabel: { color: fontColor() } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { color: fontColor() } },
      series: projs.map((p, i) => {
        const scores = App.DATA.all_gaps.filter(g => g.project_id === p.id).map(g => g.score||0).sort((a,b)=>a-b);
        if (!scores.length) return { name: p.name, type: 'line', data: [] };
        return {
          name: p.name_en || p.name, type: 'line',
          data: [scores[0], scores[Math.floor(scores.length*.25)], scores[Math.floor(scores.length*.5)], scores[Math.floor(scores.length*.75)], scores[scores.length-1]],
          lineStyle: { color: colors[i] }, itemStyle: { color: colors[i] },
        };
      }),
    });
  },

  _renderHeatmap() {
    const c = initChart('chart-gap-heat');
    if (!c) return;
    const cp = App.DATA.cross_patterns;
    if (!cp || !cp.length) return;
    const projIds = App.DATA.projects.map(p => p.id);
    const heatData = [];
    const maxVal = Math.max(...cp.flatMap(r => projIds.map(pid => r[pid]||0)), 1);
    cp.forEach((row, yi) => {
      projIds.forEach((pid, xi) => {
        heatData.push([xi, yi, row[pid]||0]);
      });
    });
    c.setOption({
      tooltip: { formatter: p => `${projIds[p.value[0]]} × ${cp[p.value[1]].name}: ${p.value[2]}个` },
      grid: { left: 160, right: 40, top: 10, bottom: 30 },
      xAxis: { type: 'category', data: App.DATA.projects.map(p => p.name), axisLabel: { color: textColor(), fontSize: 10, rotate: 30 } },
      yAxis: { type: 'category', data: cp.map(r => r.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      visualMap: { min: 0, max: maxVal, calculable: true, orient: 'horizontal', left: 'center', top: 'bottom', inRange: { color: ['#DBEAFE','#3B82F6','#1E40AF'] }, textStyle: { color: fontColor() } },
      series: [{ type: 'heatmap', data: heatData, label: { show: true, color: textColor(), fontSize: 11 }, emphasis: { itemStyle: { shadowBlur: 10 } } }],
    });
  },
};
