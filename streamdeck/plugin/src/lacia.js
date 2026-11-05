// AI の状態とマシンの負荷から、上段4キーを歩く位置とコマを決める。
export class LaciaMotion {
  x = 12;
  direction = 1;
  animationMs = 0;
  gait = 'walk';
  advance(dt, { working = false, blocked = false, fresh = false, cpu = 0, memory = 0, enabled = true } = {}) {
    if (!enabled || !fresh || blocked) return { visible: false };
    if (working) {
      const seconds = Math.min(0.25, Math.max(0, dt));
      const next = this.gait === 'walk' ? (cpu >= 0.65 || memory >= 0.85 ? 'run' : 'walk') : (cpu < 0.45 && memory < 0.75 ? 'walk' : 'run');
      if (next !== this.gait) { this.gait = next; this.animationMs = 0; }
      this.x += this.direction * seconds * (28 + 60 * Math.max(0, Math.min(1, cpu)));
      if (this.x >= 524) { this.x = 524; this.direction = -1; }
      if (this.x <= 0) { this.x = 0; this.direction = 1; }
      this.animationMs += seconds * 1000;
    }
    return { visible: true, x: this.x, direction: this.direction, animation: working ? this.gait : 'idle', animationMs: working ? this.animationMs : 0 };
  }
}

export function frameAt(frames, elapsed) {
  const total = frames.reduce((sum, frame) => sum + frame.ms, 0);
  let ms = elapsed % total;
  for (const frame of frames) { if (ms < frame.ms) return frame; ms -= frame.ms; }
  return frames[0];
}

export function overlayLacia(base, column, pose, animations) {
  if (!pose.visible) return base;
  const x = Math.round(pose.x - column * 164);
  if (x >= 144 || x + 112 <= 0) return base;
  const svg = Buffer.from(base.split(',')[1], 'base64').toString('utf8');
  // 移動用素材が無いときは待機素材を使う。動作ごとの絵は素材ファイルだけで差し替えられる。
  const directional = pose.animation !== 'idle' ? (animations[`${pose.animation}-${pose.direction < 0 ? 'left' : 'right'}`] || animations[pose.direction < 0 ? 'left' : 'right']) : null;
  const frames = (directional || animations[pose.animation] || animations.idle).frames;
  const png = frameAt(frames, pose.animationMs).png;
  const transform = pose.direction < 0 && !directional ? `translate(${x + 112} 0) scale(-1 1)` : `translate(${x} 0)`;
  const pet = `<g transform="${transform}"><image x="0" y="16" width="112" height="112" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,${png}"/></g>`;
  // SVG の text を複製して暗い輪郭を先に描き、その上に元の文字を描く。
  const outlined = svg.replace(/<text\b[^>]*>[\s\S]*?<\/text>/g, (text) =>
    text.replace('<text ', '<text stroke="#111827" stroke-width="3" stroke-linejoin="round" ') + text);
  const result = outlined.includes('<text ') ? outlined.replace('<text ', pet + '<text ') : outlined.replace('</svg>', pet + '</svg>');
  return 'data:image/svg+xml;base64,' + Buffer.from(result).toString('base64');
}

// ページキーでは長い静止の間に短い待機アニメーションを挟む。
export class PageLacia {
  constructor(now, random = Math.random) { this.random = random; this.next = now + this.delay(); this.started = 0; this.motion = 'idle'; this.x = 0; this.from = 0; this.to = 0; }
  delay() { return 30000 + this.random() * 60000; }
  frame(now) {
    if (!this.started && now >= this.next) {
      this.started = now;
      const choice = this.random();
      this.motion = choice < 0.5 ? 'idle' : choice < 0.85 ? 'walk' : 'run';
      this.from = this.x;
      this.to = this.motion === 'idle' ? this.x : (this.x === 0 ? 24 : 0);
    }
    if (this.started && now - this.started >= 1200) { this.x = this.to; this.started = 0; this.next = now + this.delay(); }
    if (!this.started) return { name: 'idle', elapsed: 0, x: this.x };
    const elapsed = now - this.started;
    if (this.motion === 'idle') return { name: 'idle', elapsed, x: this.x };
    const x = Math.round(this.from + (this.to - this.from) * Math.min(1, elapsed / 1200));
    return { name: `${this.motion}-${this.to > this.from ? 'right' : 'left'}`, elapsed, x };

  }
}
export function overlayPageLacia(base, png, x = 0) {
  const svg = Buffer.from(base.split(',')[1], 'base64').toString('utf8');
  const pet = `<image x="${Math.max(0, Math.min(32, x))}" y="56" width="88" height="88" href="data:image/png;base64,${png}"/>`;
  const outlined = svg.replace(/<text\b[^>]*>[\s\S]*?<\/text>/g, (text) =>
    text.replace('<text ', '<text stroke="#111827" stroke-width="3" stroke-linejoin="round" ') + text);
  return 'data:image/svg+xml;base64,' + Buffer.from(outlined.replace('<text ', pet + '<text ')).toString('base64');
}
