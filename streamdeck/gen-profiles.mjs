// Stream Deck Neo のプロファイル（通常 / エンジニアリング）を生成する。
// 標準アクションだけで作れるキーを置き、自作プラグインや公式プラグインが要るキーは空けておく。
// 出力は out/<名前>.streamDeckProfile（中身は ProfilesV3 と同じ構造）。取り込みは README を参照。
// キー画像は make-icons.ps1 が作る icons/*.png を使う。
import { mkdirSync, writeFileSync, rmSync, copyFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

const OUT = join(import.meta.dirname, 'out');
const ICONS = join(import.meta.dirname, 'icons');
const DEVICE = { Model: '20GBJ9901', UUID: '@(1)[4057/154/A7BSA5371M1QN6]' };

// ラベルは画像に焼き込んであるので Stream Deck のタイトルは出さない（title は設定画面での識別用）
const action = (uuid, name, title, icon, settings) => ({
  ActionID: randomUUID(), LinkedTitle: false, Name: name,
  Plugin: { Name: name, UUID: uuid, Version: '1.0' },
  Resources: null, Settings: settings, State: 0,
  States: [{
    FontFamily: '', FontSize: 12, FontStyle: '', FontUnderline: false, Image: `Images/${icon}.png`,
    OutlineThickness: 2, ShowTitle: false, Title: title, TitleAlignment: 'middle', TitleColor: '#ffffff',
  }],
  UUID: uuid,
});

const open = (title, icon, path) => action('com.elgato.streamdeck.system.open', 'Open', title, icon, { path });
const web = (title, icon, url) => action('com.elgato.streamdeck.system.website', 'Website', title, icon, { openInBrowser: true, path: url });
// actionIdx は既定プロファイルのアイコンで確認した: 1 = 再生/一時停止、4 = ミュート
const media = (title, icon, idx) => action('com.elgato.streamdeck.system.multimedia', 'Multimedia', title, icon, { actionIdx: idx });

// 修飾キーのビットは既定プロファイルの実例（Ctrl = 2、Win = 8）に合わせ、Shift = 1、Alt = 4 とした
const EMPTY_KEY = { KeyCmd: false, KeyCtrl: false, KeyModifiers: 0, KeyOption: false, KeyShift: false, NativeCode: 146, QTKeyCode: 33554431, VKeyCode: -1 };
const hotkey = (title, icon, { ctrl = false, alt = false, shift = false, win = false, key }) => {
  const vk = key.charCodeAt(0);
  const first = {
    KeyCmd: win, KeyCtrl: ctrl, KeyModifiers: (shift ? 1 : 0) | (ctrl ? 2 : 0) | (alt ? 4 : 0) | (win ? 8 : 0),
    KeyOption: alt, KeyShift: shift, NativeCode: vk, QTKeyCode: vk, VKeyCode: vk,
  };
  return action('com.elgato.streamdeck.system.hotkey', 'Hotkey', title, icon, { Coalesce: true, Hotkeys: [first, EMPTY_KEY, EMPTY_KEY, EMPTY_KEY] });
};

const clock = () => ({
  ActionID: randomUUID(), LinkedTitle: true, Name: 'Digital time',
  Plugin: { Name: 'Digital Time', UUID: 'com.elgato.streamdeck.system.digitaltime', Version: '1.0' },
  Resources: null, Settings: { '24HourFormat': true, layout: 'digital_time_07', location: '', theme: 'white' },
  State: 0, States: [{}], UUID: 'com.elgato.streamdeck.system.digitaltime',
});

const OBSIDIAN = 'C:\\Users\\schwa\\AppData\\Local\\Programs\\Obsidian\\Obsidian.exe';
const VSCODE = 'C:\\Users\\schwa\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe';
// ゲームは register-game-tasks.ps1 が登録したタスクを起動する（UAC を出さないため）。
// schtasks はコンソールアプリなので、conhost --headless で黒い窓を出さずに走らせる
const TASK = (name) => `conhost.exe --headless schtasks.exe /run /tn "\\StreamDeck\\${name}"`;
const APP = (aumid) => `explorer.exe shell:AppsFolder\\${aumid}`;

// キーの位置は "列,行"。Infobar は Neo コントローラの "1,0"（自作プラグインができるまでは時計）
const PROFILES = [
  {
    name: '通常',
    pages: [
      { // 普段使い。2,1 は PC⇄Mac（自作プラグイン）
        '0,0': media('再生/停止', 'play-pause', 1),
        '1,0': media('ミュート', 'mute', 4),
        '2,0': web('YouTube Music', 'youtube-music', 'https://music.youtube.com/'),
        '3,0': open('Obsidian', 'obsidian', `"${OBSIDIAN}"`),
        '0,1': open('原神', 'genshin', TASK('Genshin')),
        '1,1': open('崩壊：スターレイル', 'starrail', TASK('StarRail')),
        '3,1': open('ロック', 'lock', 'rundll32.exe user32.dll,LockWorkStation'),
      },
      { // AI。上段の Space 4 つと使用率、Codex 送信は自作 / 公式プラグイン待ち
        '3,1': open('Codex アプリ', 'codex-app', APP('OpenAI.Codex_2p2nqsd0c76g0!App')),
      },
      { // 会議中（Google Meet）。3,1 は経過時間（自作プラグイン）
        '0,0': hotkey('マイク', 'mic', { ctrl: true, key: 'D' }),
        '1,0': hotkey('カメラ', 'camera', { ctrl: true, key: 'E' }),
        '2,0': hotkey('挙手', 'hand', { ctrl: true, alt: true, key: 'H' }),
        '3,0': hotkey('字幕', 'captions', { key: 'C' }),
        '0,1': hotkey('チャット', 'chat', { ctrl: true, alt: true, key: 'C' }),
        '1,1': hotkey('参加者', 'people', { ctrl: true, alt: true, key: 'P' }),
        '2,1': open('会議メモ', 'meeting-note', `"${OBSIDIAN}"`),
      },
    ],
  },
  {
    name: 'エンジニアリング',
    pages: [
      { // 3,0 は Codex 送信（ChatGPT & Codex 公式プラグイン）
        '0,0': open('ターミナル', 'terminal', 'wt.exe'),
        '1,0': open('VS Code', 'vscode', `"${VSCODE}"`),
        '2,0': open('Claude Code', 'claude-code', 'wt.exe -w 0 new-tab pwsh -NoExit -Command claude'),
        '0,1': web('GitHub PR', 'github-pr', 'https://github.com/pulls'),
        '1,1': hotkey('範囲スクショ', 'screenshot', { win: true, shift: true, key: 'S' }),
        '2,1': hotkey('Meet ミュート', 'meet-mic', { ctrl: true, key: 'D' }),
        '3,1': hotkey('Meet カメラ', 'meet-camera', { ctrl: true, key: 'E' }),
      },
    ],
  },
];

for (const p of PROFILES) {
  const build = join(OUT, 'build');
  rmSync(build, { recursive: true, force: true });
  const dir = join(build, `${randomUUID().toUpperCase()}.sdProfile`);
  const pageIds = p.pages.map(() => randomUUID());
  const defaultId = randomUUID();
  const writePage = (id, keys) => {
    const pdir = join(dir, 'Profiles', id.toUpperCase());
    mkdirSync(join(pdir, 'Images'), { recursive: true });
    for (const a of Object.values(keys)) {
      const img = a.States[0].Image.replace('Images/', '');
      copyFileSync(join(ICONS, img), join(pdir, 'Images', img));
    }
    writeFileSync(join(pdir, 'manifest.json'), JSON.stringify({
      Controllers: [
        { Actions: Object.keys(keys).length ? keys : null, Type: 'Keypad' },
        { Actions: { '1,0': clock() }, Type: 'Neo' },
      ],
      Icon: '', Name: '',
    }));
  };
  p.pages.forEach((keys, i) => writePage(pageIds[i], keys));
  writePage(defaultId, {});
  writeFileSync(join(dir, 'manifest.json'), JSON.stringify({
    Device: DEVICE, Name: p.name,
    Pages: { Current: pageIds[0], Default: defaultId, Pages: pageIds },
    Version: '3.0',
  }));

  // .streamDeckProfile は .sdProfile フォルダを丸ごと zip にしたもの
  const zip = join(OUT, `${p.name}.zip`);
  const dest = join(OUT, `${p.name}.streamDeckProfile`);
  execFileSync('pwsh', ['-NoProfile', '-Command',
    `Compress-Archive -LiteralPath '${dir}' -DestinationPath '${zip}' -Force; Move-Item -LiteralPath '${zip}' -Destination '${dest}' -Force`]);
  rmSync(build, { recursive: true, force: true });
  console.log(`${p.name}: ${dest}`);
}
