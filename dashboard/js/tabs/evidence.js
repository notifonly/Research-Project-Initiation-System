const EvidenceTab = {
  render(el) {
    const d = App.DATA;
    el.innerHTML = `
      <div class="stats-row">
        <div class="stat-card"><div class="label">证据卡片</div><div class="value" style="color:var(--blue)">${d.meta.total_cards}</div><div class="sub">Evidence Cards</div></div>
        <div class="stat-card"><div class="label">文献来源</div><div class="value">${d.meta.total_literature}</div><div class="sub">去重后论文数</div></div>
      </div>
      <div class="chart-row">
        <div class="chart-card"><h3>各项目证据卡片/文献对比</h3><div class="chart-box" id="chart-ev-dual" style="height:380px"></div></div>
        <div class="chart-card"><h3>按研究范式汇总</h3><div class="chart-box" id="chart-ev-archetype" style="height:380px"></div></div>
      </div>
      <div class="chart-card" style="margin-bottom:16px"><h3>文献年份分布</h3><div class="chart-box" id="chart-ev-year" style="height:300px"></div></div>
      <div class="chart-card"><h3>全部文献列表（去重）</h3>
        <div style="max-height:500px;overflow-y:auto">
          <table class="sticky-table"><thead><tr><th>#</th><th>标题</th><th>期刊</th><th>年份</th><th>第一作者</th><th>引用项目</th></tr></thead>
            <tbody id="ev-lit-body"></tbody>
          </table>
        </div>
      </div>`;

    this._renderDualBars();
    this._renderArchetypePie();
    this._renderYearHist();
    this._renderLitTable();
  },

  _renderDualBars() {
    const c = initChart('chart-ev-dual');
    if (!c) return;
    const projs = App.DATA.projects;
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['证据卡片', '文献数'], bottom: 0, textStyle: { color: fontColor() } },
      grid: { left: 130, right: 30, top: 10, bottom: 40 },
      xAxis: { type: 'value', axisLabel: { color: fontColor() } },
      yAxis: { type: 'category', data: projs.map(p => p.name).reverse(), axisLabel: { color: textColor(), fontSize: 11 } },
      series: [
        { name: '证据卡片', type: 'bar', data: projs.map(p => p.total_cards).reverse(), itemStyle: { color: '#3B82F6', borderRadius: [0,4,4,0] } },
        { name: '文献数', type: 'bar', data: projs.map(p => p.literature_count||0).reverse(), itemStyle: { color: '#F59E0B', borderRadius: [0,4,4,0] } },
      ],
    });
  },

  _renderArchetypePie() {
    const c = initChart('chart-ev-archetype');
    if (!c) return;
    const aData = App.DATA.meta.archetypes.map(a => ({ value: a.total_cards, name: a.name, itemStyle: { color: a.color } }));
    c.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} cards ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%','70%'], center: ['50%','50%'],
        roseType: 'area',
        itemStyle: { borderRadius: 6 },
        label: { color: textColor(), formatter: '{b}\n{c} cards' },
        data: aData,
      }],
    });
  },

  _renderYearHist() {
    const c = initChart('chart-ev-year');
    if (!c) return;
    const years = {};
    App.DATA.projects.forEach(p => {
      (p.literature||[]).forEach(l => {
        const y = l.year;
        if (y) years[y] = (years[y]||0) + 1;
      });
    });
    const sorted = Object.entries(years).sort((a,b) => a[0]-b[0]);
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 10, bottom: 30 },
      xAxis: { type: 'category', data: sorted.map(s => s[0]), axisLabel: { color: fontColor(), rotate: 45 } },
      yAxis: { type: 'value', axisLabel: { color: fontColor() } },
      series: [{ type: 'bar', data: sorted.map(s => s[1]), itemStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'#3B82F6'},{offset:1,color:'#93C5FD'}]) }, barMaxWidth: 20 }],
    });
  },

  _renderLitTable() {
    const allPapers = {};
    const paperProjects = {};
    App.DATA.projects.forEach(p => {
      (p.literature||[]).forEach(l => {
        const key = l.doi || l.pmid || l.title;
        if (!key) return;
        if (!allPapers[key]) {
          allPapers[key] = l;
          paperProjects[key] = new Set();
        }
        paperProjects[key].add(p.name.slice(0, 20));
      });
    });

    const sorted = Object.entries(allPapers)
      .sort((a,b) => -(a[1].year||0) || a[1].title.localeCompare(b[1].title))
      .slice(0, 100);

    const tbody = document.getElementById('ev-lit-body');
    if (!tbody) return;
    tbody.innerHTML = sorted.map(([key, l], i) => {
      const authors = (l.authors||[]).slice(0, 2).join(', ') + (l.authors&&l.authors.length>2?' et al.':'');
      const projs = Array.from(paperProjects[key]||[]).join(', ');
      return `<tr>
        <td style="font-size:11px">${i+1}</td>
        <td style="max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px" title="${l.title}">${litAnchor(l, 80)}</td>
        <td style="font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.venue||''}</td>
        <td style="font-weight:600;color:var(--blue)">${l.year||'N/A'}</td>
        <td style="font-size:11px">${authors}</td>
        <td style="font-size:10px;color:var(--text-muted)">${projs}</td>
      </tr>`;
    }).join('');
  },
};
