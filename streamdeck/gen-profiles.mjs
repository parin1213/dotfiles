// Stream Deck Neo のプロファイル（通常 / エンジニアリング）を生成する。実行したマシンの OS 用のものを作る。
// 標準アクションと自作プラグイン（plugin/）のキーを置く。公式プラグインが要るキーは空けておく。
// 出力はプラグインに同梱するプロファイル（plugin/io.github.parin1213.desk.sdPlugin/profiles/<file>.streamDeckProfile、中身は ProfilesV3 と同じ構造）。
// 同梱するのは、プラグインがページを移れるのが同梱のプロファイルだけだから（右下のページキーが使う）。取り込みは README を参照。
// キー画像は make-icons.ps1（Mac のアプリは make-icons-mac.sh）が作る icons/*.png を使う。
import { mkdirSync, writeFileSync, rmSync, copyFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { basename, join } from 'node:path';
import { execFileSync } from 'node:child_process';

const OUT = join(import.meta.dirname, 'plugin', 'io.github.parin1213.desk.sdPlugin', 'profiles');
const ICONS = join(import.meta.dirname, 'icons');
const DEVICE = { Model: '20GBJ9901', UUID: '@(1)[4057/154/A7BSA5371M1QN6]' };
const mac = process.platform === 'darwin';

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

// 修飾キーのビットは既定プロファイルの実例（Ctrl = 2、Win = 8）に合わせ、Shift = 1、Alt = 4 とした。
// Mac では Win の位置が Command、Alt の位置が Option になる
const EMPTY_KEY = { KeyCmd: false, KeyCtrl: false, KeyModifiers: 0, KeyOption: false, KeyShift: false, NativeCode: 146, QTKeyCode: 33554431, VKeyCode: -1 };
const hotkey = (title, icon, { ctrl = false, alt = false, shift = false, win = false, key }) => {
  const vk = key.charCodeAt(0);
  const first = {
    KeyCmd: win, KeyCtrl: ctrl, KeyModifiers: (shift ? 1 : 0) | (ctrl ? 2 : 0) | (alt ? 4 : 0) | (win ? 8 : 0),
    KeyOption: alt, KeyShift: shift, NativeCode: vk, QTKeyCode: vk, VKeyCode: vk,
  };
  return action('com.elgato.streamdeck.system.hotkey', 'Hotkey', title, icon, { Coalesce: true, Hotkeys: [first, EMPTY_KEY, EMPTY_KEY, EMPTY_KEY] });
};
// Mac のホットキー。形は Stream Deck 同梱の Mac 用既定プロファイル（⌘Z、⇧⌘5、⌃⌘Space）に合わせた:
// NativeCode と VKeyCode はどちらも macOS の仮想キーコード（kVK_ANSI_*）、QTKeyCode は Qt のキーコード（英数字は大文字の文字コード）。
// 空きの枠も Mac の形（NativeCode = -1）にする
const MAC_KEYCODE = { A: 0, S: 1, D: 2, H: 4, C: 8, Q: 12, E: 14, P: 35, 4: 21 };
const MAC_EMPTY_KEY = { KeyCmd: false, KeyCtrl: false, KeyModifiers: 0, KeyOption: false, KeyShift: false, NativeCode: -1, QTKeyCode: 33554431, VKeyCode: -1 };
const macHotkey = (title, icon, { cmd = false, ctrl = false, opt = false, shift = false, key }) => {
  const code = MAC_KEYCODE[key];
  const first = {
    KeyCmd: cmd, KeyCtrl: ctrl, KeyModifiers: (shift ? 1 : 0) | (ctrl ? 2 : 0) | (opt ? 4 : 0) | (cmd ? 8 : 0),
    KeyOption: opt, KeyShift: shift, NativeCode: code, QTKeyCode: key.charCodeAt(0), VKeyCode: code,
  };
  return action('com.elgato.streamdeck.system.hotkey', 'Hotkey', title, icon, { Coalesce: true, Hotkeys: [first, MAC_EMPTY_KEY, MAC_EMPTY_KEY, MAC_EMPTY_KEY] });
};

// 自作プラグインのアクション。絵はプラグインが実行中に描くので、画像は持たせない
const DESK = { Name: 'Desk', UUID: 'io.github.parin1213.desk', Version: '0.1.0.0' };
// icon を渡すと、プラグインが絵を描く前とプラグインが絵を描かないキー（コマンド実行）にその画像を出す
const desk = (name, id, settings = {}, icon) => ({
  ActionID: randomUUID(), LinkedTitle: false, Name: name, Plugin: DESK,
  Resources: null, Settings: settings, State: 0,
  States: [icon ? { Image: `Images/${icon}.png`, ShowTitle: false, Title: name } : { ShowTitle: false }], UUID: `${DESK.UUID}.${id}`,
});
// 右下のページキー。profile は manifest の Profiles の Name（profiles/<file>）で、押したときの移り先に使う
const PAGES = 4;
const pageKey = (file, page) => desk('ページ', 'page', { profile: `profiles/${file}`, page, pages: PAGES });

// ---- Windows ---------------------------------------------------------------
// プロファイルの中身は関数に閉じ込め、Windows 用の値を引くコマンド（pwsh）は Windows で生成するときだけ走らせる
function windowsProfiles() {

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
  const pwaCmds = new Map();
  const pwaOrWeb = (title, icon, appName, url) => {
    if (!pwaCmds.has(appName)) pwaCmds.set(appName, execFileSync('pwsh', ['-NoProfile', '-Command', `
      $l = Get-ChildItem "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs" -Recurse -Filter '${appName}.lnk' | Select-Object -First 1
      if ($l) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l.FullName); '"' + $s.TargetPath + '" ' + $s.Arguments }`], { encoding: 'utf8' }).trim());
    const cmd = pwaCmds.get(appName);
    return cmd ? open(title, icon, cmd) : web(title, icon, url);
  };

  // ページは 3 つのプロファイル全部に置くので関数にして、プロファイルごとに作る（ActionID が重ならないように）。
  // 普段使い
  const mainPage = (f) => ({
    '0,0': media('再生/停止', 'play-pause', 1),
    '1,0': pwaOrWeb('YouTube Music', 'youtube-music', 'YouTube Music', 'https://music.youtube.com/'),
    '2,0': open('Obsidian', 'obsidian', `"${OBSIDIAN}"`),
    '3,0': open('ロック', 'lock', 'rundll32.exe user32.dll,LockWorkStation'),
    '0,1': open('原神', 'genshin', TASK('Genshin')),
    '1,1': open('崩壊：スターレイル', 'hsr', TASK('HSR')),
    '2,1': desk('PC ⇄ Mac', 'switch-input'),
    '3,1': pageKey(f, 1),
  });

  // AI ページ。上段は herdr の Space 1〜4（置いた列で何番目かが決まる）。Claude と Codex の使用率は Infobar に出るのでキーは置かない。
  // 2,1 の Codex 送信は公式プラグイン待ち
  const codexApp = () => open('Codex アプリ', 'codex-app', APP('OpenAI.Codex_2p2nqsd0c76g0!App'));
  const aiPage = (f) => ({
    '0,0': desk('herdr Space', 'space'),
    '1,0': desk('herdr Space', 'space'),
    '2,0': desk('herdr Space', 'space'),
    '3,0': desk('herdr Space', 'space'),
    '0,1': codexApp(),
    '3,1': pageKey(f, 2),
  });

  // 会議中（Google Meet）
  const meetPage = (f) => ({
    '0,0': hotkey('マイク', 'mic', { ctrl: true, key: 'D' }),
    '1,0': hotkey('カメラ', 'camera', { ctrl: true, key: 'E' }),
    '2,0': hotkey('挙手', 'hand', { ctrl: true, alt: true, key: 'H' }),
    '3,0': hotkey('字幕', 'captions', { key: 'C' }),
    '0,1': hotkey('チャット', 'chat', { ctrl: true, alt: true, key: 'C' }),
    '1,1': hotkey('参加者', 'people', { ctrl: true, alt: true, key: 'P' }),
    '2,1': open('会議メモ', 'meeting-note', `"${OBSIDIAN}"`),
    '3,1': pageKey(f, 3),
  });

  // リンク（ターミナル・エディタ・エージェント・GitHub）
  const linkPage = (f) => ({
    '0,0': open('ターミナル', 'terminal', PS('focus-app.ps1', '-Process WindowsTerminal -Launch wt.exe')),
    '1,0': open('VS Code', 'vscode', `"${VSCODE}"`),
    '2,0': open('Claude Code', 'claude-code', PS('start-agent.ps1', '-Kind claude')),
    '3,0': open('Codex', 'codex-cli', PS('start-agent.ps1', '-Kind codex')),
    '0,1': web('GitHub PR', 'github-pr', 'https://github.com/pulls'),
    '1,1': hotkey('範囲スクショ', 'screenshot', { win: true, shift: true, key: 'S' }),
    '2,1': codexApp(),
    '3,1': pageKey(f, 4),
  });

  // キーの位置は "列,行"。Infobar は Neo コントローラの "1,0" で、どのページも使用率を出す。
  // 右下 "3,1" はどのページもページ番号キーにそろえる
  return profiles((f) => [mainPage(f), aiPage(f), meetPage(f), linkPage(f)], TERMINAL, VSCODE);
}

// ---- Mac -------------------------------------------------------------------
// Mac の「開く」は .app かファイルを開くだけで、引数付きのコマンドは走らせられない。
// 引数の要るものは自作プラグインのコマンド実行キー（run）で、未読数を出したいアプリはアプリキー（app）で置く
function macProfiles() {
  const APPS = '/Applications';
  const CHROME_APPS = join(homedir(), 'Applications', 'Chrome Apps.localized');
  const GHOSTTY = `${APPS}/Ghostty.app`;
  const VSCODE = `${APPS}/Visual Studio Code.app`;
  // アプリキーの絵はプラグインが icons/ から描く。プロファイルに画像を入れると Stream Deck はそれを
  // ユーザーが決めた画像として扱い、プラグインからの差し替え（未読数のバッジ）を無視するので入れない
  const app = (title, icon, path, badge) => desk(title, 'app', { path, icon, ...(badge ? { badge } : {}) });
  const run = (title, icon, cmd, args = []) => desk(title, 'run', { cmd, args }, icon);
  // ブラウザでインストールしたアプリ（PWA）があればそれを開き、無ければサイトを開く
  const pwaOrWeb = (title, icon, appName, url) => {
    const p = join(CHROME_APPS, `${appName}.app`);
    return existsSync(p) ? open(title, icon, p) : web(title, icon, url);
  };

  // 普段使い。Mac は仕事で使うので、使っている時間の長い Slack・カレンダー・Notion・Google ドライブを上段に置く。
  // 右下をページ番号キーに空けるため、ロックのキーは置かない（PC ⇄ Mac がロックも兼ね、席を外すだけなら ⌃⌘Q）
  const mainPage = (f) => ({
    '0,0': app('Slack', 'slack', `${APPS}/Slack.app`, 'Slack'),
    '1,0': web('Google カレンダー', 'google-calendar', 'https://calendar.google.com/'),
    '2,0': web('Notion', 'notion', 'https://app.notion.com/'),
    '3,0': web('Google ドライブ', 'google-drive', 'https://drive.google.com/'),
    '0,1': media('再生/停止', 'play-pause', 1),
    '1,1': pwaOrWeb('YouTube Music', 'youtube-music', 'YouTube Music', 'https://music.youtube.com/'),
    '2,1': desk('PC ⇄ Mac', 'switch-input'),
    '3,1': pageKey(f, 1),
  });
  const chatgpt = () => app('ChatGPT', 'chatgpt', `${APPS}/ChatGPT.app`);
  const aiPage = (f) => ({
    '0,0': desk('herdr Space', 'space'),
    '1,0': desk('herdr Space', 'space'),
    '2,0': desk('herdr Space', 'space'),
    '3,0': desk('herdr Space', 'space'),
    '0,1': chatgpt(),
    '3,1': pageKey(f, 2),
  });
  // 会議中（Google Meet）。Mac の Meet は Ctrl の代わりに Command、Ctrl+Alt の代わりに Command+Control
  const meetPage = (f) => ({
    '0,0': macHotkey('マイク', 'mic', { cmd: true, key: 'D' }),
    '1,0': macHotkey('カメラ', 'camera', { cmd: true, key: 'E' }),
    '2,0': macHotkey('挙手', 'hand', { cmd: true, ctrl: true, key: 'H' }),
    '3,0': macHotkey('字幕', 'captions', { key: 'C' }),
    '0,1': macHotkey('チャット', 'chat', { cmd: true, ctrl: true, key: 'C' }),
    '1,1': macHotkey('参加者', 'people', { cmd: true, ctrl: true, key: 'P' }),
    '2,1': web('会議メモ', 'meeting-note', 'https://app.notion.com/'),
    '3,1': pageKey(f, 3),
  });
  const linkPage = (f) => ({
    // 「開く」は起動済みなら前面に出すだけなので、Windows の focus-app.ps1 に当たる処理は要らない
    '0,0': open('ターミナル', 'ghostty', GHOSTTY),
    '1,0': open('VS Code', 'vscode', VSCODE),
    '2,0': run('Claude Code', 'claude-code', 'start-agent.sh', ['claude']),
    '3,0': run('Codex', 'codex-cli', 'start-agent.sh', ['codex']),
    '0,1': web('GitHub PR', 'github-pr', 'https://github.com/pulls'),
    '1,1': macHotkey('範囲スクショ', 'screenshot', { cmd: true, shift: true, key: '4' }),
    '2,1': chatgpt(),
    '3,1': pageKey(f, 4),
  });

  return profiles((f) => [mainPage(f), aiPage(f), meetPage(f), linkPage(f)], GHOSTTY, VSCODE);
}

// 3 つのプロファイルは同じ 4 ページ（普段使い / AI / 会議中 / リンク）を同じ順で持つ。どのアプリが前にいても同じようにページを開けるようにするため。
// それでも分けるのは、Stream Deck がプロファイル 1 つにアプリ 1 つしか紐付けられず、開いていたページはプロファイルごとに覚えるから
// （ターミナルでは AI、VS Code ではリンクを開いたままにしておける）
// file は同梱するファイルの名前（manifest の Profiles と合わせる）
const profiles = (pages, terminal, editor) => [
  { name: '通常', file: 'normal', pages: pages('normal') },
  { name: 'エンジニアリング（ターミナル）', file: 'terminal', app: terminal, pages: pages('terminal') },
  { name: 'エンジニアリング（VS Code）', file: 'vscode', app: editor, pages: pages('vscode') },
];

const PROFILES = mac ? macProfiles() : windowsProfiles();

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
    // AppIdentifier は Stream Deck の「アプリケーション」の紐付けで、取り込んでも残る。Windows は exe、Mac は .app のパス
    ...(p.app ? { AppIdentifier: p.app } : {}),
    Device: DEVICE, Name: p.name,
    Pages: { Current: pageIds[0], Default: defaultId, Pages: pageIds },
    Version: '3.0',
  }));

  // .streamDeckProfile は .sdProfile フォルダを丸ごと zip にしたもの
  const zip = join(OUT, `${p.file}.zip`);
  const dest = join(OUT, `${p.file}.streamDeckProfile`);
  if (mac) {
    rmSync(dest, { force: true });
    execFileSync('zip', ['-qrX', dest, basename(dir)], { cwd: build });
  } else {
    execFileSync('pwsh', ['-NoProfile', '-Command',
      `Compress-Archive -LiteralPath '${dir}' -DestinationPath '${zip}' -Force; Move-Item -LiteralPath '${zip}' -Destination '${dest}' -Force`]);
  }
  rmSync(build, { recursive: true, force: true });
  console.log(`${p.name}: ${dest}`);
}
