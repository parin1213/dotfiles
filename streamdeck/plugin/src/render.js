// キーと Infobar の絵を SVG で組み立てる。値は data URL で返し、setImage / setFeedback にそのまま渡す。
// 見た目は make-icons.ps1 のキーと揃える: 用途色のグラデーション、上からの薄い光、下にラベル。
// Stream Deck の SVG 描画で崩れないよう、グラデーション・path・opacity だけで描く（filter / mask は使わない）。

const FONT = "'BIZ UDPGothic','Hiragino Sans',sans-serif";
// 数字は欧文フォントの方が締まって見える
const NUM = "'Segoe UI Variable Display','Segoe UI','SF Pro Display','Helvetica Neue',sans-serif";
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const svgUrl = (body, w = 144, h = 144) =>
  'data:image/svg+xml;base64,' + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`).toString('base64');
const text = (x, y, s, { size = 20, color = '#fff', weight = 700, anchor = 'start', opacity = 1, font = FONT } = {}) =>
  `<text x="${x}" y="${y}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}" opacity="${opacity}">${esc(s)}</text>`;

let gid = 0;
const linear = (a, b) => {
  const id = `g${gid++}`;
  return [id, `<defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>`];
};
const shine = (w, h) => {
  const id = `s${gid++}`;
  return `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".2"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs><rect width="${w}" height="${h}" fill="url(#${id})"/>`;
};
const bg = ([a, b], w = 144, h = 144) => { const [id, d] = linear(a, b); return `${d}<rect width="${w}" height="${h}" fill="url(#${id})"/>${shine(w, h)}`; };

// make-icons.ps1 の $palette と同じ色
const PAL = { ai: ['#ea580c', '#db2777'], mtg: ['#0d9488', '#16a34a'], sys: ['#334155', '#0f172a'], app: ['#27272a', '#09090b'] };
// 作業中と承認待ちを並べても見分けられるよう、作業中は黄〜橙、承認待ちは赤〜暗赤にする
const STATUS = {
  working: { label: '作業中', bg: ['#f59e0b', '#ea580c'] },
  blocked: { label: '承認待ち', bg: ['#ef4444', '#7f1d1d'] },
  done: { label: '完了', bg: ['#10b981', '#0f766e'] },
  idle: { label: '待機', bg: ['#475569', '#1e293b'] },
};

const CJK = /[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/;
const cw = (ch) => (CJK.test(ch) ? 2 : 1.15);
// 表示幅で折り返す（日本語は 2、英数字はプロポーショナルフォントで半角より少し広いので 1.15）。
// 英数字の並びとカタカナの並びは 1 語として途中で折らない。入りきらない最後の行は … で切る
function wrap(s, width, maxLines) {
  const tw = (t) => [...t].reduce((a, c) => a + cw(c), 0);
  const lines = [];
  let cur = '', w = 0;
  const flush = () => { lines.push(cur.trimEnd()); cur = ''; w = 0; };
  for (const tok of s.match(/[A-Za-z0-9._-]+|[\u30A0-\u30FF]+|[ \t]+|./gu) || []) {
    if (/^[ \t]+$/.test(tok)) { if (cur && w + 1 <= width) { cur += ' '; w += 1; } continue; }
    if (cur && w + tw(tok) > width && tw(tok) <= width) flush();
    for (const ch of tok) { if (w + cw(ch) > width) flush(); cur += ch; w += cw(ch); }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines.length = maxLines;
    let last = lines[maxLines - 1];
    while (tw(last) > width - 1) last = [...last].slice(0, -1).join('');
    lines[maxLines - 1] = last + '…';
  }
  return lines;
}

// 70% 以上は黄、90% 以上は赤。それ未満は白
const warn = (p) => (p >= 90 ? '#f87171' : p >= 70 ? '#fbbf24' : null);
const hhmm = (d) => `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
// 今日なら 23:20、別の日なら 10/17 20:00（7 日枠は常に日付付き）
const resetLabel = (epoch, alwaysDate) => {
  if (!epoch) return '';
  const d = new Date(epoch * 1000);
  const today = new Date().toDateString() === d.toDateString();
  return (alwaysDate || !today ? `${d.getMonth() + 1}/${d.getDate()} ` : '') + hhmm(d);
};

// 12 時の位置から時計回りの弧
function arc(cx, cy, r, pct) {
  const p = Math.max(0.001, Math.min(pct, 99.999)) / 100, a = p * 2 * Math.PI;
  return `M${cx} ${cy - r}A${r} ${r} 0 ${p > 0.5 ? 1 : 0} 1 ${(cx + r * Math.sin(a)).toFixed(2)} ${(cy - r * Math.cos(a)).toFixed(2)}`;
}
const ring = (cx, cy, r, sw, pct, color) => [
  `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#fff" stroke-width="${sw}" opacity=".22"/>`,
  pct == null ? '' : `<path d="${arc(cx, cy, r, pct)}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round"/>`,
].join('');

// 24 単位の線アイコン（Segoe Fluent Icons は Mac に無いので、パスで持つ）
const ICON = {
  watch: '<circle cx="12" cy="13.5" r="7.5"/><path d="M12 13.5V9.5M10 2.5h4M12 2.5v3.5M18.5 6.5l1.5-1.5"/>',
  swap: '<rect x="2.5" y="3.5" width="19" height="13" rx="2"/><path d="M8.5 20.5h7M12 16.5v4M8 8.5h8l-2.5-2.2M16 11.5H8l2.5 2.2"/>',
  lock: '<rect x="4" y="10.5" width="16" height="11" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5M12 15v2.5"/>',
};
const icon = (name, x, y, size, { sw = 1.8, opacity = 1 } = {}) =>
  `<g transform="translate(${x} ${y}) scale(${size / 24})" fill="none" stroke="#fff" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" opacity="${opacity}">${ICON[name]}</g>`;

export function spaceKey(slot, space) {
  if (!space) {
    return svgUrl([bg(PAL.app), text(72, 66, slot, { size: 34, anchor: 'middle', font: NUM, color: '#52525b' }),
      text(72, 104, '空き', { size: 16, anchor: 'middle', color: '#52525b' })].join(''));
  }
  const st = STATUS[space.status] || STATUS.idle;
  const lines = wrap(space.topic || space.label, 12, 3);
  const y0 = 82 - (lines.length - 1) * 11;
  const chip = st.label.length * 15 + 14;
  return svgUrl([
    bg(st.bg),
    '<circle cx="26" cy="26" r="15" fill="#fff" opacity=".22"/>', text(26, 33, space.number, { size: 20, anchor: 'middle', font: NUM }),
    `<rect x="${132 - chip}" y="14" width="${chip}" height="24" rx="12" fill="#000" opacity=".22"/>`,
    text(125, 31, st.label, { size: 14, anchor: 'end' }),
    ...lines.map((l, i) => text(72, y0 + i * 23, l, { size: 18, anchor: 'middle' })),
    space.focused ? '<rect x="4" y="4" width="136" height="136" rx="14" fill="none" stroke="#fff" stroke-width="4" opacity=".9"/>' : '',
  ].join(''));
}

// name は「Claude 5h」。下のラベルは枠の長さとリセット時刻だけにする（AI ページの色で Claude と分かるため）
export function limitKey(name, w, alwaysDate) {
  const kind = name.replace(/^Claude /, '');
  const body = [bg(PAL.ai)];
  if (!w) {
    body.push(ring(72, 64, 44, 9, null), text(72, 76, '—', { size: 30, anchor: 'middle', opacity: 0.6 }));
  } else {
    body.push(ring(72, 64, 44, 9, w.pct, warn(w.pct) || '#fff'));
    body.push(text(72, 74, w.pct, { size: 34, anchor: 'middle', font: NUM }), text(72, 92, '%', { size: 13, anchor: 'middle', opacity: 0.8, font: NUM }));
  }
  body.push(text(72, 132, w?.resetsAt ? `${kind} · ${resetLabel(w.resetsAt, alwaysDate)}` : name, { size: 14, anchor: 'middle', opacity: 0.95 }));
  return svgUrl(body.join(''));
}

export function infobar(claude, codex, spaces) {
  const W = 232, H = 50;
  const blocked = spaces.filter((s) => s.status === 'blocked');
  if (blocked.length) {
    const s = blocked[0];
    return svgUrl([
      bg(['#ef4444', '#7f1d1d'], W, H),
      '<circle cx="25" cy="25" r="15" fill="#fff"/>', text(25, 32, '!', { size: 20, anchor: 'middle', color: '#dc2626', font: NUM, weight: 800 }),
      text(50, 20, `${blocked.length > 1 ? `承認待ち ${blocked.length} 件` : '承認待ち'} · Space ${s.number}`, { size: 12, opacity: 0.9 }),
      text(50, 41, wrap(s.topic || s.label, 17, 1)[0] || '', { size: 16 }),
    ].join(''), W, H);
  }
  // 1 行に「● 名前 / 5h 数字 / 7d 数字」。数字の下の細い棒で量を見せる
  const row = (y, name, dot, d, stale) => {
    const o = stale ? 0.4 : 1;
    const parts = [`<circle cx="66" cy="${y + 11}" r="3.5" fill="${dot}" opacity="${o}"/>`, text(74, y + 15, name, { size: 11, color: '#e4e4e7', opacity: o })];
    [['5h', d?.h5], ['7d', d?.d7]].forEach(([k, w], i) => {
      const x = 122 + i * 56;
      parts.push(text(x, y + 15, k, { size: 9, color: '#a1a1aa', weight: 400, opacity: o, font: NUM }));
      parts.push(text(x + 50, y + 16, w ? `${w.pct}%` : '—', { size: 14, anchor: 'end', color: w ? warn(w.pct) || '#fff' : '#52525b', opacity: o, font: NUM }));
      parts.push(`<rect x="${x}" y="${y + 19}" width="50" height="2.5" rx="1.25" fill="#fff" opacity="${0.15 * o}"/>`);
      if (w) parts.push(`<rect x="${x}" y="${y + 19}" width="${Math.max(2.5, 0.5 * Math.min(w.pct, 100))}" height="2.5" rx="1.25" fill="${warn(w.pct) || dot}" opacity="${o}"/>`);
    });
    return parts.join('');
  };
  // Codex を使っていない間は値が古いままなので薄く出す（6 時間以上更新が無いとき）
  const stale = (d) => !d || Date.now() / 1000 - (d.h5?.updatedAt || 0) > 6 * 3600;
  const [id, grad] = linear(...PAL.ai);
  return svgUrl([
    bg(PAL.app, W, H), grad, `<rect width="54" height="${H}" fill="url(#${id})"/>`, shine(54, H),
    text(27, 32, hhmm(new Date()), { size: 18, anchor: 'middle', font: NUM }),
    row(2, 'Claude', '#fb923c', claude, false),
    row(25, 'Codex', '#e4e4e7', codex, stale(codex)),
  ].join(''), W, H);
}

const clock = (sec) => (sec >= 3600
  ? `${Math.floor(sec / 3600)}:${String(Math.floor(sec / 60) % 60).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
  : `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`);

// 動いている間はリングが 1 分で 1 周する
export function timerKey(t) {
  const sec = t?.start ? Math.floor((Date.now() - t.start) / 1000) : 0;
  return svgUrl([
    bg(PAL.mtg), ring(72, 62, 44, 5, t?.start ? ((sec % 60) / 60) * 100 : null, '#fff'),
    t?.start ? text(72, 74, clock(sec), { size: sec >= 3600 ? 24 : 32, anchor: 'middle', font: NUM }) : icon('watch', 48, 38, 48),
    text(72, 132, t?.start ? '経過' : 'タイマー', { size: 16, anchor: 'middle' }),
  ].join(''));
}

// to は切り替え先の名前（PC では「Mac」、Mac では「PC」）
// 切り替えたあと画面をロックするので、入れ替えの絵の右下に錠を添える
export const switchKey = (busy, to = 'Mac') => svgUrl([
  bg(PAL.sys), icon('swap', 32, 26, 60, { sw: 1.6, opacity: busy ? 0.5 : 1 }),
  icon('lock', 90, 58, 30, { sw: 2.2, opacity: busy ? 0.5 : 1 }),
  text(72, 128, busy ? '切替中…' : `${to} に切替`, { size: 18, anchor: 'middle' }),
].join(''));

// ロゴの画像が無いアプリのキー。暗い地に Dock のバッジの文字（未読数、または「•」）を重ねる。
// ロゴのあるキーは plugin.js が icons/ の PNG を使う（Stream Deck は SVG に埋め込んだ PNG を描けないため）。
// 数字が長いときは丸を横に伸ばし、4 桁以上は 999+ にまとめる
export function appKey(badge) {
  const body = [bg(PAL.app)];
  if (badge) {
    const label = /^\d+$/.test(badge) && Number(badge) > 999 ? '999+' : badge;
    const w = Math.max(48, 22 + [...label].length * 18);
    body.push(
      `<rect x="${140 - w}" y="4" width="${w}" height="48" rx="24" fill="#ef4444"/>`,
      `<rect x="${140 - w}" y="4" width="${w}" height="48" rx="24" fill="none" stroke="#09090b" stroke-width="3"/>`,
      // 「•」（件数なしの未読）はフォントによって位置がずれるので、文字ではなく丸で描く
      label === '•' ? `<circle cx="${140 - w / 2}" cy="28" r="9" fill="#fff"/>` : text(140 - w / 2, 39, label, { size: 30, anchor: 'middle', font: NUM, weight: 800 }),
    );
  }
  return svgUrl(body.join(''));
}
