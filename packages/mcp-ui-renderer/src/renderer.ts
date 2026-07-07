// renderer.ts — JSON spec → standalone HTML+CSS+JS string
// Estilo "pale": minimalismo real. Chart.js via CDN.

import type { UIDLSpec, Section, SeriesData, PieSlice } from './parser.js';

const CHART_COLORS = [
  '#4f46e5','#0891b2','#059669','#d97706','#dc2626',
  '#7c3aed','#db2777','#0d9488','#ca8a04','#6366f1'
];

const COLOR_MAP: Record<string, string> = {
  red:'#dc2626', orange:'#d97706', yellow:'#ca8a04', green:'#059669',
  blue:'#4f46e5', purple:'#7c3aed', cyan:'#0891b2', pink:'#db2777',
  indigo:'#6366f1', teal:'#0d9488', emerald:'#10b981', amber:'#f59e0b',
  rose:'#f43f5e', violet:'#8b5cf6', lime:'#84cc16', sky:'#0ea5e9',
  slate:'#64748b', zinc:'#71717a', neutral:'#737373', stone:'#78716c',
  fuchsia:'#d946ef', white:'#ffffff', black:'#000000',
  gray:'#6b7280', grey:'#6b7280'
};

function resolveColor(c?: string, fallback?: string): string {
  if (!c) return fallback || CHART_COLORS[0];
  if (c.startsWith('#')) return c;
  return COLOR_MAP[c.toLowerCase()] || fallback || CHART_COLORS[0];
}

function esc(s: string | number): string {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function generateCSS(theme: string): string {
  const dark = theme === 'dark';
  return `
    :root {
      --bg: ${dark ? '#0a0a0b' : '#fafafa'};
      --bg-card: ${dark ? '#141416' : '#ffffff'};
      --bg-hover: ${dark ? '#1c1c1f' : '#f5f5f5'};
      --text: ${dark ? '#ececef' : '#1a1a1a'};
      --text-dim: ${dark ? '#8b8b94' : '#737373'};
      --border: ${dark ? '#232328' : '#e5e5e5'};
      --accent: ${dark ? '#818cf8' : '#4f46e5'};
      --accent-glow: ${dark ? 'rgba(129,140,248,0.12)' : 'rgba(79,70,229,0.08)'};
      --highlight-bg: ${dark ? '#15132d' : '#eef2ff'};
      --highlight-border: ${dark ? '#4338ca' : '#c7d2fe'};
      --code-bg: ${dark ? '#111113' : '#f4f4f5'};
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { font-size: 16px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body {
      font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
      background: var(--bg); color: var(--text);
      line-height: 1.6; padding: 2.5rem 1.5rem;
      max-width: 1040px; margin: 0 auto;
    }
    h1 { font-size: 1.85rem; font-weight: 700; margin: 0 0 0.25rem; letter-spacing: -0.03em; background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    h2 { font-size: 1.15rem; font-weight: 600; margin: 2.25rem 0 0.75rem; letter-spacing: -0.01em; color: var(--text); position: relative; padding-left: 0.75rem; }
    h2::before { content: ''; position: absolute; left: 0; top: 0.2em; bottom: 0.2em; width: 3px; background: var(--accent); border-radius: 2px; }
    h3 { font-size: 1.0rem; font-weight: 600; margin: 1.5rem 0 0.5rem; color: var(--text-dim); }
    p, .text-block { margin: 0.75rem 0; color: var(--text-dim); font-size: 0.925rem; }
    hr { border: none; border-top: 1px solid var(--border); margin: 2rem 0; }
    .metrics { display: grid; gap: 0.875rem; margin: 1.25rem 0; }
    .metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.15rem 1.35rem; transition: all 0.2s ease; position: relative; overflow: hidden; }
    .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--accent); opacity: 0; transition: opacity 0.2s; }
    .metric-card:hover { background: var(--bg-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,${dark ? '0.4' : '0.08'}); }
    .metric-card:hover::before { opacity: 1; }
    .metric-label { font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 500; }
    .metric-value { font-size: 1.6rem; font-weight: 700; margin: 0.3rem 0 0.15rem; letter-spacing: -0.02em; }
    .metric-note { font-size: 0.72rem; color: var(--text-dim); opacity: 0.8; }
    .chart-wrap { margin: 1.5rem 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
    .chart-wrap h3 { margin: 0 0 0.75rem; color: var(--text); font-size: 0.95rem; }
    .chart-wrap canvas { max-height: 300px; }
    .table-wrap { margin: 1.5rem 0; overflow-x: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 0.25rem 0; }
    .table-wrap h3 { padding: 0.75rem 1rem 0.5rem; margin: 0; color: var(--text); font-size: 0.95rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    thead th { text-align: left; padding: 0.6rem 1rem; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); }
    tbody td { padding: 0.6rem 1rem; border-bottom: 1px solid ${dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'}; }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover { background: var(--bg-hover); }
    .cards { display: grid; gap: 0.875rem; margin: 1.25rem 0; }
    .info-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.15rem 1.35rem; transition: all 0.2s ease; }
    .info-card:hover { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-glow), 0 4px 12px rgba(0,0,0,${dark ? '0.3' : '0.06'}); transform: translateY(-1px); }
    .info-card-title { font-weight: 600; font-size: 0.9rem; }
    .info-card-sub { font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem; }
    .info-card-value { font-size: 0.82rem; color: var(--accent); margin-top: 0.35rem; font-weight: 600; letter-spacing: 0.01em; }
    .text-highlight { background: var(--highlight-bg); border-left: 3px solid var(--highlight-border); padding: 0.85rem 1.15rem; border-radius: 0 8px 8px 0; margin: 1.25rem 0; color: var(--text); font-size: 0.9rem; }
    .text-insight { background: linear-gradient(135deg, var(--highlight-bg) 0%, ${dark ? 'rgba(129,140,248,0.06)' : 'rgba(79,70,229,0.04)'} 100%); border-left: 3px solid var(--accent); padding: 0.85rem 1.15rem; border-radius: 0 8px 8px 0; margin: 1.25rem 0; font-size: 0.9rem; }
    .text-dim { color: var(--text-dim); }
    .code-block { background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.15rem; overflow-x: auto; font-family: 'Cascadia Code','Fira Code','JetBrains Mono','Consolas',monospace; font-size: 0.8rem; line-height: 1.55; margin: 1rem 0; white-space: pre; }
    .list-block { margin: 1rem 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; }
    .list-block h3 { margin: 0 0 0.5rem; color: var(--text); font-size: 0.95rem; }
    .list-block ul { padding-left: 1.25rem; }
    .list-block li { margin: 0.35rem 0; color: var(--text-dim); font-size: 0.875rem; }
    .list-block li::marker { color: var(--accent); }
    details { margin: 1rem 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    details summary { padding: 0.75rem 1rem; cursor: pointer; font-weight: 500; background: var(--bg-card); }
    details[open] summary { border-bottom: 1px solid var(--border); }
    details .collapse-body { padding: 1rem; }
    .footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); font-size: 0.7rem; color: var(--text-dim); opacity: 0.6; display: flex; justify-content: space-between; }
    @media (max-width: 640px) {
      body { padding: 1.25rem 1rem; }
      h1 { font-size: 1.5rem; }
      .metric-value { font-size: 1.3rem; }
      .metrics, .cards { grid-template-columns: 1fr !important; }
    }`;
}

function renderSection(sec: Section, idx: number): string {
  switch (sec.type) {
    case 'h1': return `<h1>${esc(sec.text)}</h1>`;
    case 'h2': return `<h2>${esc(sec.text)}</h2>`;
    case 'h3': return `<h3>${esc(sec.text)}</h3>`;
    case 'hr': return '<hr>';

    case 'text': {
      const cls = sec.style === 'highlight' ? 'text-highlight'
                : sec.style === 'insight' ? 'text-insight'
                : sec.style === 'dim' ? 'text-block text-dim' : 'text-block';
      return `<div class="${cls}">${esc(sec.text).replace(/\n/g,'<br>')}</div>`;
    }

    case 'metrics': {
      let html = `<div class="metrics" style="grid-template-columns:repeat(${sec.cols},1fr);">`;
      for (const m of sec.items) {
        const color = resolveColor(m.color, '#4f46e5');
        html += `<div class="metric-card" style="border-top:2px solid ${color}"><div class="metric-label">${esc(m.label)}</div><div class="metric-value" style="color:${color}">${esc(m.value)}</div>${m.note ? `<div class="metric-note">${esc(m.note)}</div>` : ''}</div>`;
      }
      return html + '</div>';
    }

    case 'chart': return `<div class="chart-wrap">${sec.title ? `<h3>${esc(sec.title)}</h3>` : ''}<canvas id="chart_${idx}"></canvas></div>`;

    case 'table': {
      let html = `<div class="table-wrap">${sec.title ? `<h3>${esc(sec.title)}</h3>` : ''}<table><thead><tr>`;
      for (const c of sec.columns) html += `<th>${esc(c)}</th>`;
      html += '</tr></thead><tbody>';
      for (const row of sec.rows) { html += '<tr>'; for (const cell of row) html += `<td>${esc(cell)}</td>`; html += '</tr>'; }
      return html + '</tbody></table></div>';
    }

    case 'cards': {
      let html = `<div class="cards" style="grid-template-columns:repeat(${sec.cols},1fr);">`;
      for (const c of sec.items) html += `<div class="info-card"><div class="info-card-title">${esc(c.title)}</div>${c.subtitle ? `<div class="info-card-sub">${esc(c.subtitle)}</div>` : ''}${c.value ? `<div class="info-card-value">${esc(c.value)}</div>` : ''}</div>`;
      return html + '</div>';
    }

    case 'list': {
      let html = `<div class="list-block">${sec.title ? `<h3>${esc(sec.title)}</h3>` : ''}<ul>`;
      for (const item of sec.items) html += `<li>${esc(item)}</li>`;
      return html + '</ul></div>';
    }

    case 'code': return `<div class="code-block">${esc(sec.text)}</div>`;
    case 'collapse': return `<details><summary>${esc(sec.title)}</summary><div class="collapse-body">${esc(sec.content).replace(/\n/g,'<br>')}</div></details>`;
    default: return '';
  }
}

function generateChartJS(spec: UIDLSpec): string {
  const scripts: string[] = [];
  const dark = spec.theme === 'dark';
  const gridColor = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
  const textColor = dark ? '#8b8b94' : '#737373';

  spec.sections.forEach((sec, idx) => {
    if (sec.type !== 'chart') return;
    const id = `chart_${idx}`;
    const ct = sec.chartType;

    if (ct === 'bar') {
      const labels = sec.x.map(v => JSON.stringify(String(v))).join(',');
      const data = sec.series[0]?.data || [];
      const c = resolveColor(sec.series[0]?.color || sec.color);
      scripts.push(`new Chart(document.getElementById('${id}'),{type:'bar',data:{labels:[${labels}],datasets:[{data:[${data}],backgroundColor:'${c}aa',borderColor:'${c}',borderWidth:0,borderRadius:4,borderSkipped:false,hoverBackgroundColor:'${c}'}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{color:'${textColor}'}},y:{grid:{color:'${gridColor}'},ticks:{color:'${textColor}'},beginAtZero:true}}}});`);
    } else if (ct === 'line') {
      const labels = sec.x.map(v => JSON.stringify(String(v))).join(',');
      const ds = sec.series.map((s: SeriesData, si: number) => {
        const c = resolveColor(s.color, CHART_COLORS[si]);
        return `{label:${JSON.stringify(s.name)},data:[${s.data}],borderColor:'${c}',backgroundColor:'${c}22',tension:0.3,pointRadius:3,fill:${si===0}}`;
      });
      scripts.push(`new Chart(document.getElementById('${id}'),{type:'line',data:{labels:[${labels}],datasets:[${ds}]},options:{responsive:true,plugins:{legend:{display:${sec.series.length>1},labels:{color:'${textColor}'}}},scales:{x:{grid:{color:'${gridColor}'},ticks:{color:'${textColor}'}},y:{grid:{color:'${gridColor}'},ticks:{color:'${textColor}'}}}}});`);
    } else if (ct === 'pie' || ct === 'donut') {
      const pd = sec.pieData || [];
      const labels = pd.map((d: PieSlice) => JSON.stringify(d.label)).join(',');
      const vals = pd.map((d: PieSlice) => d.value).join(',');
      const cols = pd.map((d: PieSlice, di: number) => `'${resolveColor(d.color, CHART_COLORS[di])}'`).join(',');
      scripts.push(`new Chart(document.getElementById('${id}'),{type:'${ct==='donut'?'doughnut':'pie'}',data:{labels:[${labels}],datasets:[{data:[${vals}],backgroundColor:[${cols}],borderWidth:1,borderColor:'${dark?'#0f0f0f':'#fafafa'}'}]},options:{responsive:true,plugins:{legend:{position:'bottom',labels:{color:'${textColor}',padding:12}}}}});`);
    } else if (ct === 'radar') {
      const labels = (sec.axes || sec.x).map(v => JSON.stringify(String(v))).join(',');
      const ds = sec.series.map((s: SeriesData, si: number) => {
        const c = resolveColor(s.color, CHART_COLORS[si]);
        return `{label:${JSON.stringify(s.name)},data:[${s.data}],borderColor:'${c}',backgroundColor:'${c}22',pointBackgroundColor:'${c}'}`;
      });
      scripts.push(`new Chart(document.getElementById('${id}'),{type:'radar',data:{labels:[${labels}],datasets:[${ds}]},options:{responsive:true,plugins:{legend:{labels:{color:'${textColor}'}}},scales:{r:{grid:{color:'${gridColor}'},pointLabels:{color:'${textColor}'},ticks:{display:false}}}}});`);
    } else if (ct === 'scatter') {
      const xd = sec.x as number[];
      const yd = sec.series[0]?.data || [];
      const pts = xd.map((x, i) => `{x:${x},y:${yd[i]||0}}`).join(',');
      const c = resolveColor(sec.series[0]?.color || sec.color);
      scripts.push(`new Chart(document.getElementById('${id}'),{type:'scatter',data:{datasets:[{data:[${pts}],backgroundColor:'${c}',pointRadius:4}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{color:'${gridColor}'},ticks:{color:'${textColor}'}},y:{grid:{color:'${gridColor}'},ticks:{color:'${textColor}'}}}}});`);
    }
  });

  return scripts.join('\n    ');
}

export function renderHTML(spec: UIDLSpec): string {
  const css = generateCSS(spec.theme);
  const body = spec.sections.map((s, i) => renderSection(s, i)).join('\n    ');
  const charts = generateChartJS(spec);

  return `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(spec.title || 'UIDL Page')}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"><\/script>
  <style>${css}</style>
</head>
<body>
    ${body}
    <div class="footer"><span>Generado con UIDL Renderer</span><span>${new Date().toISOString().slice(0,10)}</span></div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {
      Chart.defaults.font.family = "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif";
      Chart.defaults.font.size = 12;
      ${charts}
    });
    <\/script>
</body>
</html>`;
}
