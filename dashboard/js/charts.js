/* Shared chart utilities */
const charts = {};

function initChart(elId) {
  const el = document.getElementById(elId);
  if (!el) return null;
  if (charts[elId]) charts[elId].dispose();
  const c = echarts.init(el, null, { renderer: 'canvas' });
  charts[elId] = c;
  return c;
}

function fontColor() {
  return document.body.classList.contains('dark') ? '#94a3b8' : '#64748b';
}

function textColor() {
  return document.body.classList.contains('dark') ? '#f1f5f9' : '#1e293b';
}

const ARCHETYPE_COLORS = {
  'archetype_a_v2g': '#3B82F6',
  'archetype_b_prs': '#F59E0B',
  'archetype_c_sc_ai': '#10B981',
  'archetype_d_omics_score': '#8B5CF6',
};

const PROJECT_COLORS = ['#3B82F6','#F59E0B','#10B981','#8B5CF6','#EC4899','#06B6D4','#F97316'];

function getArchetypeBadgeClass(aid) {
  const map = {
    'archetype_a_v2g': 'badge-blue',
    'archetype_b_prs': 'badge-amber',
    'archetype_c_sc_ai': 'badge-green',
    'archetype_d_omics_score': 'badge-purple',
  };
  return map[aid] || 'badge-blue';
}

function getArchetypeColor(aid) {
  return ARCHETYPE_COLORS[aid] || '#6B7280';
}

function loadProjectColors(n) {
  return PROJECT_COLORS.slice(0, n);
}

function litLink(l) {
  if (l.url) return l.url;
  if (l.doi) return 'https://doi.org/' + l.doi;
  if (l.pmid) return 'https://pubmed.ncbi.nlm.nih.gov/' + l.pmid;
  return null;
}

function litAnchor(l, maxLen) {
  var href = litLink(l);
  var title = l.title || '';
  var display = maxLen && title.length > maxLen ? title.slice(0, maxLen) + '...' : title;
  if (href) {
    return '<a href="' + href + '" target="_blank" rel="noopener" title="' + title + '" style="color:var(--blue);text-decoration:none">' + display + '</a>';
  }
  var escaped = title.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  return '<span title="' + escaped + '">' + (display || '') + '</span>';
}

window.addEventListener('resize', () => {
  Object.values(charts).forEach(c => { try { c.resize(); } catch(e) {} });
});
