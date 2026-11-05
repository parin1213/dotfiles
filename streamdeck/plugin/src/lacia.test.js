import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { LaciaMotion, frameAt, overlayLacia, PageLacia, overlayPageLacia } from './lacia.js';
const frames = JSON.parse(readFileSync(new URL('./lacia-frames.json', import.meta.url), 'utf8').replace(/^\uFEFF/, '')).idle.frames;
const animations = {idle: {frames}};
const fresh = { fresh: true, working: true };
const slow = new LaciaMotion(), fast = new LaciaMotion();
for (let i=0;i<10;i++) { slow.advance(.1, {...fresh,cpu:0,memory:0}); fast.advance(.1, {...fresh,cpu:1,memory:1}); }
assert(fast.x > slow.x);
assert.equal(fast.gait,'run'); assert.equal(slow.gait,'walk');
const x=slow.x;
assert.equal(slow.advance(.1,{fresh:true,working:false}).x,x);
assert.equal(slow.advance(.1,{...fresh,blocked:true}).visible,false);
assert.equal(slow.advance(.1,{...fresh,fresh:false}).visible,false);
assert.equal(slow.advance(.1,{...fresh,enabled:false}).visible,false);
for(let i=0;i<2000;i++){ const pose=fast.advance(.1,fresh); assert(pose.x>=0 && pose.x<=524); }
const base='data:image/svg+xml;base64,'+Buffer.from('<svg width="144" height="144"><rect width="144" height="144" fill="black"/></svg>').toString('base64');
const pose={visible:true,x:140,direction:1,animationMs:0};
const left=overlayLacia(base,0,pose,animations),right=overlayLacia(base,1,pose,animations);
assert.notEqual(left,base);assert.notEqual(right,base);
assert.equal(overlayLacia(base,2,pose,animations),base);
assert.equal(overlayLacia(base,0,{visible:false},animations),base);
const replacement={idle:{frames},move:{frames:[{ms:100,png:'replacement'}]}};
assert(Buffer.from(overlayLacia(base,0,{...pose,animation:'move'},replacement).split(',')[1],'base64').toString().includes('replacement'));
assert.equal(frameAt(frames,frames.reduce((s,f)=>s+f.ms,0)),frames[0]);
console.log('PASS: load speed, idle, approval priority, stale state, disable, bounds, cross-key composition, frame duration.');
console.log(JSON.stringify({frames:frames.length,slowX:slow.x,fastX:fast.x}));

const dirs={idle:{frames},right:{frames:[{ms:100,png:'RIGHT'}]},left:{frames:[{ms:100,png:'LEFT'}]}};
for (const [direction,expected] of [[1,'RIGHT'],[-1,'LEFT']]) {
  const image=Buffer.from(overlayLacia(base,0,{...pose,animation:'move',direction},dirs).split(',')[1],'base64').toString();
  assert(image.includes(expected)); assert(!image.includes('scale(-1 1)'));
}

const titleBase='data:image/svg+xml;base64,'+Buffer.from('<svg><rect/><text x="10" y="20" fill="white">タイトル</text></svg>').toString('base64');
const titleSvg=Buffer.from(overlayLacia(titleBase,0,{...pose,x:10},animations).split(',')[1],'base64').toString();
assert(titleSvg.indexOf('<image') < titleSvg.indexOf('<text'));
assert(titleSvg.includes('stroke="#111827" stroke-width="3"'));
assert.equal((titleSvg.match(/タイトル/g)||[]).length,2);
assert.equal(overlayLacia(titleBase,0,{visible:false},animations),titleBase);

const bank=JSON.parse(readFileSync(new URL('./lacia-frames.json',import.meta.url),'utf8'));
for(const direction of ['left','right']) {
 assert.deepEqual(bank[`walk-${direction}`].frames.map(f=>f.ms),Array(8).fill(120));
 assert.deepEqual(bank[`run-${direction}`].frames.map(f=>f.ms),[40,80,80,80,80,80,80,40]);
}
const g=new LaciaMotion();
assert.equal(g.advance(.1,{...fresh,cpu:.66}).animation,'run');
assert.equal(g.advance(.1,{...fresh,cpu:.55}).animation,'run');
assert.equal(g.advance(.1,{...fresh,cpu:.44,memory:.74}).animation,'walk');
assert.equal(g.advance(.1,{...fresh,memory:.86}).animation,'run');
const run=bank['run-right'].frames;
assert.equal(frameAt(run,39),run[0]); assert.equal(frameAt(run,40),run[1]);
assert.equal(frameAt(run,519),run[6]); assert.equal(frameAt(run,520),run[7]);

const idlePet=new PageLacia(1000,()=>0);
assert.equal(idlePet.frame(30999).elapsed,0); assert.equal(idlePet.frame(31200).name,'idle');
assert.equal(idlePet.frame(31400).elapsed,200); assert.equal(idlePet.frame(32400).elapsed,0);
assert(idlePet.next>=62400);
const walkPet=new PageLacia(0,()=>.6); assert.equal(walkPet.frame(66000).name,'walk-right');
const runPet=new PageLacia(0,()=>.95); assert.equal(runPet.frame(87000).name,'run-right');
const pageSvg=Buffer.from(overlayPageLacia(titleBase,'ABC').split(',')[1],'base64').toString();
assert(pageSvg.indexOf('<image')<pageSvg.indexOf('<text')); assert(pageSvg.includes('ABC'));

const wander=new PageLacia(0,()=>.6);
assert.equal(wander.frame(66000).x,0);
assert.deepEqual(wander.frame(66300),{name:'walk-right',elapsed:300,x:6});
assert.deepEqual(wander.frame(66600),{name:'walk-right',elapsed:600,x:12});
assert.deepEqual(wander.frame(66900),{name:'walk-right',elapsed:900,x:18});
assert.equal(wander.frame(67200).x,24);
assert.equal(wander.frame(100000).x,24);
assert.equal(wander.frame(133200).name,'walk-left');
assert.equal(wander.frame(134400).x,0);
const clipped=Buffer.from(overlayPageLacia(titleBase,'ABC',999).split(',')[1],'base64').toString();
assert(clipped.includes('x="32" y="56" width="88"'));
