#!/usr/bin/env node
// Claude Code の会話から「いま何の話をしているか」の短いタイトルを作り、herdr のタブ名と Spaces の topic に出す。
//
// なぜ: Claude Code のセッション名は最初の発言から 1 回だけ付き、話が移っても変わらない。
//       Stream Deck と herdr のサイドバーで Space を見分けるには、今の話題に合ったタイトルが要る。
//
// Stop hook から呼ぶ。Haiku の呼び出しに数秒かかるので、hook はすぐ戻し、裏で動く自分自身に任せる。
// 作ったタイトルは state に書き、表示は herdr-tab-title に任せる（タブ名の手動変更を守る処理がそちらにあるため）。
//
// 使い方（Claude Code の hooks.Stop と hooks.SessionStart）: node ~/.local/bin/herdr-topic.mjs
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, openSync, readFileSync, readSync, closeSync, fstatSync, statSync, writeFileSync, unlinkSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const win = process.platform === 'win32';
const stateDir = join(process.env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'herdr-topic');
const paneKey = (process.env.HERDR_PANE_ID || '').replace(/:/g, '_');

// 表示幅（日本語は 2）。全角 12 文字 = 24 幅に収める。
const MAX_WIDTH = 24;
const width = (s) => [...s].reduce((w, ch) => w + (/[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/.test(ch) ? 2 : 1), 0);

const PROMPT = [
  'あなたはターミナルのタブに出す見出しを作る。入力は Claude Code の会話の直近部分。',
  '今まさに取り組んでいる話題を、日本語の名詞句 1 行で出力する。全角 12 文字以内。',
  '固有名（リポジトリ名・ツール名・機能名）があれば残し、「〜について」「〜の件」などの飾りや句読点・括弧・引用符は付けない。',
  '「前のタイトル」が今の話題にも合っていれば、一字も変えずにそのまま出力する。',
  'タイトル以外は何も出力しない。',
].join('\n');

if (process.argv[2] === '--worker') {
  worker(process.argv[3]);
} else {
  hook();
}

function hook() {
  // タイトル生成用に立ち上げた claude からの hook では何もしない（--setting-sources '' で読まれないが念のため）。
  if (process.env.HERDR_TOPIC_CHILD || !process.env.HERDR_ENV || !paneKey) return;
  let input = '';
  try { input = readFileSync(0, 'utf8'); } catch { return; }
  let ev;
  try { ev = JSON.parse(input); } catch { return; }
  // 同じペインで新しい会話を始めたら、前の会話のタイトルを捨てる（compact や resume では残す）
  if (ev.hook_event_name === 'SessionStart') {
    if (ev.source === 'startup' || ev.source === 'clear') { try { unlinkSync(join(stateDir, `${paneKey}.txt`)); } catch {} }
    return;
  }
  const transcript = ev.transcript_path;
  if (!transcript || !existsSync(transcript)) return;
  const child = spawn(process.execPath, [fileURLToPath(import.meta.url), '--worker', transcript], {
    detached: true, stdio: 'ignore', windowsHide: true,
  });
  child.unref();
}

function worker(transcript) {
  mkdirSync(stateDir, { recursive: true });
  const titleFile = join(stateDir, `${paneKey}.txt`);
  const lockFile = join(stateDir, `${paneKey}.lock`);
  const logFile = join(stateDir, 'log.txt');
  const log = (msg) => { try { writeFileSync(logFile, `${new Date().toISOString()} ${paneKey} ${msg}\n`, { flag: 'a' }); } catch {} };

  // 生成中に次の発言が来たら、今回は見送る（直後の Stop でまた呼ばれる）。固まった lock は 2 分で無視する。
  if (existsSync(lockFile) && Date.now() - statSync(lockFile).mtimeMs < 120_000) return;
  writeFileSync(lockFile, String(process.pid));
  try {
    const previous = existsSync(titleFile) ? readFileSync(titleFile, 'utf8').trim() : '';
    const excerpt = readExcerpt(transcript);
    if (!excerpt) return;
    const started = Date.now();
    const r = spawnSync('claude', [
      '-p', '--model', 'haiku', '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config',
      '--tools', '', '--system-prompt', PROMPT,
    ], {
      input: `前のタイトル: ${previous || '（なし）'}\n\n${excerpt}`,
      encoding: 'utf8', cwd: tmpdir(), windowsHide: true, timeout: 60_000,
      env: { ...process.env, HERDR_TOPIC_CHILD: '1', MAX_THINKING_TOKENS: '0' },
    });
    if (r.status !== 0) { log(`claude 失敗 status=${r.status} ${(r.stderr || r.error?.message || '').slice(0, 200)}`); return; }
    const title = clean(r.stdout);
    log(`${Date.now() - started}ms ${previous} -> ${title}`);
    if (!title || title === previous) return;
    writeFileSync(titleFile, title);
    showTitle();
  } finally {
    try { unlinkSync(lockFile); } catch {}
  }
}

// transcript は数 MB になるので末尾だけ読み、直近の発言とアシスタントの返答を短く切って並べる。
function readExcerpt(path) {
  const fd = openSync(path, 'r');
  const size = fstatSync(fd).size;
  const len = Math.min(size, 1024 * 1024);
  const buf = Buffer.alloc(len);
  readSync(fd, buf, 0, len, size - len);
  closeSync(fd);
  const turns = [];
  for (const line of buf.toString('utf8').split('\n')) {
    let e;
    try { e = JSON.parse(line); } catch { continue; }
    if (e.isMeta || e.isSidechain || e.isCompactSummary || !e.message) continue;
    const c = e.message.content;
    const text = typeof c === 'string' ? c : Array.isArray(c) ? c.filter((p) => p.type === 'text').map((p) => p.text).join('\n') : '';
    // コマンドの出力や system-reminder などタグで始まるものは会話ではない
    if (!text.trim() || text.trimStart().startsWith('<')) continue;
    if (e.type === 'user') turns.push(`ユーザー: ${text.trim().slice(0, 400)}`);
    else if (e.type === 'assistant') turns.push(`アシスタント: ${text.trim().slice(0, 300)}`);
  }
  // 同じ話題が続いているかを見られるよう、直近のユーザー発言 3 つ分の範囲を渡す
  let users = 0, from = turns.length;
  while (from > 0 && users < 3) { from--; if (turns[from].startsWith('ユーザー:')) users++; }
  return turns.slice(from).join('\n').slice(-3000);
}

function clean(out) {
  let t = (out || '').split(/\r?\n/).map((s) => s.trim()).find(Boolean) || '';
  t = t.replace(/^(タイトル|見出し)\s*[:：]\s*/, '').replace(/[「」『』"'`*#。．]/g, '').trim();
  let cut = '';
  for (const ch of t) { if (width(cut + ch) > MAX_WIDTH) break; cut += ch; }
  return cut;
}

// タブ名と Spaces の topic を herdr-tab-title に書かせる。
function showTitle() {
  const bin = join(homedir(), '.local', 'bin');
  const [cmd, args] = win
    ? ['powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', join(bin, 'herdr-tab-title.ps1'), 'auto']]
    : [join(bin, 'herdr-tab-title'), ['auto']];
  spawnSync(cmd, args, { stdio: 'ignore', windowsHide: true, timeout: 30_000 });
}
