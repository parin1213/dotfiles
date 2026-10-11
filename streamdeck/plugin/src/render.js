// キーと Infobar の絵を SVG で組み立てる。値は data URL で返し、setImage / setFeedback にそのまま渡す。


const FONT = "'BIZ UDPGothic','Hiragino Sans','Yu Gothic UI',sans-serif";
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const svgUrl = (body, w = 144, h = 144) =>
  'data:image/svg+xml;base64,' + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`).toString('base64');
const text = (x, y, s, { size = 20, color = '#fff', weight = 700, anchor = 'start', opacity = 1 } = {}) =>
  `<text x="${x}" y="${y}" font-family="${FONT}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}" opacity="${opacity}">${esc(s)}</text>`;
const grad = (id, a, b) => `<defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>`;

const cw = (ch) => (/[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/.test(ch) ? 2 : 1.15);
// 表示幅で折り返す（日本語は 2、英数字はプロポーショナルフォントで半角より少し広いので 1.15）。入りきらない最後の行は … で切る
function wrap(s, width, maxLines) {
  const lines = [];
  let cur = '', w = 0;
  for (const ch of s) {
    if (w + cw(ch) > width) { lines.push(cur); cur = ''; w = 0; }
    cur += ch; w += cw(ch);
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines.length = maxLines;
    let last = lines[maxLines - 1];
    while ([...last].reduce((a, c) => a + cw(c), 0) > width - 1) last = [...last].slice(0, -1).join('');
    lines[maxLines - 1] = last + '…';
  }
  return lines;
}

const pctColor = (p) => (p >= 90 ? '#f87171' : p >= 70 ? '#fbbf24' : '#4ade80');
const hhmm = (d) => `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
// 今日なら 23:20、別の日なら 10/17 20:00（7 日枠は常に日付付き）
const resetLabel = (epoch, alwaysDate) => {
  if (!epoch) return '';
  const d = new Date(epoch * 1000);
  const today = new Date().toDateString() === d.toDateString();
  return (alwaysDate || !today ? `${d.getMonth() + 1}/${d.getDate()} ` : '') + hhmm(d);
};

const STATUS = {
  working: { label: '作業中', bg: ['#c2410c', '#9a3412'] },
  blocked: { label: '承認待ち', bg: ['#dc2626', '#991b1b'] },
  done: { label: '完了', bg: ['#15803d', '#166534'] },
  idle: { label: '待機', bg: ['#334155', '#1e293b'] },
};

export function spaceKey(slot, space) {
  if (!space) {
    return svgUrl(`<rect width="144" height="144" fill="#18181b"/>${text(14, 34, slot, { size: 24, color: '#52525b' })}${text(72, 88, '空き', { size: 20, color: '#52525b', anchor: 'middle' })}`);
  }
  const st = STATUS[space.status] || STATUS.idle;
  const lines = wrap(space.topic || space.label, 12, 3);
  const y0 = 84 - (lines.length - 1) * 12;
  return svgUrl([
    grad('g', ...st.bg), '<rect width="144" height="144" fill="url(#g)"/>',
    text(12, 30, space.number, { size: 24 }),
    text(132, 28, st.label, { size: 17, anchor: 'end', opacity: 0.9 }),
    ...lines.map((l, i) => text(72, y0 + i * 24, l, { size: 18, anchor: 'middle' })),
    space.focused ? '<rect x="3" y="3" width="138" height="138" rx="10" fill="none" stroke="#fff" stroke-width="5" opacity=".85"/>' : '',
  ].join(''));
}

export function limitKey(name, w, alwaysDate) {
  const body = ['<rect width="144" height="144" fill="#18181b"/>', text(72, 30, name, { size: 18, anchor: 'middle', color: '#d4d4d8' })];
  if (!w) {
    body.push(text(72, 88, '—', { size: 40, anchor: 'middle', color: '#52525b' }));
  } else {
    const c = pctColor(w.pct);
    body.push(text(72, 86, `${w.pct}%`, { size: 46, anchor: 'middle', color: c }));
    if (w.resetsAt) body.push(text(72, 116, `→${resetLabel(w.resetsAt, alwaysDate)}`, { size: 16, anchor: 'middle', color: '#a1a1aa' }));
    body.push('<rect x="14" y="128" width="116" height="7" rx="3.5" fill="#3f3f46"/>');
    body.push(`<rect x="14" y="128" width="${Math.max(4, (116 * Math.min(w.pct, 100)) / 100)}" height="7" rx="3.5" fill="${c}"/>`);
  }
  return svgUrl(body.join(''));
}

export function infobar(claude, codex, spaces) {
  const blocked = spaces.filter((s) => s.status === 'blocked');
  if (blocked.length) {
    const s = blocked[0];
    const head = blocked.length > 1 ? `承認待ち ${blocked.length} 件` : '承認待ち';
    return svgUrl([
      grad('g', '#dc2626', '#991b1b'), '<rect width="232" height="50" fill="url(#g)"/>',
      text(8, 18, head, { size: 13, opacity: 0.9 }),
      text(8, 42, `${s.number}  ${wrap(s.topic || s.label, 19, 1)[0] || ''}`, { size: 16 }),
    ].join(''), 232, 50);
  }
  const now = new Date();
  const row = (y, name, d, stale) => {
    const parts = [text(50, y + 16, name, { size: 11, color: '#d4d4d8', opacity: stale ? 0.45 : 1 })];
    // 幅が 232px しかないので、バーは付けず数字だけを色で出す
    [['5h', d?.h5], ['7d', d?.d7]].forEach(([k, w], i) => {
      const x = 100 + i * 66, o = stale ? 0.45 : 1;
      parts.push(text(x, y + 16, k, { size: 10, color: '#a1a1aa', weight: 400, opacity: o }));
      parts.push(w ? text(x + 19, y + 17, `${w.pct}%`, { size: 15, color: pctColor(w.pct), opacity: o })
        : text(x + 19, y + 17, '—', { size: 15, color: '#52525b' }));
    });
    return parts.join('');
  };
  // Codex を使っていない間は値が古いままなので薄く出す（6 時間以上更新が無いとき）
  const stale = (d) => !d || Date.now() / 1000 - (d.h5?.updatedAt || 0) > 6 * 3600;
  return svgUrl([
    '<rect width="232" height="50" fill="#09090b"/>',
    text(22, 31, hhmm(now), { size: 17, anchor: 'middle' }),
    '<rect x="43" y="8" width="1" height="34" fill="#3f3f46"/>',
    row(1, 'Claude', claude, false),
    row(24, 'Codex', codex, stale(codex)),
  ].join(''), 232, 50);
}

export function timerKey(t) {
  const sec = t?.start ? Math.floor((Date.now() - t.start) / 1000) : 0;
  const s = sec >= 3600 ? `${Math.floor(sec / 3600)}:${String(Math.floor(sec / 60) % 60).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
    : `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
  return svgUrl([
    grad('g', '#0d9488', '#16a34a'), '<rect width="144" height="144" fill="url(#g)"/>',
    text(72, 40, t?.start ? '経過' : 'タイマー', { size: 19, anchor: 'middle', opacity: 0.9 }),
    text(72, 96, s, { size: sec >= 3600 ? 32 : 42, anchor: 'middle', opacity: t?.start ? 1 : 0.5 }),
  ].join(''));
}

export const switchKey = (busy) => svgUrl([
  grad('g', '#334155', '#0f172a'), '<rect width="144" height="144" fill="url(#g)"/>',
  text(72, 62, 'PC ⇄ Mac', { size: 24, anchor: 'middle' }),
  text(72, 100, busy ? '切替中…' : 'Dell の入力', { size: 17, anchor: 'middle', opacity: 0.8 }),
].join(''));
