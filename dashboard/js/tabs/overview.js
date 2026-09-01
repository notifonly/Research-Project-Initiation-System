const OverviewTab = {
  render(el) {
    const d = App.DATA;
    const m = d.meta;

    el.innerHTML = `
      <div class="stats-row">
        <div class="stat-card" style="border-left:3px solid var(--blue)"><div class="label">证据卡片</div><div class="value">${m.total_cards}</div><div class="sub">${m.total_literature} 篇文献</div></div>
        <div class="stat-card" style="border-left:3px solid var(--red)"><div class="label">研究缺口</div><div class="value">${m.total_gaps}</div><div class="sub">${Object.keys(d.gap_patterns).length} 种模式</div></div>
        <div class="stat-card" style="border-left:3px solid var(--green)"><div class="label">研究假设</div><div class="value">${m.total_hypotheses}</div><div class="sub">7个方向 × 5假设</div></div>
        <div class="stat-card"><div class="label">研究范式</div><div class="value">${m.archetypes.length}</div><div class="sub">V2G / PRS / scAI / Omics</div></div>
      </div>

      <div class="chart-row">
        <div class="chart-card"><h3>研究项目全景对比</h3><div class="chart-box" id="chart-ov-radar" style="height:400px"></div></div>
        <div class="chart-card"><h3>管线完成进度</h3><div class="chart-box" id="chart-ov-progress" style="height:400px"></div></div>
      </div>

      <h3 style="margin-bottom:12px;font-size:16px">📋 研究方向详情</h3>
      <div class="project-cards" id="project-cards"></div>

      <div class="chart-card" style="margin-top:16px">
        <h3>项目指标总览</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>项目</th><th>范式</th><th>证据卡</th><th>文献</th><th>Gap</th><th>假设</th><th>进度</th><th>耗时</th></tr></thead>
          <tbody>${d.projects.map(p => {
            const badgeCls = getArchetypeBadgeClass(p.archetype_id);
            const pct = p.progress?.percent || 0;
            return `<tr class="cursor" onclick="OverviewTab.focusProject('${p.id}')">
              <td><strong>${p.name}</strong></td>
              <td><span class="badge ${badgeCls}">${p.archetype}</span></td>
              <td style="font-weight:700;color:var(--blue)">${p.total_cards}</td>
              <td>${p.literature_count||0}</td>
              <td>${p.gap_count}</td>
              <td>${p.hypothesis_count}</td>
              <td><div style="display:flex;align-items:center;gap:6px"><div class="progress-bar" style="width:60px;margin:0"><div class="fill" style="width:${pct}%;background:var(--blue)"></div></div>${pct}%</div></td>
              <td>${p.duration_s.toFixed(0)}s</td>
            </tr>`;
          }).join('')}</tbody>
        </table></div>
      </div>`;

    this._renderRadar();
    this._renderProgress();
    this._renderProjectCards();
  },

  _renderRadar() {
    const c = initChart('chart-ov-radar');
    if (!c) return;
    const projects = App.DATA.projects;
    const maxCards = Math.max(...projects.map(p => p.total_cards), 1);
    const maxGaps = Math.max(...projects.map(p => p.gap_count), 1);
    const maxHyps = Math.max(...projects.map(p => p.hypothesis_count), 1);
    const maxLit = Math.max(...projects.map(p => p.literature_count||0), 1);

    const indicator = [
      { name: '证据卡片', max: maxCards },
      { name: '文献数量', max: maxLit },
      { name: '研究缺口', max: maxGaps },
      { name: '研究假设', max: maxHyps },
      { name: '管线进度%', max: 100 },
    ];

    const series = projects.map((p, i) => ({
      name: p.name_en || p.name,
      type: 'radar',
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { color: PROJECT_COLORS[i], width: 1 },
      areaStyle: { color: PROJECT_COLORS[i], opacity: 0.1 },
      itemStyle: { color: PROJECT_COLORS[i] },
      data: [{
        value: [p.total_cards, p.literature_count||0, p.gap_count, p.hypothesis_count, p.progress?.percent||0],
        name: p.name_en || p.name,
      }],
    }));

    c.setOption({
      tooltip: {},
      legend: { bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      radar: {
        center: ['50%', '40%'],
        radius: '60%',
        indicator,
        axisName: { color: textColor(), fontSize: 11 },
        splitArea: { areaStyle: { color: ['var(--bg)', 'var(--bg-alt)' in { 'var(--bg)': '#f8fafc', 'var(--bg-alt)': '#f1f5f9' } ? [] : []] } },
      },
      series,
    });
  },

  _renderProgress() {
    const c = initChart('chart-ov-progress');
    if (!c) return;
    const projects = App.DATA.projects;
    c.setOption({
      tooltip: { trigger: 'axis', formatter: p => `${p.name}<br/>${p.value}%` },
      grid: { left: 130, right: 40, top: 10, bottom: 30 },
      xAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: fontColor(), formatter: '{value}%' } },
      yAxis: { type: 'category', data: projects.map(p => p.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      series: [{
        type: 'bar',
        data: projects.map(p => {
          const pct = p.progress?.percent || 0;
          return { value: pct, itemStyle: { color: p.converged ? '#10B981' : pct > 50 ? '#F59E0B' : '#3B82F6', borderRadius: [0,4,4,0] } };
        }).reverse(),
        label: { show: true, position: 'right', formatter: '{c}%', color: textColor(), fontSize: 11 },
      }],
    });
  },

  _renderProjectCards() {
    const container = document.getElementById('project-cards');
    if (!container) return;
    const d = App.DATA;

    container.innerHTML = d.projects.map(p => {
      const color = getArchetypeColor(p.archetype_id);
      const badgeCls = getArchetypeBadgeClass(p.archetype_id);
      const pct = p.progress?.percent || 0;
      return `<div class="project-card" onclick="OverviewTab.focusProject('${p.id}')">
        <div class="card-header">
          <div><span class="badge ${badgeCls}" style="margin-bottom:6px;display:inline-block">${p.archetype}</span><h4>${p.name}</h4></div>
          <div style="font-size:12px;color:var(--text-muted)">${p.total_cards}卡</div>
        </div>
        <div class="card-body">
          <div class="desc" title="${p.research_direction||''}">${p.research_direction || '暂无研究方向描述'}</div>
          <div class="progress-bar"><div class="fill" style="width:${pct}%;background:${color}"></div></div>
          <div class="card-stats">
            <div class="card-stat"><div class="stat-val">${p.total_cards}</div><div class="stat-lbl">证据卡片</div></div>
            <div class="card-stat"><div class="stat-val">${p.gap_count}</div><div class="stat-lbl">研究缺口</div></div>
            <div class="card-stat"><div class="stat-val">${p.hypothesis_count}</div><div class="stat-lbl">研究假设</div></div>
            <div class="card-stat"><div class="stat-val">${p.literature_count||0}</div><div class="stat-lbl">文献</div></div>
          </div>
          ${p.literature && p.literature.length > 0 ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 代表文献: ${litAnchor(p.literature[0], 50)}</div>` : ''}
        </div>
      </div>`;
    }).join('');
  },

  focusProject(pid) {
    const p = App.DATA.projects.find(pr => pr.id === pid);
    if (!p) return;

    const badgeCls = getArchetypeBadgeClass(p.archetype_id);
    const color = getArchetypeColor(p.archetype_id);

    let lithtml = '';
    if (p.literature && p.literature.length) {
      lithtml = `<div class="field"><div class="field-label">代表性文献 (${p.literature_count||0}篇)</div>
        <div class="lit-list">${p.literature.map(l => `<div class="lit-item"><span class="lit-year">${l.year||''}</span>
          ${litAnchor(l, 80)} <span class="lit-venue">${l.venue}</span><br><span class="lit-authors">${(l.authors||[]).slice(0,3).join(', ')}${l.authors&&l.authors.length>3?' et al.':''}</span>
          ${litLink(l) ? `<a href="${litLink(l)}" target="_blank" rel="noopener" style="font-size:11px;color:var(--blue)">📎 原文</a>` : l.doi ? `<a href="https://doi.org/${l.doi}" target="_blank" style="font-size:11px;color:var(--blue)">DOI</a>` : ''}</div>`).join('')}</div></div>`;
    }

    let gaphs = '';
    if (p.hypotheses && p.hypotheses.length) {
      gaphs = `<div class="field"><div class="field-label">研究假设</div>
        ${p.hypotheses.map(h => `<div style="margin-bottom:8px;padding:8px;background:var(--bg-alt);border-radius:6px;font-size:13px">
          <strong>${h.statement}</strong>
          <div style="display:flex;gap:12px;margin-top:4px;font-size:11px;color:var(--text-muted)">
            <span>创新性: ${(h.novelty_score||0).toFixed(2)}</span>
            <span>可行性: ${(h.feasibility_score||0).toFixed(2)}</span>
            <span>影响: ${h.expected_impact||'N/A'}</span>
          </div>
          ${h.rationale ? `<div style="margin-top:4px;font-size:11px;color:var(--text-muted)">${h.rationale.slice(0,200)}</div>` : ''}
        </div>`).join('')}</div>`;
    }

    showModal(`
      <button class="close" onclick="closeModal()">✕</button>
      <h3>${p.icon||'🧬'} ${p.name}</h3>
      <div class="field"><span class="badge ${badgeCls}">${p.archetype}</span> <span style="font-size:12px;color:var(--text-muted);margin-left:8px">${p.id}</span></div>
      <div class="field"><div class="field-label">研究方向</div><div class="field-val">${p.research_direction||'N/A'}</div></div>
      <div class="field" style="display:flex;gap:16px">
        <div><div class="field-label">证据卡片</div><span style="font-weight:700;color:var(--blue);font-size:18px">${p.total_cards}</span></div>
        <div><div class="field-label">研究缺口</div><span style="font-weight:700;color:var(--red);font-size:18px">${p.gap_count}</span></div>
        <div><div class="field-label">假设</div><span style="font-weight:700;color:var(--green);font-size:18px">${p.hypothesis_count}</span></div>
        <div><div class="field-label">管线进度</div><span style="font-weight:700;font-size:18px">${p.progress?.percent||0}%</span></div>
      </div>
      ${gaphs}
      ${lithtml}
    `);
  },
};
