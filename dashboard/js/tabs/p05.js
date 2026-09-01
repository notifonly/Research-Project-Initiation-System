const P05Tab = {
  // 评分维度（优先从 data.json dimensions 读取，回退到硬编码以对齐 scripts/p05_harness/validators/rubric.py RUBRIC_DIMENSIONS）
  DIM_KEYS: [],

  DIM_LABELS: {
    literature_coverage: '文献覆盖度',
    technical_feasibility: '技术可行性',
    innovation_clarity: '创新性清晰度',
    data_accessibility: '数据可及性',
    gap_alignment: '缺口对齐度',
    evaluation_rigor: '评估严谨性',
  },
  DIM_COLORS: ['#3B82F6', '#8B5CF6', '#F59E0B', '#10B981', '#EC4899', '#06B6D4'],

  _initDims() {
    var dims = (App.DATA.p05_research_plans && App.DATA.p05_research_plans.dimensions);
    if (dims && dims.length) {
      this.DIM_KEYS = dims.map(function(d) { return d.key; });
      dims.forEach(function(d) {
        if (!this.DIM_LABELS[d.key]) { this.DIM_LABELS[d.key] = d.label_zh; }
      }, this);
    } else {
      this.DIM_KEYS = ['literature_coverage', 'technical_feasibility', 'innovation_clarity', 'data_accessibility', 'gap_alignment', 'evaluation_rigor'];
    }
  },

  // 新颖性判定展示映射（与 phase15_novelty_verify.Verdict 对齐）
  VERDICT_MAP: {
    scooped: { label: 'scooped 被抢先', color: 'var(--red)', icon: '❌' },
    crowded: { label: 'crowded 拥挤', color: 'var(--red)', icon: '⚠️' },
    adjacent: { label: 'adjacent 邻近', color: 'var(--yellow)', icon: 'ℹ️' },
    clear: { label: 'clear 清晰', color: 'var(--green)', icon: '✅' },
    insufficient_evidence: { label: '证据不足', color: 'var(--text-muted)', icon: '❓' },
  },

  _verdictBadge(verdict, papersFound) {
    var v = this.VERDICT_MAP[verdict] || { label: verdict || '未验证', color: 'var(--text-muted)', icon: '' };
    var extra = (papersFound != null) ? ' (' + papersFound + '篇)' : '';
    return '<span style="font-size:10px;font-weight:600;color:' + v.color + '" title="新颖性判定: ' + v.label + extra + '">' + v.icon + ' ' + v.label + '</span>';
  },

  render(el) {
    const plans = App.DATA.p05_research_plans;
    if (!plans || !plans.candidates || !plans.candidates.length) {
      el.innerHTML = '<div class="state-empty"><div class="icon">🧪</div><h3>暂无 P05 方案质量数据</h3><p>请先运行 python scripts/p05_harness/main.py 生成研究方案验收结果</p></div>';
      return;
    }

    this._initDims();

    const dimLabels = this.DIM_LABELS;
    const dimKeys = this.DIM_KEYS;
    const avg = plans.dimension_averages || {};
    const dimColors = this.DIM_COLORS;

    var avgHTML = dimKeys.map(function(k, i) {
      var v = avg[k];
      if (v != null) {
        return '<div class="stat-card"><div class="label">' + dimLabels[k] + '</div><div class="value" style="color:' + dimColors[i] + ';font-size:22px">' + v.toFixed(1) + '</div><div class="sub">/ 5.0</div></div>';
      } else {
        return '<div class="stat-card"><div class="label">' + dimLabels[k] + '</div><div class="value" style="color:var(--text-muted);font-size:20px">-</div><div class="sub">暂无评分数据</div></div>';
      }
    }).join('');

    el.innerHTML = ''
      + '<h3 style="font-size:16px;margin-bottom:16px">🧪 P05 研究方案质量验收</h3>'
      + '<div class="stats-row">'
      + '<div class="stat-card"><div class="label">通过</div><div class="value" style="color:var(--green)">' + plans.passed_count + '</div><div class="sub">threshold ≥ 4.0</div></div>'
      + '<div class="stat-card"><div class="label">未通过</div><div class="value" style="color:var(--red)">' + plans.failed_count + '</div><div class="sub">max 3 rounds</div></div>'
      + '<div class="stat-card"><div class="label">LLM 调用</div><div class="value">' + plans.total_llm_calls + '</div><div class="sub">总计</div></div>'
      + '<div class="stat-card"><div class="label">MCP 调用</div><div class="value">' + plans.total_mcp_calls + '</div><div class="sub">总计</div></div>'
      + '<div class="stat-card"><div class="label">耗时</div><div class="value">' + (plans.total_duration_s / 60).toFixed(1) + ' min</div><div class="sub">总计</div></div>'
      + '</div>'
      + '<div class="stats-row">' + avgHTML + '</div>'
      + '<div class="chart-row">'
      + '<div class="chart-card full"><h3>候选方案评分概览</h3><div class="chart-box" id="chart-p05-scores" style="height:300px"></div></div>'
      + '</div>'
      + '<h3 style="margin-top:16px;margin-bottom:12px;font-size:15px">📋 深度分析候选 (' + plans.candidates.length + ' 个)</h3>'
      + '<div class="chart-card"><div class="table-wrap" id="p05-table-wrap"></div></div>';

    this._renderScoreBar();
    this._renderCandidateGrid();
  },

  _renderScoreBar() {
    var c = initChart('chart-p05-scores');
    if (!c) return;
    var plans = App.DATA.p05_research_plans;
    if (!plans) return;

    var cands = plans.candidates.slice().sort(function(a, b) { return b.final_score - a.final_score; });
    var cats = cands.map(function(cd) { return cd.candidate_id.replace('p05_sc_multiomics_ai_', ''); });
    var dimKeys = P05Tab.DIM_KEYS;
    var dimNames = dimKeys.map(function(k) { return P05Tab.DIM_LABELS[k]; });
    var dimColors = P05Tab.DIM_COLORS;

    c.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: dimNames, bottom: 0, textStyle: { color: fontColor(), fontSize: 10 }, type: 'scroll' },
      grid: { left: 60, right: 20, top: 10, bottom: 55 },
      xAxis: { type: 'category', data: cats, axisLabel: { color: textColor(), fontSize: 11, rotate: 30 }, axisTick: { alignWithLabel: true } },
      yAxis: { type: 'value', min: 0, max: 5, axisLabel: { color: fontColor() }, splitLine: { lineStyle: { color: 'var(--border)' } } },
      series: dimKeys.map(function(k, i) {
        return {
          name: dimNames[i],
          type: 'bar',
          barMaxWidth: 14,
          emphasis: { focus: 'series' },
          itemStyle: { color: dimColors[i] },
          data: cands.map(function(cd) {
            var sc = 0;
            if (cd.iterations && cd.iterations.length) {
              // 展示交付方案（最高分轮）的维度分
              var best = cd.iterations.reduce(function(a, b) { return (b.weighted_score > (a ? a.weighted_score : -1)) ? b : a; }, null);
              sc = ((best && best.scores) || {})[k] || 0;
            }
            return sc;
          }),
        };
      }),
    });
  },

  _renderCandidateGrid() {
    var el = document.getElementById('p05-table-wrap');
    if (!el) return;
    var plans = App.DATA.p05_research_plans;
    var cands = plans.candidates.slice().sort(function(a, b) { return b.final_score - a.final_score; });

    var dimKeys = P05Tab.DIM_KEYS;

    var scoreDot = function(v) {
      var c = v >= 4 ? 'var(--green)' : v >= 3 ? 'var(--yellow)' : 'var(--red)';
      return '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c + ';margin-right:2px" title="' + v.toFixed(1) + '"></span>';
    };

    var html = '<div style="display:flex;flex-wrap:wrap;gap:12px">';
    for (var i = 0; i < cands.length; i++) {
      var cd = cands[i];
      var shortId = cd.candidate_id.replace('p05_sc_multiomics_ai_', '');
      var passedCls = cd.passed ? 'impact-rev' : 'impact-med';
      var passedLabel = cd.passed ? '通过' : '未通过';
      var rqFull = cd.research_question || '';
      var rq = rqFull.length > 120 ? rqFull.slice(0, 120) + '...' : rqFull;
      var dimDots = dimKeys.map(function(k) {
        var v = 0;
        if (cd.iterations && cd.iterations.length) {
          var best = cd.iterations.reduce(function(a, b) { return (b.weighted_score > (a ? a.weighted_score : -1)) ? b : a; }, null);
          v = ((best && best.scores) || {})[k] || 0;
        }
        return scoreDot(v);
      }).join('');

      // 新颖性判定 + 红队高风险徽标 + 证据锚定徽标
      var nv = cd.novelty_verdict || {};
      var rt = cd.redteam_result || {};
      var nvBadge = nv.overall_verdict ? P05Tab._verdictBadge(nv.overall_verdict, nv.papers_found) : '';
      var rtBadge = '';
      if (rt.high_count != null && (rt.high_count > 0 || rt.medium_count > 0)) {
        var rtColor = rt.high_count > 0 ? 'var(--red)' : 'var(--yellow)';
        rtBadge = '<span style="font-size:10px;font-weight:600;color:' + rtColor + '" title="红队发现: ' + rt.high_count + ' 高 / ' + (rt.medium_count || 0) + ' 中 / ' + (rt.low_count || 0) + ' 低">🛡️ ' + rt.high_count + 'H ' + (rt.medium_count || 0) + 'M</span>';
      }
      var evLink = cd.evidence_link || {};
      var evBadge = '';
      if (evLink.evidence_source === 'fallback_pool') {
        evBadge = '<span style="font-size:10px;font-weight:600;color:var(--amber)" title="无候选专属证据卡，已回退到全库证据卡池 (' + (evLink.evidence_pool_size || 0) + ' 张)">📎 全库</span>';
      } else if (evLink.linked_card_count > 0) {
        evBadge = '<span style="font-size:10px;font-weight:600;color:var(--green)" title="已锚定 ' + evLink.linked_card_count + ' 张专属证据卡">📎 ' + evLink.linked_card_count + ' 卡</span>';
      }

      html += '<div class="stat-card cursor" onclick="P05Tab.showDetail(' + i + ')" style="flex:1 1 300px;min-width:280px;max-width:360px;padding:14px;transition:box-shadow .2s">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        + '<code style="font-size:13px;font-weight:700">' + shortId + '</code>'
        + '<div style="display:flex;align-items:center;gap:8px">'
        + '<span class="impact-tag ' + passedCls + '" style="font-size:10px">' + passedLabel + '</span>'
        + '<span style="font-weight:700;font-size:18px;color:' + (cd.final_score >= 4 ? 'var(--green)' : cd.final_score >= 3.5 ? 'var(--yellow)' : 'var(--red)') + '">' + cd.final_score.toFixed(2) + '</span>'
        + '</div></div>'
        + '<div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:8px" title="' + rqFull.replace(/"/g, '&quot;') + '">' + rq + '</div>'
        + '<div style="display:flex;align-items:center;gap:4px;margin-bottom:4px">' + dimDots + '<span style="font-size:10px;color:var(--text-muted);margin-left:4px">' + (cd.iterations ? cd.iterations.length : 0) + ' 轮</span></div>'
        + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px">' + nvBadge + rtBadge + evBadge + '</div>'
        + '<div style="font-size:10px;color:var(--text-muted)">' + (cd.method || '') + ' | ' + (cd.disease || '') + '</div>'
        + '</div>';
    }
    html += '</div>';
    el.innerHTML = html;
  },

  showDetail(idx) {
    var cands = App.DATA.p05_research_plans.candidates.slice().sort(function(a, b) { return b.final_score - a.final_score; });
    var cd = cands[idx];
    if (!cd) return;

    var dimKeys = P05Tab.DIM_KEYS;
    var dimNames = dimKeys.map(function(k) { return P05Tab.DIM_LABELS[k]; });

    var shortId = cd.candidate_id.replace('p05_sc_multiomics_ai_', '');
    var passedCls = cd.passed ? 'impact-rev' : 'impact-med';
    var passedLabel = cd.passed ? '通过' : '未通过';
    var finalColor = cd.final_score >= 4 ? 'var(--green)' : cd.final_score >= 3.5 ? 'var(--yellow)' : 'var(--red)';

    var iterRows = '';
    if (cd.iterations && cd.iterations.length) {
      for (var ii = 0; ii < cd.iterations.length; ii++) {
        var it = cd.iterations[ii];
        var s = it.scores || {};
        var cells = dimKeys.map(function(k) { return '<td style="text-align:center">' + (s[k] != null ? s[k].toFixed(1) : '-') + '</td>'; }).join('');
        iterRows += '<tr style="' + (it.passed ? 'background:rgba(16,185,129,0.15)' : '') + '"><td style="text-align:center">R' + (it.iteration + 1) + '</td>' + cells + '<td style="text-align:center;font-weight:700">' + it.weighted_score.toFixed(2) + '</td><td style="text-align:center">' + (it.passed ? '✅' : '') + '</td></tr>';
      }
    }

    // ── 新颖性验证 ──
    var noveltyHTML = P05Tab._renderNoveltySection(cd);

    // ── 红队评审 ──
    var redteamHTML = P05Tab._renderRedteamSection(cd);

    // ── 评审意见 ──
    var critiqueHTML = '';
    if (cd.critique_text) {
      critiqueHTML = '<h4 style="margin-top:20px;margin-bottom:8px">💬 评审意见（交付轮）</h4>'
        + '<div class="field" style="font-size:12px;line-height:1.7;color:var(--text);white-space:pre-wrap">' + cd.critique_text + '</div>';
      if (cd.detailed_feedback && Object.keys(cd.detailed_feedback).length) {
        critiqueHTML += '<div style="margin-top:6px">';
        var fbKeys = Object.keys(cd.detailed_feedback);
        for (var fi = 0; fi < fbKeys.length; fi++) {
          var flabel = P05Tab.DIM_LABELS[fbKeys[fi]] || fbKeys[fi];
          var ftext = String(cd.detailed_feedback[fbKeys[fi]]);
          var fshort = ftext.length > 300 ? ftext.slice(0, 300) + '...' : ftext;
          critiqueHTML += '<div style="font-size:11px;margin-bottom:4px"><b style="color:var(--blue)">' + flabel + ':</b> <span style="color:var(--text-muted)" title="' + ftext.replace(/"/g, '&quot;') + '">' + fshort + '</span></div>';
        }
        critiqueHTML += '</div>';
      }
    }

    // ── 引用验证 ──
    var citeHTML = '';
    if (cd.citation_checks && cd.citation_checks.length) {
      var verifiedN = cd.citation_checks.filter(function(x) { return x.exists; }).length;
      var notFoundN = cd.citation_checks.filter(function(x) { return !x.exists && x.status !== 'unverifiable'; }).length;
      var unverifiableN = cd.citation_checks.filter(function(x) { return x.status === 'unverifiable'; }).length;
      citeHTML = '<h4 style="margin-top:20px;margin-bottom:8px">🔗 引用验证 (' + verifiedN + '/' + cd.citation_checks.length + ' 通过'
        + (notFoundN ? ', <span style="color:var(--red)">疑似幻觉 ' + notFoundN + '</span>' : '')
        + (unverifiableN ? ', <span style="color:var(--amber)">待人工核实 ' + unverifiableN + '</span>' : '')
        + ')</h4>';
      for (var ci = 0; ci < cd.citation_checks.length; ci++) {
        var chk = cd.citation_checks[ci];
        var icon = chk.exists ? '✅' : (chk.status === 'unverifiable' ? '❓' : '❌');
        var disp = chk.display || chk.doi || chk.pmid || chk.accession || '?';
        citeHTML += '<div style="font-size:11px;margin-bottom:2px">' + icon + ' <code>' + disp + '</code>'
          + (chk.verified_title ? ' <span style="color:var(--text-muted)" title="' + String(chk.verified_title).replace(/"/g, '&quot;') + '">→ ' + chk.verified_title.slice(0, 80) + (chk.verified_title.length > 80 ? '...' : '') + '</span>' : '')
          + (!chk.exists && chk.error ? ' <span style="color:' + (chk.status === 'unverifiable' ? 'var(--amber)' : 'var(--red)') + '">' + chk.error + '</span>' : '')
          + '</div>';
      }
    }

    var roadmapHTML = '';
    if (cd.technical_roadmap && cd.technical_roadmap.length) {
      roadmapHTML = '<h4 style="margin-top:20px;margin-bottom:8px">🛠️ 技术路线 (' + cd.technical_roadmap.length + ' 步, 总计 ' + cd.technical_roadmap.reduce(function(acc, s) { return acc + (s.weeks || 0); }, 0) + ' 周)</h4>';
      for (var ri = 0; ri < cd.technical_roadmap.length; ri++) {
        var step = cd.technical_roadmap[ri];
        roadmapHTML += '<details class="field" style="margin-bottom:6px"><summary style="cursor:pointer;font-weight:600;font-size:13px;padding:4px 0">Step ' + (step.step || ri + 1) + ': ' + (step.title || '') + ' <span style="font-size:10px;color:var(--text-muted)">(' + (step.weeks || '?') + 'w)</span></summary>'
          + '<div style="padding:8px 0 4px 16px;font-size:12px;line-height:1.6;color:var(--text-muted)">' + (step.desc || '') + '</div>'
          + (step.methods ? '<div style="padding:0 0 4px 16px;font-size:11px;color:var(--blue)"><b>方法:</b> ' + step.methods + '</div>' : '')
          + (step.tools && step.tools.length ? '<div style="padding:0 0 4px 16px"><b style="font-size:11px">工具:</b> ' + step.tools.map(function(t) { return '<span class="badge badge-blue" style="margin:1px">' + t + '</span>'; }).join('') + '</div>' : '')
          + (step.expected_output ? '<div style="padding:0 0 4px 16px;font-size:11px;color:var(--green)"><b>产出:</b> ' + step.expected_output + '</div>' : '')
          + '</details>';
      }
    }

    var dataHTML = '';
    if (cd.data_sources_detail && cd.data_sources_detail.length) {
      dataHTML = '<h4 style="margin-top:20px;margin-bottom:8px">📦 数据源 (' + cd.data_sources_detail.length + ' 个)</h4>';
      for (var di = 0; di < cd.data_sources_detail.length; di++) {
        var ds = cd.data_sources_detail[di];
        dataHTML += '<div class="field" style="margin-bottom:4px;padding:6px 10px;background:var(--bg-alt);border-radius:6px;font-size:12px">'
          + '<b>' + (ds.name || 'Unnamed') + '</b>'
          + ' <span class="badge" style="font-size:10px">' + (ds.access || '?') + '</span>'
          + ' <span style="font-size:10px;color:var(--text-muted)">' + (ds.format || '') + ' | ' + (ds.size || '') + '</span>'
          + (ds.url ? '<br/><a href="' + ds.url + '" target="_blank" style="font-size:10px;color:var(--blue)">' + ds.url + '</a>' : '')
          + (ds.note ? '<br/><span style="font-size:10px;color:var(--text-muted)">' + ds.note + '</span>' : '')
          + '</div>';
      }
    }

    var feasHTML = '';
    if (cd.feasibility && Object.keys(cd.feasibility).length) {
      feasHTML = '<h4 style="margin-top:20px;margin-bottom:8px">📊 可行性评估</h4>';
      var fkeys = Object.keys(cd.feasibility);
      for (var fj = 0; fj < fkeys.length; fj++) {
        var fk = fkeys[fj];
        var fv = cd.feasibility[fk];
        var label = fk.replace(/_/g, ' ');
        feasHTML += '<div class="field" style="margin-bottom:4px"><b style="font-size:12px">' + label + '</b>';
        if (typeof fv === 'object' && fv !== null) {
          if (fv.score != null) feasHTML += ' <span class="badge" style="background:' + (fv.score >= 70 ? 'var(--green)' : fv.score >= 50 ? 'var(--yellow)' : 'var(--red)') + ';font-size:10px">' + fv.score + '%</span>';
          if (fv.reason) feasHTML += ' <div style="font-size:11px;color:var(--text-muted);margin-top:2px">' + fv.reason.slice(0, 300) + '</div>';
          if (fv.gpu_hours) feasHTML += ' <span style="font-size:10px;color:var(--blue);display:block;margin-top:2px">GPU: ' + fv.gpu_hours + '</span>';
          if (fv.platform) feasHTML += ' <span style="font-size:10px;color:var(--blue)">Platform: ' + fv.platform + '</span>';
        } else {
          feasHTML += ' <span style="font-size:11px;color:var(--text-muted)">' + String(fv).slice(0, 300) + '</span>';
        }
        feasHTML += '</div>';
      }
    }

    var innovHTML = '';
    if (cd.innovation_points && cd.innovation_points.length) {
      innovHTML = '<h4 style="margin-top:20px;margin-bottom:8px">💡 创新点 (' + cd.innovation_points.length + ' 个)</h4>';
      for (var ni = 0; ni < cd.innovation_points.length; ni++) {
        var ip = cd.innovation_points[ni];
        var ipText = (typeof ip === 'string') ? ip : (ip.claim || JSON.stringify(ip));
        var ipEscaped = ipText.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        innovHTML += '<div class="field" style="margin-bottom:4px;font-size:12px;line-height:1.5" title="' + ipEscaped + '">' + (ni + 1) + '. ' + (ipText.length > 120 ? ipText.slice(0, 120).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '...' : ipEscaped) + '</div>';
      }
    }

    var outputHTML = '';
    if (cd.expected_outputs && cd.expected_outputs.length) {
      outputHTML = '<h4 style="margin-top:20px;margin-bottom:8px">📤 预期产出</h4>';
      for (var oi = 0; oi < cd.expected_outputs.length; oi++) {
        outputHTML += '<div class="field" style="margin-bottom:2px;font-size:12px">• ' + cd.expected_outputs[oi] + '</div>';
      }
    }

    var gapHTML = '';
    if (cd.iterations && cd.iterations.length) {
      gapHTML = '<h4 style="margin-top:20px;margin-bottom:8px">🔍 各轮文献缺口</h4>';
      for (var gi = 0; gi < cd.iterations.length; gi++) {
        var it2 = cd.iterations[gi];
        var gaps = it2.literature_gaps || [];
        if (!gaps.length) continue;
        gapHTML += '<div style="margin-bottom:8px"><b style="font-size:12px;color:var(--yellow)">R' + (it2.iteration + 1) + ' (' + gaps.length + ' 个缺口)</b>';
        for (var gj = 0; gj < gaps.length; gj++) {
          gapHTML += '<div style="font-size:11px;color:var(--text-muted);padding-left:16px">• ' + gaps[gj] + '</div>';
        }
        gapHTML += '</div>';
      }
    }

    showModal(''
      + '<button class="close" onclick="closeModal()">✕</button>'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px">'
      + '<div><code style="font-size:14px;font-weight:700">' + shortId + '</code> <span class="impact-tag ' + passedCls + '">' + passedLabel + '</span>'
      + ' <span style="font-size:11px;color:var(--text-muted)">' + (cd.method || '') + ' | ' + (cd.disease || '') + '</span></div>'
      + '<div style="text-align:center;padding:4px 12px;background:var(--bg-alt);border-radius:8px"><div style="font-size:11px;color:var(--text-muted)">最终评分</div><div style="font-weight:700;font-size:22px;color:' + finalColor + '">' + cd.final_score.toFixed(2) + '</div></div>'
      + '</div>'

      + noveltyHTML
      + redteamHTML

      + '<h4 style="margin-bottom:8px;margin-top:20px">📝 研究摘要</h4>'
      + '<div style="font-size:13px;line-height:1.7;color:var(--text);margin-bottom:16px">' + (cd.summary_zh || 'N/A') + '</div>'

      + roadmapHTML
      + dataHTML
      + feasHTML
      + innovHTML
      + outputHTML

      + '<h4 style="margin-top:20px;margin-bottom:8px">📈 迭代评分历史</h4>'
      + '<div class="table-wrap"><table style="font-size:12px"><thead><tr><th style="text-align:center">轮次</th>'
      + dimNames.map(function(dn) { return '<th style="text-align:center">' + dn + '</th>'; }).join('')
      + '<th style="text-align:center">加权分</th><th style="text-align:center">通过</th></tr></thead>'
      + '<tbody>' + iterRows + '</tbody></table></div>'

      + critiqueHTML
      + gapHTML
      + citeHTML

      + (cd.evidence_link && cd.evidence_link.evidence_source ? (function() {
          var el2 = cd.evidence_link;
          if (el2.evidence_source === 'fallback_pool') {
            return '<h4 style="margin-top:20px;margin-bottom:8px">📎 证据锚定</h4><div class="field" style="font-size:12px;color:var(--amber)">⚠️ 无候选专属证据卡，回退到全库证据卡池 (' + (el2.evidence_pool_size || 0) + ' 张)<br/><span style="font-size:10px">方案评分基于全部候选的证据卡，缺乏对该方向的针对性锚定</span></div>';
          }
          var total = (el2.evidence_pool_size || 0);
          var ratio = total > 0 ? Math.round(el2.linked_card_count / total * 100) : 0;
          var ratioColor = ratio >= 20 ? 'var(--green)' : ratio >= 5 ? 'var(--yellow)' : 'var(--red)';
          return '<h4 style="margin-top:20px;margin-bottom:8px">📎 证据锚定</h4><div class="field" style="font-size:12px">专属证据卡: <b style="color:var(--green)">' + el2.linked_card_count + '</b> 张 | 占总池: <b style="color:' + ratioColor + '">' + ratio + '%</b> (' + el2.linked_card_count + '/' + total + ')</div>';
        })() : '')
      + (cd.literature_coverage && cd.literature_coverage.status ? '<h4 style="margin-top:20px;margin-bottom:8px">📚 文献覆盖检查</h4><div class="field" style="font-size:12px">关联证据卡: ' + (cd.literature_coverage.evidence_card_count || 0) + ' | 引用论文: ' + (cd.literature_coverage.cited_paper_count || 0) + ' | 重叠: ' + (cd.literature_coverage.overlapping_count || 0) + ' | 覆盖度: <b style="color:' + (cd.literature_coverage.status === 'good' ? 'var(--green)' : 'var(--red)') + '">' + (cd.literature_coverage.status || '?') + '</b>' + (cd.literature_coverage.evidence_source === 'fallback_pool' ? ' <span style="color:var(--amber)" title="该候选无 candidate 标签证据卡，已回退使用全库证据卡池">[回退全库证据卡]</span>' : '') + '</div>' : '')

      + (cd.error ? '<div class="field" style="margin-top:16px;color:var(--red);font-size:12px"><b>错误:</b> ' + cd.error + '</div>' : '')
    );
  },

  // 新颖性验证区块（含初始/复验对照）
  _renderNoveltySection(cd) {
    var nv = cd.novelty_verdict || {};
    if (!nv.overall_verdict) return '';
    var nvi = cd.novelty_verdict_initial || {};

    var html = '<h4 style="margin-bottom:8px">🔎 新颖性验证（Phase 1.5 对抗性检索）</h4>';
    html += '<div class="field" style="font-size:12px;margin-bottom:8px">'
      + '整体判定: ' + P05Tab._verdictBadge(nv.overall_verdict, nv.papers_found)
      + (nv.reverified_post_refine ? ' <span class="badge badge-blue" style="font-size:10px;margin-left:6px" title="refine 后对最终方案复验">已复验</span>' : '')
      + (nv.repositioning_required ? ' <span style="color:var(--red);font-size:11px;margin-left:6px">需重定位</span>' : '')
      + (cd.repositioning_attempts ? ' <span style="color:var(--text-muted);font-size:11px;margin-left:6px">重定位 ' + cd.repositioning_attempts + ' 次</span>' : '')
      + '</div>';

    if (nvi.overall_verdict && nvi.overall_verdict !== nv.overall_verdict) {
      html += '<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">初始方案判定: ' + P05Tab._verdictBadge(nvi.overall_verdict, nvi.papers_found) + '（refine 前）</div>';
    }

    var verdicts = nv.verdicts || [];
    for (var vi = 0; vi < verdicts.length; vi++) {
      var vd = verdicts[vi];
      var claim = String(vd.claim || '');
      var claimShort = claim.length > 150 ? claim.slice(0, 150) + '...' : claim;
      html += '<details class="field" style="margin-bottom:6px"><summary style="cursor:pointer;font-size:12px">'
        + P05Tab._verdictBadge(vd.verdict) + ' <span title="' + claim.replace(/"/g, '&quot;') + '">' + claimShort + '</span>'
        + '</summary><div style="padding:6px 0 2px 12px;font-size:11px;color:var(--text-muted);line-height:1.6">'
        + (vd.closeness || '')
        + '</div>';
      var cw = vd.closest_works || [];
      if (cw.length) {
        html += '<div style="padding:0 0 6px 12px">';
        for (var wi = 0; wi < Math.min(cw.length, 3); wi++) {
          var w = cw[wi];
          var wTitle = String(w.title || 'N/A');
          var wShort = wTitle.length > 100 ? wTitle.slice(0, 100) + '...' : wTitle;
          var wLink = w.doi ? 'https://doi.org/' + w.doi : '';
          html += '<div style="font-size:11px;margin-bottom:2px">📄 '
            + (wLink ? '<a href="' + wLink + '" target="_blank" style="color:var(--blue)" title="' + wTitle.replace(/"/g, '&quot;') + '">' + wShort + '</a>' : '<span title="' + wTitle.replace(/"/g, '&quot;') + '">' + wShort + '</span>')
            + ' <span style="color:var(--text-muted)">(' + (w.authors || '') + ', ' + (w.year || '') + ')</span>'
            + (w.similarity ? '<br/><span style="color:var(--text-muted);padding-left:16px">→ ' + w.similarity + '</span>' : '')
            + '</div>';
        }
        html += '</div>';
      }
      html += '</details>';
    }
    return html;
  },

  // 红队评审区块（含初始/复验对照）
  _renderRedteamSection(cd) {
    var rt = cd.redteam_result || {};
    if (!rt.findings && rt.high_count == null) return '';
    var rti = cd.redteam_result_initial || {};

    var sevColor = { high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--text-muted)' };
    var sevLabel = { high: '高', medium: '中', low: '低' };

    var html = '<h4 style="margin-top:20px;margin-bottom:8px">🛡️ 方法论红队评审（Phase 1.6）</h4>';
    html += '<div class="field" style="font-size:12px;margin-bottom:8px">'
      + '发现: <b style="color:var(--red)">' + (rt.high_count || 0) + ' 高</b> / <b style="color:var(--yellow)">' + (rt.medium_count || 0) + ' 中</b> / <b>' + (rt.low_count || 0) + ' 低</b>'
      + ' | 数据声明核实: ' + (rt.verified_claims || 0) + ' 通过, ' + ((rt.unverified_claims || []).length) + ' 未核实'
      + (rt.reverified_post_refine ? ' <span class="badge badge-blue" style="font-size:10px;margin-left:6px" title="refine 后对最终方案复验">已复验</span>' : '')
      + '</div>';

    if (rti.high_count != null && (rti.high_count !== rt.high_count || rti.medium_count !== rt.medium_count)) {
      html += '<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">初始方案发现: ' + rti.high_count + ' 高 / ' + (rti.medium_count || 0) + ' 中（refine 前）</div>';
    }

    var findings = rt.findings || [];
    for (var fi = 0; fi < findings.length; fi++) {
      var f = findings[fi];
      var sc = sevColor[f.severity] || 'var(--text-muted)';
      html += '<div class="field" style="margin-bottom:4px;font-size:11px;border-left:3px solid ' + sc + ';padding-left:8px">'
        + '<b style="color:' + sc + '">[' + (sevLabel[f.severity] || f.severity) + '] ' + (f.check || '') + '</b>'
        + '<div style="color:var(--text-muted);margin-top:2px;line-height:1.5">' + (f.detail || '') + '</div>'
        + '</div>';
    }

    // 纯规模声明（如"19数据集"）无标识符无法核实，仅展示含具体标识符的数据源声明
    var unverified = (rt.unverified_claims || []).filter(function(c) {
      return c.claim_type === 'data_source' || (c.identifiers && c.identifiers.length);
    });
    if (unverified.length) {
      html += '<div style="font-size:11px;margin-top:6px"><b style="color:var(--yellow)">未核实声明:</b>';
      for (var ui = 0; ui < Math.min(unverified.length, 8); ui++) {
        var claimText = unverified[ui].claim_text || '';
        html += '<div style="color:var(--text-muted);padding-left:16px" title="' + claimText.replace(/"/g, '&quot;') + '">• ' + claimText.slice(0, 120) + (claimText.length > 120 ? '...' : '') + '</div>';
      }
      html += '</div>';
    }
    return html;
  },
};
