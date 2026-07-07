// parser.ts — UIDL v1 parser (UIDL text → JSON spec)

export interface UIDLSpec {
  version: number;
  theme: string;
  layout: string;
  title: string;
  sections: Section[];
}

export type Section =
  | { type: 'h1' | 'h2' | 'h3'; text: string }
  | { type: 'hr' }
  | { type: 'text'; text: string; style?: string }
  | { type: 'metrics'; cols: number; items: MetricItem[] }
  | { type: 'chart'; chartType: string; title: string; x: (string | number)[]; series: SeriesData[]; color?: string; axes?: string[]; pieData?: PieSlice[] }
  | { type: 'table'; title: string; columns: string[]; rows: (string | number)[][] }
  | { type: 'cards'; cols: number; items: CardItem[] }
  | { type: 'list'; title: string; items: string[] }
  | { type: 'code'; lang: string; text: string }
  | { type: 'collapse'; title: string; content: string };

export interface MetricItem { label: string; value: string; color?: string; note?: string; }
export interface SeriesData { name: string; data: number[]; color?: string; }
export interface PieSlice { label: string; value: number; color?: string; }
export interface CardItem { title: string; subtitle: string; value: string; }

type Token = string | number;

const COLORS = new Set([
  'red','orange','yellow','green','blue','purple','cyan','pink','white','black',
  'gray','grey','indigo','teal','emerald','amber','rose','violet','lime','sky',
  'slate','zinc','neutral','stone','fuchsia'
]);

function isColor(val: unknown): boolean {
  if (typeof val !== 'string') return false;
  return COLORS.has(val.toLowerCase()) || /^#[0-9a-fA-F]{3,8}$/.test(val);
}

function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < line.length) {
    if (line[i] === ' ' || line[i] === '\t') { i++; continue; }
    if (line[i] === '"') {
      i++;
      let str = '';
      while (i < line.length && line[i] !== '"') { str += line[i]; i++; }
      if (i < line.length) i++;
      tokens.push(str);
    } else {
      let tok = '';
      while (i < line.length && line[i] !== ' ' && line[i] !== '\t') { tok += line[i]; i++; }
      const num = Number(tok);
      tokens.push(tok !== '' && !isNaN(num) ? num : tok);
    }
  }
  return tokens;
}

function getIndent(line: string): number {
  let n = 0;
  for (const ch of line) {
    if (ch === ' ') n++;
    else if (ch === '\t') n += 2;
    else break;
  }
  return n;
}

export function parseUIDL(text: string): UIDLSpec {
  const lines = text.split(/\r?\n/);
  const result: UIDLSpec = { version: 1, theme: 'light', layout: 'stack', title: '', sections: [] };
  let i = 0;

  const skip = () => { while (i < lines.length && (lines[i].trim() === '' || lines[i].trim().startsWith('//'))) i++; };

  skip();
  if (i < lines.length && lines[i].trim().startsWith('UIDL/')) {
    result.version = parseInt(lines[i].trim().split('/')[1]) || 1;
    i++; skip();
  }

  while (i < lines.length) {
    skip(); if (i >= lines.length) break;
    if (getIndent(lines[i]) > 0) break;
    const t = tokenizeLine(lines[i]);
    const cmd = String(t[0] || '').toLowerCase();
    if (cmd === 'theme') { result.theme = String(t[1] || 'light'); i++; }
    else if (cmd === 'layout') { result.layout = String(t[1] || 'stack'); i++; }
    else if (cmd === 'title') { result.title = String(t[1] || ''); i++; }
    else break;
  }

  while (i < lines.length) {
    skip(); if (i >= lines.length) break;
    if (getIndent(lines[i]) > 0) { i++; continue; }
    const t = tokenizeLine(lines[i]);
    const cmd = String(t[0] || '').toLowerCase();

    if (cmd === 'h1' || cmd === 'h2' || cmd === 'h3') {
      result.sections.push({ type: cmd, text: String(t[1] || '') });
      i++; continue;
    }

    if (cmd === 'text') {
      const sec: Section & { type: 'text' } = { type: 'text', text: String(t[1] || '') };
      if (t[2]) sec.style = String(t[2]);
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        sec.text += '\n' + lines[i].trim();
        i++;
      }
      result.sections.push(sec);
      continue;
    }

    if (cmd === 'hr' || cmd === '---') {
      result.sections.push({ type: 'hr' });
      i++; continue;
    }

    if (cmd === 'metrics') {
      const cols = typeof t[1] === 'number' ? t[1] : 3;
      const items: MetricItem[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        const mt = tokenizeLine(lines[i]);
        const item: MetricItem = { label: String(mt[0] || ''), value: String(mt[1] || '') };
        if (mt[2] && isColor(mt[2])) { item.color = String(mt[2]); if (mt[3]) item.note = String(mt[3]); }
        else if (mt[2]) { item.note = String(mt[2]); }
        items.push(item);
        i++;
      }
      result.sections.push({ type: 'metrics', cols, items });
      continue;
    }

    if (cmd === 'chart') {
      const chartType = String(t[1] || 'bar');
      const sec = { type: 'chart' as const, chartType, title: t[2] ? String(t[2]) : '', x: [] as (string|number)[], series: [] as SeriesData[], pieData: undefined as PieSlice[] | undefined };
      let y: number[] | undefined;
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        const ct = tokenizeLine(lines[i]);
        const sub = String(ct[0] || '').toLowerCase();
        if (sub === 'title') { sec.title = String(ct[1] || ''); }
        else if (sub === 'x' || sub === 'axes') { sec.x = ct.slice(1); }
        else if (sub === 'y') { y = ct.slice(1).filter((v): v is number => typeof v === 'number'); }
        else if (sub === 'series') {
          const name = String(ct[1] || '');
          const rest = ct.slice(2);
          const lastVal = rest[rest.length - 1];
          const hasColor = rest.length > 0 && isColor(lastVal);
          const color = hasColor ? String(rest.pop()!) : undefined;
          const data = rest.map(Number).filter(n => !isNaN(n));
          sec.series.push({ name, data, ...(color ? { color } : {}) });
        } else if (sub === 'color') {
          (sec as any).color = String(ct[1] || '');
        } else if (chartType === 'pie' || chartType === 'donut') {
          if (!sec.pieData) sec.pieData = [];
          const label = String(ct[0] || '');
          const value = typeof ct[1] === 'number' ? ct[1] : parseFloat(String(ct[1])) || 0;
          const color = ct[2] && isColor(ct[2]) ? String(ct[2]) : undefined;
          sec.pieData.push({ label, value, ...(color ? { color } : {}) });
        }
        i++;
      }
      if (y && sec.series.length === 0) {
        sec.series.push({ name: sec.title || 'Valor', data: y });
      }
      result.sections.push(sec as any);
      continue;
    }

    if (cmd === 'table') {
      const sec = { type: 'table' as const, title: t[1] ? String(t[1]) : '', columns: [] as string[], rows: [] as (string|number)[][] };
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        const tt = tokenizeLine(lines[i]);
        const sub = String(tt[0] || '').toLowerCase();
        if (sub === 'cols') { sec.columns = tt.slice(1).map(String); }
        else if (sub === 'row') { sec.rows.push(tt.slice(1)); }
        i++;
      }
      result.sections.push(sec);
      continue;
    }

    if (cmd === 'cards') {
      const cols = typeof t[1] === 'number' ? t[1] : 3;
      const items: CardItem[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        const ct = tokenizeLine(lines[i]);
        if (String(ct[0]).toLowerCase() === 'card') {
          items.push({ title: String(ct[1] || ''), subtitle: String(ct[2] || ''), value: ct[3] !== undefined ? String(ct[3]) : '' });
        }
        i++;
      }
      result.sections.push({ type: 'cards', cols, items });
      continue;
    }

    if (cmd === 'list') {
      const sec = { type: 'list' as const, title: t[1] ? String(t[1]) : '', items: [] as string[] };
      i++;
      while (i < lines.length && lines[i].trim() !== '' && getIndent(lines[i]) > 0) {
        const lt = tokenizeLine(lines[i]);
        const first = String(lt[0] || '');
        sec.items.push((first === '-' || first === '*') ? lt.slice(1).map(String).join(' ') : lt.map(v => String(v)).join(' '));
        i++;
      }
      result.sections.push(sec);
      continue;
    }

    if (cmd === 'code') {
      const lang = t[1] ? String(t[1]) : '';
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && getIndent(lines[i]) > 0) {
        codeLines.push(lines[i].replace(/^ {2}/, ''));
        i++;
      }
      result.sections.push({ type: 'code', lang, text: codeLines.join('\n') });
      continue;
    }

    if (cmd === 'collapse') {
      const contentLines: string[] = [];
      i++;
      while (i < lines.length && getIndent(lines[i]) > 0) {
        contentLines.push(lines[i].trimStart());
        i++;
      }
      result.sections.push({ type: 'collapse', title: t[1] ? String(t[1]) : 'Detalles', content: contentLines.join('\n') });
      continue;
    }

    i++;
  }

  if (!result.title) {
    const h1 = result.sections.find(s => s.type === 'h1') as { type: 'h1'; text: string } | undefined;
    if (h1) result.title = h1.text;
  }

  return result;
}
