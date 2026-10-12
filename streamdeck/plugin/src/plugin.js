// Stream Deck Neo 用の自作プラグイン。
// - Infobar: Claude Code / Codex の 5 時間・7 日の使用率と時計。承認待ちの Space があればその表示に切り替える
// - Space キー: herdr の Space の状態と話題。エージェントが最近動いた順に並べる。押すとその Space に移ってターミナルを前に出す
// - Claude 5h / 7d キー、経過時間キー、PC⇄Mac キー
// - アプリキー（Mac は Dock のバッジで未読数を出す）、コマンド実行キー（Mac の「開く」は引数付きコマンドを走らせられないため）
// キーと Infobar の絵は render.js が SVG で組み立てる。
import streamDeck, { SingletonAction } from '@elgato/streamdeck';
import { execFile } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, realpathSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { appKey, infobar, limitKey, spaceKey, switchKey, timerKey } from './render.js';

const win = process.platform === 'win32';
const log = streamDeck.logger;
// プラグインのフォルダは dotfiles への junction / symlink。実体をたどって streamdeck/ の下のスクリプトを使う
const STREAMDECK_DIR = join(dirname(realpathSync(fileURLToPath(import.meta.url))), '..', '..', '..');
const ID = 'io.github.parin1213.desk';

// ---- データ ----------------------------------------------------------------

// Stream Deck から起動されたプロセスは PATH が素の状態なので、Mac では mise と Homebrew の置き場所を足す
const env = win ? process.env : { ...process.env, PATH: [join(homedir(), '.local', 'share', 'mise', 'shims'), '/opt/homebrew/bin', process.env.PATH].join(delimiter) };
const run = (cmd, args, timeout = 10_000) => new Promise((resolve) => {
  execFile(cmd, args, { windowsHide: true, timeout, encoding: 'utf8', env }, (err, stdout, stderr) => resolve({ ok: !err, stdout, stderr, error: err?.message }));
});

// Stream Deck から起動されたプロセスは PATH が素の状態のことがあるので、mise の置き場所も探す
function findHerdr() {
  const exe = win ? 'herdr.exe' : 'herdr';
  for (const dir of (process.env.PATH || '').split(delimiter)) {
    if (dir && existsSync(join(dir, exe))) return join(dir, exe);
  }
  const installs = win ? join(process.env.LOCALAPPDATA || '', 'mise', 'installs') : join(homedir(), '.local', 'share', 'mise', 'installs');
  try {
    for (const tool of readdirSync(installs).filter((d) => /herdr/.test(d))) {
      const versions = readdirSync(join(installs, tool)).filter((v) => /^\d/.test(v))
        .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
      for (const v of versions) {
        for (const p of [join(installs, tool, v, exe), join(installs, tool, v, 'bin', exe)]) if (existsSync(p)) return p;
      }
    }
  } catch {}
  return null;
}
let herdrBin = findHerdr();

// herdr の Space 一覧。サーバーが動いていなければ空（herdr はここから起動されない）
async function readSpaces() {
  herdrBin ??= findHerdr();
  if (!herdrBin) return [];
  const r = await run(herdrBin, ['api', 'snapshot'], 5000);
  if (!r.ok) return [];
  try {
    const s = JSON.parse(r.stdout).result.snapshot;
    return s.workspaces.map((w) => ({
      id: w.workspace_id, number: w.number, status: w.agent_status || 'idle', focused: w.focused,
      topic: w.tokens?.topic || '', label: w.label || '',
    })).sort((a, b) => a.number - b.number);
  } catch { return []; }
}

const readJson = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } };

// リセット時刻を過ぎた枠は 0% とみなす（ステータスラインは Claude の画面が更新されたときにしか書かないため）
const windowOf = (pct, resetsAt, updatedAt) => {
  if (pct == null) return null;
  const now = Date.now() / 1000;
  const reset = resetsAt != null && resetsAt < now;
  return { pct: reset ? 0 : Math.round(pct), resetsAt: reset ? null : resetsAt, updatedAt };
};

function readClaude() {
  const j = readJson(join(homedir(), '.claude', 'cache', 'rate-limit.json'));
  if (!j) return null;
  const updatedAt = Date.parse(j.updated_at) / 1000;
  return { h5: windowOf(j.five_hour_pct, j.five_hour_resets_at, updatedAt), d7: windowOf(j.seven_day_pct, j.seven_day_resets_at, updatedAt) };
}

// Codex は rate_limits を各セッションのログ（rollout-*.jsonl）に書く。一番新しいファイルの最後の値を使う
function readCodex() {
  const root = join(process.env.CODEX_HOME || join(homedir(), '.codex'), 'sessions');
  const newest = (dir, depth) => {
    let names;
    try { names = readdirSync(dir).sort().reverse(); } catch { return null; }
    if (depth === 0) {
      const f = names.find((n) => n.startsWith('rollout-') && n.endsWith('.jsonl'));
      return f ? join(dir, f) : null;
    }
    for (const n of names) { const f = newest(join(dir, n), depth - 1); if (f) return f; }
    return null;
  };
  const file = newest(root, 3);
  if (!file) return null;
  const fd = openSync(file, 'r');
  const size = statSync(file).size, len = Math.min(size, 512 * 1024);
  const buf = Buffer.alloc(len);
  readSync(fd, buf, 0, len, size - len);
  closeSync(fd);
  const lines = buf.toString('utf8').split('\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].includes('"rate_limits"')) continue;
    let e;
    try { e = JSON.parse(lines[i]); } catch { continue; }
    const rl = findKey(e, 'rate_limits');
    if (!rl?.primary) continue;
    const updatedAt = Date.parse(e.timestamp) / 1000 || statSync(file).mtimeMs / 1000;
    return { h5: windowOf(rl.primary.used_percent, rl.primary.resets_at, updatedAt), d7: windowOf(rl.secondary?.used_percent, rl.secondary?.resets_at, updatedAt) };
  }
  return null;
}
const findKey = (o, k) => {
  if (!o || typeof o !== 'object') return null;
  if (k in o) return o[k];
  for (const v of Object.values(o)) { const f = findKey(v, k); if (f) return f; }
  return null;
};

// 同じ絵を送り直さない（Stream Deck への送信を減らす）
const lastImage = new Map();
const setImage = (a, url) => { if (lastImage.get(a.id) !== url) { lastImage.set(a.id, url); a.setImage(url); } };

// ---- アクション -------------------------------------------------------------

let spaces = [];
let claude = null, codex = null;

// Space ごとの「エージェントが最後に動いた時刻」。作業中・承認待ちの間と、状態が変わった瞬間を動いたとみなす。
// herdr で Space を開いただけでは数えない（キーを押すたびに並びが入れ替わると、押したいキーの位置が動くため）。
// herdr の snapshot には時刻が無いので、プラグインが観測して global settings に残す（Stream Deck を再起動しても並びを保つ）
let lastActive = {};
const lastStatus = new Map();
let activeDirty = false, activeSavedAt = 0;
function trackActivity() {
  const now = Date.now();
  const ids = new Set(spaces.map((s) => s.id));
  for (const s of spaces) {
    const changed = lastStatus.has(s.id) && lastStatus.get(s.id) !== s.status;
    if (!(s.id in lastActive) || changed || s.status === 'working' || s.status === 'blocked') { lastActive[s.id] = now; activeDirty = true; }
    lastStatus.set(s.id, s.status);
  }
  for (const id of Object.keys(lastActive)) if (!ids.has(id)) { delete lastActive[id]; activeDirty = true; }
  if (activeDirty && now - activeSavedAt > 30_000) {
    activeDirty = false; activeSavedAt = now;
    streamDeck.settings.setGlobalSettings({ lastActive }).catch(() => {});
  }
}
// 最近動いた順。同じ時刻なら Space の番号順
const recentSpaces = () => [...spaces].sort((a, b) => (lastActive[b.id] || 0) - (lastActive[a.id] || 0) || a.number - b.number);

class Space extends SingletonAction {
  manifestId = `${ID}.space`;
  // 最近動いた順の何番目を出すかは設定の slot、無ければ置いた列（左から 1, 2, …）
  slot(a, settings) { return Number(settings?.slot) || (a.coordinates?.column ?? 0) + 1; }
  spaceAt(a) { return recentSpaces()[this.slot(a, this.settings.get(a.id)) - 1]; }
  settings = new Map();
  render(a) { setImage(a, spaceKey(this.slot(a, this.settings.get(a.id)), this.spaceAt(a))); }
  async onWillAppear(ev) { this.settings.set(ev.action.id, ev.payload.settings); lastImage.delete(ev.action.id); this.render(ev.action); }
  async onDidReceiveSettings(ev) { this.settings.set(ev.action.id, ev.payload.settings); this.render(ev.action); }
  async onKeyDown(ev) {
    const sp = this.spaceAt(ev.action);
    if (!sp || !herdrBin) return ev.action.showAlert();
    await run(herdrBin, ['workspace', 'focus', sp.id]);
    await focusTerminal();
    refreshSpaces();
  }
  refresh() { for (const a of this.actions) this.render(a); }
}

// streamdeck/ の下の PowerShell スクリプトを窓を出さずに走らせる。pwsh が無ければ Windows PowerShell で
let pwsh;
async function ps(file, args, timeout) {
  pwsh ??= (await run('pwsh', ['-NoProfile', '-Command', '1'])).ok ? 'pwsh' : 'powershell.exe';
  return run(pwsh, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', join(STREAMDECK_DIR, file), ...args], timeout);
}

async function focusTerminal() {
  if (win) {
    await ps('focus-app.ps1', ['-Process', 'WindowsTerminal', '-Launch', 'wt.exe', '-Arguments', 'herdr']);
  } else {
    await run('open', ['-a', process.env.DESK_TERMINAL || 'Ghostty']);
  }
}

class Limit extends SingletonAction {
  constructor(kind) { super(); this.kind = kind; this.manifestId = `${ID}.claude-${kind}`; }
  render(a) { setImage(a, limitKey(`Claude ${this.kind}`, claude?.[this.kind === '5h' ? 'h5' : 'd7'], this.kind === '7d')); }
  async onWillAppear(ev) { lastImage.delete(ev.action.id); this.render(ev.action); }
  refresh() { for (const a of this.actions) this.render(a); }
}

class Infobar extends SingletonAction {
  manifestId = `${ID}.infobar`;
  async onWillAppear(ev) {
    if (!ev.action.isNeoInfobar()) return;
    await ev.action.setFeedbackLayout('layouts/infobar.json');
    lastImage.delete(ev.action.id);
    this.render(ev.action);
  }
  render(a) {
    const url = infobar(claude, codex, spaces);
    if (lastImage.get(a.id) !== url) { lastImage.set(a.id, url); a.setFeedback({ canvas: url }); }
  }
  refresh() { for (const a of this.actions) if (a.isNeoInfobar()) this.render(a); }
}

// 押すと 0 から数え直す。1 秒以上の長押しで止める。状態はキーごと
class Timer extends SingletonAction {
  manifestId = `${ID}.timer`;
  timers = new Map();
  async onWillAppear(ev) { lastImage.delete(ev.action.id); setImage(ev.action, timerKey(this.timers.get(ev.action.id))); }
  async onKeyDown(ev) { this.timers.set(ev.action.id, { ...this.timers.get(ev.action.id), down: Date.now() }); }
  async onKeyUp(ev) {
    const t = this.timers.get(ev.action.id) || {};
    const long = t.down && Date.now() - t.down >= 1000;
    this.timers.set(ev.action.id, long ? {} : { start: Date.now() });
    setImage(ev.action, timerKey(this.timers.get(ev.action.id)));
  }
  tick() { for (const a of this.actions) if (this.timers.get(a.id)?.start) setImage(a, timerKey(this.timers.get(a.id))); }
}

// Dell を相手のマシンに切り替える。PC からは Mac（TB4 = 0x19）に、Mac からは PC（DP = 0x0F = 15）に
const SWITCH_TO = win ? 'Mac' : 'PC';
class SwitchInput extends SingletonAction {
  manifestId = `${ID}.switch-input`;
  async onWillAppear(ev) { lastImage.delete(ev.action.id); setImage(ev.action, switchKey(false, SWITCH_TO)); }
  async onKeyDown(ev) {
    setImage(ev.action, switchKey(true, SWITCH_TO));
    const r = win
      ? await ps('switch-input.ps1', ['-Model', 'U2725QE', '-Source', '0x19'], 30_000)
      : await run(join(STREAMDECK_DIR, 'switch-input.sh'), ['U2725QE', '15'], 30_000);
    setImage(ev.action, switchKey(false, SWITCH_TO));
    if (!r.ok) { log.error(`switch-input 失敗: ${r.stderr}`); ev.action.showAlert(); }
  }
}

// アプリを開くキー。設定: path（開くアプリ）、icon（icons/ の PNG の名前）、badge（Dock のバッジを読むアプリ名。Mac だけ）。
// Stream Deck は SVG に埋め込んだ PNG を描けないので、バッジを重ねた絵は make-icons-mac.sh が
// icons/badges/<icon>-<1〜9 | 9+ | dot>.png に作っておき、件数に合うものをそのまま送る
const pngs = new Map();
const pngOf = (file) => {
  if (!pngs.has(file)) {
    try { pngs.set(file, 'data:image/png;base64,' + readFileSync(join(STREAMDECK_DIR, 'icons', file)).toString('base64')); } catch { pngs.set(file, null); }
  }
  return pngs.get(file);
};
// 件数が 10 以上なら 9+、数字でない（•）なら dot
const badgeFile = (icon, badge) => `badges/${icon}-${/^\d+$/.test(badge) ? (Number(badge) > 9 ? '9+' : badge) : 'dot'}.png`;
const appImage = (icon, badge) => (icon && badge && pngOf(badgeFile(icon, badge))) || (icon && pngOf(`${icon}.png`)) || appKey(badge);
// lsappinfo の StatusLabel が Dock のバッジ。権限なしで読める。アプリが動いていなければ空
async function readBadge(app) {
  const r = await run('lsappinfo', ['info', '-only', 'StatusLabel', app], 3000);
  return r.stdout.match(/"label"="([^"]*)"/)?.[1] || '';
}
class App extends SingletonAction {
  manifestId = `${ID}.app`;
  settings = new Map();
  badges = new Map();
  render(a) {
    const st = this.settings.get(a.id) || {};
    setImage(a, appImage(st.icon, this.badges.get(a.id)));
  }
  async onWillAppear(ev) { this.settings.set(ev.action.id, ev.payload.settings); lastImage.delete(ev.action.id); this.render(ev.action); }
  async onDidReceiveSettings(ev) { this.settings.set(ev.action.id, ev.payload.settings); this.render(ev.action); }
  async onKeyDown(ev) {
    const { path } = this.settings.get(ev.action.id) || {};
    if (!path) return ev.action.showAlert();
    const r = win ? await run(path, []) : await run('open', ['-a', path]);
    if (!r.ok) { log.error(`app 失敗: ${path} ${r.stderr}`); ev.action.showAlert(); }
  }
  async refresh() {
    if (win) return;
    for (const a of this.actions) {
      const app = this.settings.get(a.id)?.badge;
      if (!app) continue;
      const badge = await readBadge(app);
      if (badge !== this.badges.get(a.id)) log.info(`badge ${app}: "${this.badges.get(a.id) ?? ''}" -> "${badge}"`);
      this.badges.set(a.id, badge);
      this.render(a);
    }
  }
}

// コマンドを実行するキー。設定: cmd（実行ファイル。streamdeck/ の下にあるスクリプトは名前だけでよい）、args（配列）。絵はプロファイルの画像を使う
class Run extends SingletonAction {
  manifestId = `${ID}.run`;
  async onKeyDown(ev) {
    const { cmd, args = [] } = ev.payload.settings || {};
    if (!cmd) return ev.action.showAlert();
    const local = join(STREAMDECK_DIR, cmd);
    const file = !cmd.startsWith('/') && existsSync(local) ? local : cmd;
    const r = await run(file, args, 60_000);
    if (!r.ok) { log.error(`run 失敗: ${file} ${r.error || ''} ${r.stderr}`); ev.action.showAlert(); }
  }
}

const space = new Space(), limit5 = new Limit('5h'), limit7 = new Limit('7d'), bar = new Infobar(), timer = new Timer(), app = new App();
for (const a of [space, limit5, limit7, bar, timer, app, new SwitchInput(), new Run()]) streamDeck.actions.registerAction(a);

// ---- 更新 ------------------------------------------------------------------

let polling = false;
async function refreshSpaces() {
  if (polling) return;
  polling = true;
  try {
    // 表示しているキーが無ければ herdr を呼ばない
    if ([...space.actions].length || [...bar.actions].length) { spaces = await readSpaces(); trackActivity(); }
    space.refresh();
    bar.refresh();
  } finally { polling = false; }
}
function refreshLimits() {
  claude = readClaude();
  codex = readCodex();
  limit5.refresh(); limit7.refresh(); bar.refresh();
}

// 承認待ちに変わったのをすぐ出したいので herdr は 1.5 秒ごと。使用率のファイルは 10 秒ごと
setInterval(refreshSpaces, 1500);
setInterval(refreshLimits, 10_000);
// 未読数は 3 秒ごと
setInterval(() => app.refresh(), 3000);
setInterval(() => { timer.tick(); bar.refresh(); }, 1000);
refreshLimits();

await streamDeck.connect();
// 接続前に観測した分（初回は全部「今」になる）より、前回保存した時刻を優先する
lastActive = { ...lastActive, ...((await streamDeck.settings.getGlobalSettings())?.lastActive || {}) };
