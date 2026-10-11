// Stream Deck Neo のプロファイル（通常 / エンジニアリング）を生成する。
// 標準アクションと自作プラグイン（plugin/）のキーを置く。公式プラグインが要るキーは空けておく。
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

// 自作プラグインのアクション。絵はプラグインが実行中に描くので、画像は持たせない
const DESK = { Name: 'Desk', UUID: 'io.github.parin1213.desk', Version: '0.1.0.0' };
const desk = (name, id, settings = {}) => ({
  ActionID: randomUUID(), LinkedTitle: false, Name: name, Plugin: DESK,
  Resources: null, Settings: settings, State: 0, States: [{ ShowTitle: false }], UUID: `${DESK.UUID}.${id}`,
});

const OBSIDIAN = 'C:\\Users\\schwa\\AppData\\Local\\Programs\\Obsidian\\Obsidian.exe';
const VSCODE = 'C:\\Users\\schwa\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe';
// ストア版の Windows Terminal はパスにバージョンが入るので、生成時に今入っているものを引く
const TERMINAL = execFileSync('pwsh', ['-NoProfile', '-Command',
  "(Get-AppxPackage Microsoft.WindowsTerminal).InstallLocation + '\\WindowsTerminal.exe'"], { encoding: 'utf8' }).trim();
// ゲームは register-game-tasks.ps1 が登録したタスクを起動する（UAC を出さないため）。
// schtasks はコンソールアプリなので、conhost --headless で黒い窓を出さずに走らせる
const TASK = (name) => `conhost.exe --headless schtasks.exe /run /tn "\\StreamDeck\\${name}"`;
const APP = (aumid) => `explorer.exe shell:AppsFolder\\${aumid}`;
const PS = (file, args = '') => `conhost.exe --headless pwsh -NoProfile -File "${join(import.meta.dirname, file)}" ${args}`.trim();

// ブラウザでインストールしたアプリ（PWA）があればそれを開き、無ければサイトを開く。
// PWA はスタートメニューに「<名前>.lnk」として入るので、生成時にそのショートカットの起動コマンドを読む
const pwaOrWeb = (title, icon, appName, url) => {
  const cmd = execFileSync('pwsh', ['-NoProfile', '-Command', `
    $l = Get-ChildItem "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs" -Recurse -Filter '${appName}.lnk' | Select-Object -First 1
    if ($l) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l.FullName); '"' + $s.TargetPath + '" ' + $s.Arguments }`], { encoding: 'utf8' }).trim();
  return cmd ? open(title, icon, cmd) : web(title, icon, url);
};

// AI ページ。上段は herdr の Space 1〜4（置いた列で何番目かが決まる）。2,1 の Codex 送信は公式プラグイン待ち。
// エンジニアリングでもターミナルを見ながら Space を切り替えたいので、両方のプロファイルに置く（ActionID が重ならないよう毎回作る）
const aiPage = () => ({
  '0,0': desk('herdr Space', 'space'),
  '1,0': desk('herdr Space', 'space'),
  '2,0': desk('herdr Space', 'space'),
  '3,0': desk('herdr Space', 'space'),
  '0,1': desk('Claude 5 時間', 'claude-5h'),
  '1,1': desk('Claude 7 日', 'claude-7d'),
  '3,1': open('Codex アプリ', 'codex-app', APP('OpenAI.Codex_2p2nqsd0c76g0!App')),
});

// エンジニアリングのリンクのページ
const linkPage = () => ({
  '0,0': open('ターミナル', 'terminal', PS('focus-app.ps1', '-Process WindowsTerminal -Launch wt.exe')),
  '1,0': open('VS Code', 'vscode', `"${VSCODE}"`),
  '2,0': open('Claude Code', 'claude-code', PS('start-agent.ps1', '-Kind claude')),
  '3,0': open('Codex', 'codex-cli', PS('start-agent.ps1', '-Kind codex')),
  '0,1': web('GitHub PR', 'github-pr', 'https://github.com/pulls'),
  '1,1': hotkey('範囲スクショ', 'screenshot', { win: true, shift: true, key: 'S' }),
  '2,1': hotkey('Meet ミュート', 'meet-mic', { ctrl: true, key: 'D' }),
  '3,1': hotkey('Meet カメラ', 'meet-camera', { ctrl: true, key: 'E' }),
});

// キーの位置は "列,行"。Infobar は Neo コントローラの "1,0" で、どのページも使用率を出す
const PROFILES = [
  {
    name: '通常',
    pages: [
      { // 普段使い
        '0,0': media('再生/停止', 'play-pause', 1),
        '1,0': media('ミュート', 'mute', 4),
        '2,0': pwaOrWeb('YouTube Music', 'youtube-music', 'YouTube Music', 'https://music.youtube.com/'),
        '3,0': open('Obsidian', 'obsidian', `"${OBSIDIAN}"`),
        '0,1': open('原神', 'genshin', TASK('Genshin')),
        '1,1': open('崩壊：スターレイル', 'hsr', TASK('HSR')),
        '2,1': desk('PC ⇄ Mac', 'switch-input'),
        '3,1': open('ロック', 'lock', 'rundll32.exe user32.dll,LockWorkStation'),
      },
      aiPage(),
      { // 会議中（Google Meet）
        '0,0': hotkey('マイク', 'mic', { ctrl: true, key: 'D' }),
        '1,0': hotkey('カメラ', 'camera', { ctrl: true, key: 'E' }),
        '2,0': hotkey('挙手', 'hand', { ctrl: true, alt: true, key: 'H' }),
        '3,0': hotkey('字幕', 'captions', { key: 'C' }),
        '0,1': hotkey('チャット', 'chat', { ctrl: true, alt: true, key: 'C' }),
        '1,1': hotkey('参加者', 'people', { ctrl: true, alt: true, key: 'P' }),
        '2,1': open('会議メモ', 'meeting-note', `"${OBSIDIAN}"`),
        '3,1': desk('経過時間', 'timer'),
      },
    ],
  },
  // Stream Deck はプロファイル 1 つに紐付けられるアプリが 1 つなので、同じ中身をアプリごとに作る。
  // 最初に出すページを指定しても取り込みで 1 ページ目に戻るので、ページの並びで決める: ターミナルは AI が先、VS Code はリンクが先
  { name: 'エンジニアリング（ターミナル）', app: TERMINAL, pages: [aiPage(), linkPage()] },
  { name: 'エンジニアリング（VS Code）', app: VSCODE, pages: [linkPage(), aiPage()] },
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
      if (!a.States[0].Image) continue;
      const img = a.States[0].Image.replace('Images/', '');
      copyFileSync(join(ICONS, img), join(pdir, 'Images', img));
    }
    writeFileSync(join(pdir, 'manifest.json'), JSON.stringify({
      Controllers: [
        { Actions: Object.keys(keys).length ? keys : null, Type: 'Keypad' },
        { Actions: { '1,0': desk('使用率（Infobar）', 'infobar') }, Type: 'Neo' },
      ],
      Icon: '', Name: '',
    }));
  };
  p.pages.forEach((keys, i) => writePage(pageIds[i], keys));
  writePage(defaultId, {});
  writeFileSync(join(dir, 'manifest.json'), JSON.stringify({
    // AppIdentifier は Stream Deck の「アプリケーション」の紐付けで、取り込んでも残る。
    ...(p.app ? { AppIdentifier: p.app } : {}),
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
