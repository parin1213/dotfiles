// 自作プラグインを Stream Deck に入れる。プラグインのフォルダを Stream Deck の Plugins に junction（Mac は symlink）で
// つなぐので、以降は pnpm build のあと restart するだけで反映される。
// 実行: pnpm run link（つなぐ + 再起動） / pnpm run restart（再起動だけ）
import { execFileSync, spawn } from 'node:child_process';
import { existsSync, lstatSync, symlinkSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const UUID = 'io.github.parin1213.desk';
const win = process.platform === 'win32';
const src = join(import.meta.dirname, '..', `${UUID}.sdPlugin`);
const pluginsDir = win
  ? join(process.env.APPDATA, 'Elgato', 'StreamDeck', 'Plugins')
  : join(homedir(), 'Library', 'Application Support', 'com.elgato.StreamDeck', 'Plugins');
const dest = join(pluginsDir, `${UUID}.sdPlugin`);

if (!process.argv.includes('--restart-only')) {
  if (!existsSync(join(src, 'bin', 'plugin.js'))) throw new Error('bin/plugin.js が無い。先に pnpm build を実行する');
  let linked = false;
  try { linked = lstatSync(dest).isSymbolicLink(); } catch {}
  if (existsSync(dest) && !linked) throw new Error(`${dest} がリンクではなく実体のフォルダになっている。中身を確かめてから消す`);
  if (!linked) symlinkSync(src, dest, win ? 'junction' : 'dir');
  console.log(`${dest} -> ${src}`);
}

// プラグインは Stream Deck の起動時に読み込まれるので、アプリを再起動する
if (win) {
  try { execFileSync('taskkill', ['/IM', 'StreamDeck.exe', '/F'], { stdio: 'ignore' }); } catch {}
  await new Promise((r) => setTimeout(r, 2000));
  spawn(join(process.env.ProgramFiles, 'Elgato', 'StreamDeck', 'StreamDeck.exe'), [], { detached: true, stdio: 'ignore' }).unref();
} else {
  // quit は終了を待たずに返る。終わる前に open すると既存のアプリが前に出るだけで、そのあと終了して起動し直さない。
  // quit が -128 で断られることもあるので、10 秒で終わらなければ kill する
  const running = () => { try { execFileSync('pgrep', ['-x', 'Stream Deck'], { stdio: 'ignore' }); return true; } catch { return false; } };
  try { execFileSync('osascript', ['-e', 'quit app "Elgato Stream Deck"'], { stdio: 'ignore' }); } catch {}
  for (let i = 0; i < 20 && running(); i++) await new Promise((r) => setTimeout(r, 500));
  if (running()) {
    try { execFileSync('pkill', ['-x', 'Stream Deck']); } catch {}
    for (let i = 0; i < 10 && running(); i++) await new Promise((r) => setTimeout(r, 500));
  }
  execFileSync('open', ['-a', 'Elgato Stream Deck']);
}
console.log('Stream Deck を再起動した');
