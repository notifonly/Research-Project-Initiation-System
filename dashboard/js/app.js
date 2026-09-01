/* ─── Application core: state, theme, tabs, modal, export ─── */

const App = {
  DATA: null,
  loaded: false,
  error: null,

  TABS: [
    { id: 'overview', label: '📊 研究方向' },
    { id: 'evidence', label: '📚 文献证据' },
    { id: 'gaps', label: '🔍 研究缺口' },
    { id: 'hypotheses', label: '💡 研究假设' },
    { id: 'pipeline', label: '⚙️ 管线分析' },
    { id: 'compare', label: '🔄 方向对比' },
    { id: 'proposals', label: '⭐ 开题建议' },
    { id: 'decompose', label: '🧬 方向分解' },
    { id: 'p05', label: '🧪 P05 方案质量' },
    { id: 'p08', label: '🌍 P08 方案质量' },
    { id: 'p09', label: '🧬 P09 方案质量' },
  ],

  activeTab: 'overview',
};

/* ─── Theme ─── */
function initTheme() {
  const btn = document.getElementById('themeBtn');
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (isDark) {
    document.body.classList.add('dark');
    btn.textContent = '☀️';
  }
  btn.addEventListener('click', toggleTheme);
}

function toggleTheme() {
  document.body.classList.toggle('dark');
  const btn = document.getElementById('themeBtn');
  btn.textContent = document.body.classList.contains('dark') ? '☀️' : '🌙';
  Object.values(charts).forEach(c => { try { c.resize(); } catch(e) {} });
}

/* ─── Data loading ─── */
function loadData() {
  if (typeof INLINE_DATA !== 'undefined') {
    App.DATA = INLINE_DATA;
    App.loaded = true;
    initApp();
    return;
  }
  showLoading();
  fetch('data.json')
    .then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(d => {
      App.DATA = d;
      App.loaded = true;
      initApp();
    })
    .catch(e => {
      App.error = e.message;
      showError();
    });
}

function showLoading() {
  const main = document.getElementById('main');
  main.innerHTML = `
    <div style="padding:40px">
      <div class="skeleton skeleton-text" style="height:28px;width:200px;margin-bottom:16px"></div>
      <div class="skeleton skeleton-text" style="height:120px;margin-bottom:16px"></div>
      <div class="skeleton skeleton-text" style="height:120px;margin-bottom:16px"></div>
      <div class="skeleton skeleton-text short"></div>
    </div>`;
}

function showError() {
  const main = document.getElementById('main');
  main.innerHTML = `
    <div class="state-error">
      <div class="icon">⚠️</div>
      <h3>数据加载失败</h3>
      <p style="color:var(--text-muted)">${App.error || '无法加载 data.json，请确认文件存在'}</p>
      <button class="btn btn-primary" onclick="location.reload()" style="margin-top:16px">重试</button>
    </div>`;
}

/* ─── Tabs ─── */
function initTabs() {
  const nav = document.getElementById('tabNav');
  const main = document.getElementById('main');
  nav.innerHTML = '';
  main.innerHTML = '';

  App.TABS.forEach(t => {
    const btn = document.createElement('button');
    btn.textContent = t.label;
    btn.dataset.tab = t.id;
    btn.addEventListener('click', () => switchTab(t.id));
    nav.appendChild(btn);

    const div = document.createElement('div');
    div.className = 'tab-content';
    div.id = 'tab-' + t.id;
    main.appendChild(div);
  });
}

function switchTab(tabId) {
  if (App.activeTab === tabId && document.getElementById('tab-' + tabId).children.length > 0) return;
  App.activeTab = tabId;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  document.querySelector(`nav.tabs button[data-tab="${tabId}"]`).classList.add('active');
  setTimeout(() => renderTab(tabId), 50);
}

function renderTab(tabId) {
  const el = document.getElementById('tab-' + tabId);
  if (!el || !App.DATA) return;
  try {
    switch (tabId) {
      case 'overview': OverviewTab.render(el); break;
      case 'evidence': EvidenceTab.render(el); break;
      case 'gaps': GapsTab.render(el); break;
      case 'hypotheses': HypothesesTab.render(el); break;
      case 'pipeline': PipelineTab.render(el); break;
      case 'compare': CompareTab.render(el); break;
      case 'proposals': ProposalsTab.render(el); break;
      case 'decompose': DecomposeTab.render(el); break;
      case 'p05': P05Tab.render(el); break;
      case 'p08': P08Tab.render(el); break;
      case 'p09': P09Tab.render(el); break;
    }
  } catch (err) {
    console.error('Render error', tabId, err);
    el.innerHTML = `<div class="state-error"><div class="icon">⚠️</div><h3>渲染错误</h3><p>${err.message}</p></div>`;
  }
}

/* ─── Modal ─── */
function showModal(html) {
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalOverlay').classList.add('show');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('show');
}

/* ─── Landing ─── */
function showLanding() {
  const d = App.DATA;
  const m = d.meta;
  const main = document.getElementById('main');
  const nav = document.getElementById('tabNav');
  nav.style.display = 'none';

  main.innerHTML = `
    <div class="landing">
      <div class="hero-icon">🧬</div>
      <h2>AIscience 开题研究看板</h2>
      <p class="hero-sub">从研究兴趣出发，系统梳理 <strong>7</strong> 个研究方向的选题价值、文献缺口、核心假设与开题路径。</p>
      <div class="features">
        <div class="feature"><div class="feat-icon">📚</div><div class="feat-label">${m.total_cards} 证据卡片</div><div class="feat-val">774 篇文献</div></div>
        <div class="feature"><div class="feat-icon">🔍</div><div class="feat-label">${m.total_gaps} 研究缺口</div><div class="feat-val">${Object.keys(d.gap_patterns).length} 种模式</div></div>
        <div class="feature"><div class="feat-icon">💡</div><div class="feat-label">${m.total_hypotheses} 研究假设</div><div class="feat-val">${m.archetypes.length} 种范式</div></div>
        <div class="feature"><div class="feat-icon">📄</div><div class="feat-label">7个研究方向</div><div class="feat-val">4大研究范式</div></div>
      </div>
      <button class="btn btn-primary" id="btn-enter" style="padding:12px 32px;font-size:15px;border-radius:24px">
        📋 查看研究方向 →
      </button>
      <p style="margin-top:12px;font-size:12px;color:var(--text-muted)">点击上方标签页可切换到不同视图</p>
    </div>`;

  document.getElementById('btn-enter').addEventListener('click', enterApp);
}

function enterApp() {
  const nav = document.getElementById('tabNav');
  nav.style.display = '';
  initTabs();
  switchTab('overview');
}

/* ─── Init ─── */
function initApp() {
  initTheme();
  showLanding();
}

/* ─── Export ─── */
function exportReport() {
  const d = App.DATA;
  if (!d) return;

  const lines = [];
  lines.push('# AIscience 开题研究报告');
  lines.push(`> 生成时间: ${new Date().toISOString().slice(0, 10)}`);
  lines.push(`> 项目数: ${d.meta.total_projects} | 证据卡: ${d.meta.total_cards} | Gap: ${d.meta.total_gaps} | 假设: ${d.meta.total_hypotheses}`);
  lines.push('');
  lines.push('---');
  lines.push('');

  d.projects.forEach((p, i) => {
    lines.push(`## ${i+1}. ${p.name}`);
    lines.push('');
    lines.push(`**研究方向**: ${p.research_direction || 'N/A'}`);
    lines.push('');
    lines.push(`| 指标 | 值 |`);
    lines.push(`|------|----|`);
    lines.push(`| 证据卡片 | ${p.total_cards} |`);
    lines.push(`| 研究缺口 | ${p.gap_count} |`);
    lines.push(`| 研究假设 | ${p.hypothesis_count} |`);
    lines.push(`| Token用量 | ${(p.budget_used/1000).toFixed(1)}k |`);
    lines.push(`| 管线进度 | ${p.progress?.percent || 0}% |`);
    lines.push('');

    if (p.hypotheses && p.hypotheses.length) {
      lines.push('### 研究假设');
      p.hypotheses.forEach(h => {
        lines.push(`- **${h.statement}** 创新[${(h.novelty_score||0).toFixed(2)}] 可行[${(h.feasibility_score||0).toFixed(2)}]`);
        if (h.rationale) lines.push(`  - 依据: ${h.rationale.slice(0,150)}`);
      });
      lines.push('');
    }

    if (p.gaps && p.gaps.length) {
      lines.push('### 主要研究缺口');
      p.gaps.slice(0, 5).forEach(g => {
        lines.push(`- **${g.pattern_id}** - ${g.description || g.axis || ''} (分数: ${(g.score||0).toFixed(2)})`);
      });
      lines.push('');
    }

    if (p.literature && p.literature.length) {
      lines.push('### 代表性文献');
      p.literature.slice(0, 5).forEach(l => {
        const authors = (l.authors || []).slice(0, 3).join(', ');
        lines.push(`- ${authors} (${l.year || 'N/A'}). *${l.title}*. ${l.venue}.`);
        if (l.doi) lines.push(`  DOI: ${l.doi}`);
      });
      lines.push('');
    }
  });

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `AIscience_开题报告_${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ─── Startup ─── */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('modalOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) closeModal(); });
  document.getElementById('exportBtn').addEventListener('click', exportReport);
  loadData();
});
