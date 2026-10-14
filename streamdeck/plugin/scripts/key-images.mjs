// プラグインが絵を描く前（Stream Deck の起動直後など）に出るキーの既定画像を、render.js と同じ絵で作る。
// manifest.json の States.Image がこれを指す。実行: pnpm build（build の中で呼ぶ）
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { limitKey, pageKey, spaceKey, switchKey, timerKey } from '../src/render.js';

const dir = join(import.meta.dirname, '..', 'io.github.parin1213.desk.sdPlugin', 'imgs', 'keys');
mkdirSync(dir, { recursive: true });
const images = {
  space: spaceKey('', null),
  'claude-5h': limitKey('Claude 5h', null),
  'claude-7d': limitKey('Claude 7d', null),
  timer: timerKey(null),
  switch: switchKey(false, process.platform === 'win32' ? 'Mac' : 'PC'),
  page: pageKey(1, 4, null),
};
for (const [name, url] of Object.entries(images)) {
  writeFileSync(join(dir, `${name}.svg`), Buffer.from(url.split(',')[1], 'base64'));
}
console.log(`既定画像を ${dir} に書いた`);
