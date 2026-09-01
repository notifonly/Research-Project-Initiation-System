const DecomposeTab = {
  activeProject: null,

  render(el) {
    const d = App.DATA;
    const dc = d.decompose;
    if (!dc || !dc.length) {
      el.innerHTML = `<div class="state-empty"><div class="icon">🧬</div><h3>暂无方向分解数据</h3><p>请先运行 scripts/decompose_directions.py 生成方向分解结果</p></div>`;
      return;
    }

    const projectMap = {};
    d.projects.forEach(p => { projectMap[p.id] = p; });

    const names = dc.map(r => {
      const p = projectMap[r.project_id];
      return p ? (p.name.length > 28 ? p.name.slice(0, 28) + '...' : p.name) : r.project_id;
    });

    if (!this.activeProject || !dc.find(r => r.project_id === this.activeProject)) {
      this.activeProject = dc[0].project_id;
    }

    var options = dc.map(r => '<option value="' + r.project_id + '"' + (r.project_id === this.activeProject ? ' selected' : '') + '>' + (projectMap[r.project_id] ? projectMap[r.project_id].name : r.project_id) + '</option>').join('');

    el.innerHTML = ''
      + '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap">'
      + '<h3 style="font-size:16px">🧬 方向分解</h3>'
      + '<select id="dc-project-sel" onchange="DecomposeTab._onProjectChange()" style="padding:6px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card);color:var(--text);font-size:13px;min-width:280px">' + options + '</select>'
      + '</div>'
      + '<div class="chart-row"><div class="chart-card"><h3>疾病×组织 候选密度热力图</h3><div class="chart-box" id="chart-dc-heatmap" style="height:420px"></div></div><div class="chart-card"><h3>文献密度分布 (钟形曲线)</h3><div class="chart-box" id="chart-dc-bell" style="height:420px"></div></div></div>'
      + '<div class="chart-row"><div class="chart-card full"><h3>五维分解轴概览</h3><div class="chart-box" id="chart-dc-axes" style="height:300px"></div></div></div>'
      + '<h3 style="margin-top:16px;margin-bottom:12px;font-size:15px">📋 Top-15 候选课题</h3>'
      + '<div class="chart-card"><div class="table-wrap" id="dc-table-wrap"></div></div>'
      + '<div id="dc-score-legend" style="margin-top:8px;font-size:11px;color:var(--text-muted);display:flex;flex-wrap:wrap;flex-direction:column;gap:4px"><div><span>评分公式: density(40%) + novelty(35%) + feasibility(25%)</span><span>&#8226;</span><span>文献密度: &lt;200 甜蜜点 | 200-1k 良 | 1k-5k 中等 | 5k-20k 较挤 | &gt;20k 拥挤</span></div><div style="opacity:0.7">文献数基于PubMed关键词检索结果总数估算，反映交叉领域竞争程度，非精准文献计量</div></div>';

    this._renderHeatmap();
    this._renderBell();
    this._renderAxes();
    this._renderTable();
  },

  _onProjectChange() {
    var sel = document.getElementById('dc-project-sel');
    if (sel) { this.activeProject = sel.value; }
    var tabEl = document.getElementById('tab-decompose');
    if (tabEl) { this.render(tabEl); }
  },

  _getProj() {
    var dc = App.DATA.decompose || [];
    for (var i = 0; i < dc.length; i++) {
      if (dc[i].project_id === this.activeProject) return dc[i];
    }
    return dc[0];
  },

  _renderHeatmap() {
    var c = initChart('chart-dc-heatmap');
    if (!c) return;
    var proj = this._getProj();
    if (!proj) return;

    var diseases = proj.dimensions.disease_phenotypes || [];
    var tissues = proj.dimensions.cell_types_tissues || [];
    var candidates = proj.candidates || [];

    if (!diseases.length || !tissues.length) {
      c.setOption({ title: { text: '此项目使用自定义分解轴，不支持标准疾病×组织热力图', left: 'center', top: 'center', textStyle: { color: fontColor(), fontSize: 14 } } });
      return;
    }

    var shortDisease = function(s) {
      if (!s) return '';
      var m = s.match(/^([^(]+)/);
      return m ? m[1].trim() : s.slice(0, 25);
    };
    var shortTissue = function(s) {
      if (!s) return '';
      var m = s.match(/^([^(]+)/);
      return m ? m[1].trim() : s.slice(0, 18);
    };

    var diseaseLabels = diseases.slice(0, 8).map(shortDisease);
    var tissueLabels = tissues.slice(0, 8).map(shortTissue);

    var matrix = [];
    for (var di = 0; di < diseaseLabels.length; di++) {
      matrix[di] = [];
      for (var ti = 0; ti < tissueLabels.length; ti++) {
        matrix[di][ti] = { score: 0, count: 0, lit: 0 };
      }
    }

    candidates.forEach(function(cd) {
      var di = diseaseLabels.indexOf(shortDisease(cd.disease));
      var ti = tissueLabels.indexOf(shortTissue(cd.tissue));
      if (di >= 0 && ti >= 0) {
        if (cd.combined_score > matrix[di][ti].score) {
          matrix[di][ti].score = cd.combined_score;
          matrix[di][ti].lit = cd.literature_count;
        }
        matrix[di][ti].count++;
      }
    });

    var data = [];
    for (var di = 0; di < diseaseLabels.length; di++) {
      for (var ti = 0; ti < tissueLabels.length; ti++) {
        var sc = Math.round(matrix[di][ti].score * 1000) / 1000;
        data.push([ti, di, sc > 0 ? sc : '-', matrix[di][ti].lit]);
      }
    }

    c.setOption({
      tooltip: {
        formatter: function(p) {
          return '<b>' + diseaseLabels[p.value[1]] + '</b> × <b>' + tissueLabels[p.value[0]] + '</b><br/>' +
            '最高分: ' + (p.value[2] === '-' ? 'N/A' : p.value[2].toFixed(3)) + '<br/>文献: ' + p.value[3];
        }
      },
      grid: { left: 100, right: 40, top: 10, bottom: 80 },
      xAxis: {
        type: 'category', data: tissueLabels,
        axisLabel: { color: fontColor(), fontSize: 10, rotate: 30, formatter: function(v) { return v.length > 14 ? v.slice(0, 13) + '...' : v; } },
      },
      yAxis: {
        type: 'category', data: diseaseLabels.reverse(),
        axisLabel: { color: fontColor(), fontSize: 10 },
      },
      visualMap: {
        min: 0.30, max: 0.90, calculable: true,
        orient: 'horizontal', left: 'center', bottom: 0,
        inRange: { color: ['#e2e8f0', '#93c5fd', '#3B82F6', '#1d4ed8'] },
        textStyle: { color: fontColor(), fontSize: 10 },
        formatter: function(v) { return v.toFixed(2); },
      },
      series: [{
        name: 'Score', type: 'heatmap',
        data: data.filter(function(d) { return d[2] !== '-'; }),
        label: { show: true, color: textColor(), fontSize: 9 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
      }],
    });
  },

  _renderBell() {
    var c = initChart('chart-dc-bell');
    if (!c) return;
    var proj = this._getProj();
    if (!proj) return;
    var candidates = proj.candidates || [];

    var densityBuckets = [
      { label: '0-5 (过疏)', range: [0, 5], candidates: [] },
      { label: '5-30 (稀疏)', range: [6, 30], candidates: [] },
      { label: '30-200 (甜蜜点)', range: [30, 200], candidates: [] },
      { label: '200-1k (良)', range: [200, 1000], candidates: [] },
      { label: '1k-5k (中等)', range: [1000, 5000], candidates: [] },
      { label: '5k-20k (较挤)', range: [5000, 20000], candidates: [] },
      { label: '20k+ (拥挤)', range: [20000, 1e9], candidates: [] },
    ];

    candidates.forEach(function(cd) {
      for (var i = 0; i < densityBuckets.length; i++) {
        if (cd.literature_count >= densityBuckets[i].range[0] && cd.literature_count <= densityBuckets[i].range[1]) {
          densityBuckets[i].candidates.push(cd);
          break;
        }
      }
    });

    var colors = ['#94a3b8', '#93c5fd', '#3B82F6', '#10B981', '#F59E0B', '#F97316', '#EF4444'];
    var barData = [], avgScoreData = [];
    densityBuckets.forEach(function(b, i) {
      barData.push({ value: b.candidates.length, itemStyle: { color: colors[i] } });
      var sum = 0;
      b.candidates.forEach(function(cd) { sum += cd.combined_score; });
      avgScoreData.push(b.candidates.length ? Math.round(sum / b.candidates.length * 1000) / 1000 : 0);
    });

    c.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function(params) {
          var idx = params[0].dataIndex;
          var b = densityBuckets[idx];
          return '<b>' + b.label + '</b><br/>候选数: ' + b.candidates.length + '<br/>平均分: ' + avgScoreData[idx].toFixed(3);
        }
      },
      legend: { data: ['候选数', '平均分'], bottom: 0, textStyle: { color: fontColor(), fontSize: 10 } },
      grid: { left: 50, right: 50, top: 30, bottom: 55 },
      xAxis: {
        type: 'category',
        data: densityBuckets.map(function(b) { return b.label; }),
        axisLabel: { color: fontColor(), fontSize: 10, rotate: 15 },
      },
      yAxis: [
        { type: 'value', name: '候选数', axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor(), fontSize: 10 }, splitLine: { lineStyle: { color: 'var(--border)' } } },
        { type: 'value', name: '平均分', max: 0.9, min: 0.2, axisLabel: { color: fontColor() }, nameTextStyle: { color: textColor(), fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: '候选数', type: 'bar', data: barData, barWidth: '40%' },
        { name: '平均分', type: 'line', yAxisIndex: 1, data: avgScoreData, smooth: true, lineStyle: { color: '#8B5CF6', width: 2 }, itemStyle: { color: '#8B5CF6' }, symbol: 'circle', symbolSize: 6 },
      ],
    });
  },

  _renderAxes() {
    var c = initChart('chart-dc-axes');
    if (!c) return;
    var proj = this._getProj();
    if (!proj) return;
    var dims = proj.dimensions;

    var hasStdDims = dims.disease_phenotypes || dims.cell_types_tissues || dims.methods_techniques || dims.data_resources || dims.populations;
    if (!hasStdDims) {
      c.setOption({ title: { text: '此项目使用自定义分解轴，标准五维概览不适用', left: 'center', top: 'center', textStyle: { color: fontColor(), fontSize: 14 } } });
      return;
    }

    var axes = [
      { name: 'diseases', label: '疾病', items: (dims.disease_phenotypes || []).slice(0, 4).map(function(s) { var m = s.match(/^([^(]+)/); return m ? m[1].trim() : s.slice(0, 14); }) },
      { name: 'tissues', label: '组织/细胞', items: (dims.cell_types_tissues || []).slice(0, 4).map(function(s) { var m = s.match(/^([^(]+)/); return m ? m[1].trim() : s.slice(0, 14); }) },
      { name: 'methods', label: '方法', items: (dims.methods_techniques || []).slice(0, 4).map(function(s) { var m = s.match(/^([^(]+)/); return m ? m[1].trim() : s.slice(0, 14); }) },
      { name: 'data', label: '数据', items: (dims.data_resources || []).slice(0, 4).map(function(s) { var m = s.match(/^([^(]+)/); return m ? m[1].trim() : s.slice(0, 14); }) },
      { name: 'pop', label: '人群', items: (dims.populations || []).slice(0, 4).map(function(s) { var m = s.match(/^([^(]+)/); return m ? m[1].trim() : s.slice(0, 14); }) },
    ];

    var axisColors = ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899'];
    var series = [];
    var allMax = 0;

    axes.forEach(function(ax, ai) {
      allMax = Math.max(allMax, ax.items.length);
      var data = [];
      ax.items.forEach(function(item, i) {
        data.push({ name: item, value: ax.items.length - i });
      });
      series.push({
        name: ax.label, type: 'bar', barGap: '20%',
        data: data,
        itemStyle: { color: axisColors[ai], borderRadius: [2, 2, 0, 0] },
        emphasis: { focus: 'series' },
      });
    });

    c.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      grid: { left: 30, right: 30, top: 10, bottom: 55 },
      xAxis: { type: 'value', show: false, max: allMax + 1 },
      yAxis: { type: 'category', data: axes.map(function(a) { return a.label; }), axisLabel: { color: textColor(), fontSize: 12, fontWeight: 'bold' }, axisLine: { show: false }, axisTick: { show: false } },
      series: series.map(function(s) {
        return Object.assign({}, s, { label: { show: true, position: 'inside', color: '#fff', fontSize: 9, formatter: function(p) { return p.name; } } });
      }),
    });
  },

  _renderTable() {
    var el = document.getElementById('dc-table-wrap');
    if (!el) return;
    var proj = this._getProj();
    if (!proj) return;

    var candidates = (proj.candidates || []).slice(0, 15);
    var shortMethod = function(s) {
      var m = s.match(/^([^(]+)/);
      var name = m ? m[1].trim() : s.slice(0, 22);
      return name.length > 22 ? name.slice(0, 21) + '...' : name;
    };

    function scoreColor(sc) {
      if (sc >= 0.8) return 'var(--green)';
      if (sc >= 0.5) return 'var(--blue)';
      if (sc >= 0.35) return 'var(--amber)';
      return 'var(--red)';
    }

    var rows = candidates.map(function(cd, i) {
      var dName = cd.disease || '—';
      var m = dName.match(/^([^(]+)/);
      dName = m ? m[1].trim() : dName.slice(0, 30);
      dName = dName.length > 28 ? dName.slice(0, 27) + '...' : dName;
      var tissueText = cd.tissue || '—';
      var methodText = cd.method || '—';

      return '<tr>'
        + '<td style="font-weight:700;color:' + scoreColor(cd.combined_score) + '">' + cd.combined_score.toFixed(3) + '</td>'
        + '<td title="' + (cd.disease || '').replace(/"/g, '&quot;') + '">' + dName + '</td>'
        + '<td title="' + (cd.tissue || '').replace(/"/g, '&quot;') + '">' + tissueText.slice(0, 25) + (tissueText.length > 25 ? '...' : '') + '</td>'
        + '<td title="' + (cd.method || '').replace(/"/g, '&quot;') + '">' + (typeof shortMethod === 'function' ? shortMethod(methodText) : methodText.slice(0, 22)) + '</td>'
        + '<td>' + (cd.literature_count >= 1000 ? (cd.literature_count/1000).toFixed(1) + 'k' : cd.literature_count) + '</td>'
        + '</tr>';
    }).join('');

    el.innerHTML = '<table class="sticky-table"><thead><tr><th>评分</th><th>疾病</th><th>组织</th><th>方法</th><th>文献数</th></tr></thead><tbody>' + rows + '</tbody></table>';
  },
};
