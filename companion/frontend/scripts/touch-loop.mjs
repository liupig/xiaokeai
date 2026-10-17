/**
 * 触碰闭环：连续摸同一处会从护住走到腻、麻、不理；
 * 凉一会儿又能回来。不连浏览器，逻辑自己跑完。
 *
 * node --experimental-strip-types scripts/touch-loop.mjs
 */
import { decideTouch } from '../src/features/touch/decide.ts';
import { pickLine, touchBrief } from '../src/features/touch/lines.ts';
import {
  commitTouch, emptyTouch, liveZone, loadTouch, recentSpeech, saveTouch,
} from '../src/features/touch/memory.ts';

const bag = new Map();
globalThis.localStorage = {
  getItem: (k) => (bag.has(k) ? bag.get(k) : null),
  setItem: (k, v) => bag.set(k, String(v)),
};

let failed = 0;
function check(cond, msg) {
  if (cond) console.log(`ok  ${msg}`);
  else {
    failed += 1;
    console.error(`FAIL ${msg}`);
  }
}

function roll(mem, zone, now, extra = {}) {
  const live = liveZone(mem.zones[zone], zone, now);
  return decideTouch({
    zone,
    hour: extra.hour ?? 21,
    bond: mem.bond,
    knownMs: Math.max(0, now - mem.knownSince),
    idleMs: extra.idleMs ?? 400,
    sessionMs: extra.sessionMs ?? 5 * 60000,
    heat: live.heat,
    streak: live.streak,
    boundary: extra.boundary ?? 'free',
    speechRecent: recentSpeech(mem, now),
    muted: mem.muteUntil > now,
    recentPoses: mem.recentPoses,
    rng: extra.rng ?? Math.random,
  });
}

function apply(mem, zone, now, decision, spoken = '') {
  commitTouch(mem, zone, now, {
    heatAdd: decision.heatAdd,
    bondDelta: decision.bondDelta,
    muteMs: spoken ? decision.muteMs : 0,
    pose: decision.pose,
    spoken,
  });
}

const soft = new Set(['fond', 'shy', 'play', 'cover', 'dodge']);
const hard = new Set(['bored', 'numb', 'ignore', 'disdain']);

const head = emptyTouch(1_700_000_000_000, 0.45);
head.knownSince -= 12 * 86400000;
const headTones = new Set();
for (let i = 0; i < 30; i += 1) {
  const d = roll(head, 'head', head.knownSince + 12 * 86400000, {
    idleMs: 3600000,
    rng: () => (i % 10) / 10,
  });
  headTones.add(d.tone);
  check(d.pose, `摸头第 ${i} 次有姿态 ${d.tone}`);
  check(soft.has(d.tone), `摸头第 ${i} 次还软：${d.tone}`);
}
check(headTones.size >= 2, `摸头不是只有一种：${[...headTones].join(',')}`);

let now = 1_700_000_000_000;
const chest = emptyTouch(now, 0.42);
chest.knownSince = now - 10 * 86400000;
const chestLog = [];
for (let i = 0; i < 8; i += 1) {
  const d = roll(chest, 'chest', now, { idleMs: i === 0 ? 3600000 : 400, rng: () => 0.5 });
  const live = liveZone(chest.zones.chest, 'chest', now);
  chestLog.push(`${i}:${d.tone}/h${live.heat.toFixed(2)}/s${live.streak}`);
  if (i === 0) check(soft.has(d.tone) && d.pose, `第一下摸胸还在推让或害羞：${d.tone}`);
  if (i >= 4) check(hard.has(d.tone), `连摸第 ${i} 下已经腻了：${d.tone}`);
  if (i >= 4) check(!d.speak, `连摸第 ${i} 下不再开口`);
  apply(chest, 'chest', now, d, '');
  now += 400;
}
console.log('  chest', chestLog.join(' '));
check(chest.zones.chest.streak === 8, `连摸记了 8 下，实际 ${chest.zones.chest.streak}`);
check(chest.zones.chest.heat > 0.85, `胸口还热着 ${chest.zones.chest.heat.toFixed(2)}`);

const cooledAt = now + 180000;
const cooledHeat = liveZone(chest.zones.chest, 'chest', cooledAt).heat;
const cooled = roll(chest, 'chest', cooledAt, { idleMs: 180000, rng: () => 0.2 });
check(cooledHeat < 0.45, `三分钟后热度退到 ${cooledHeat.toFixed(2)}`);
check(soft.has(cooled.tone), `凉了之后又肯反应：${cooled.tone}`);

let fondOnStrict = 0;
const strict = emptyTouch(now, 0.3);
strict.knownSince = now - 3600000;
for (let i = 0; i < 20; i += 1) {
  const d = roll(strict, 'chest', now, { boundary: 'strict', idleMs: 3600000, rng: () => i / 20 });
  if (d.tone === 'fond') fondOnStrict += 1;
}
check(fondOnStrict === 0, '尺度偏严时摸胸不会亲昵');

const muteMem = emptyTouch(now, 0.7);
muteMem.knownSince = now - 40 * 86400000;
muteMem.muteUntil = now + 10000;
const muted = roll(muteMem, 'head', now, { idleMs: 1000, rng: () => 0.01 });
check(!muted.speak, '冷淡过之后这段时间不再开口');

const speakMem = emptyTouch(now, 0.7);
speakMem.knownSince = now - 40 * 86400000;
speakMem.speechAt = [now - 1000, now - 2000, now - 3000, now - 4000];
const talkedOut = roll(speakMem, 'head', now, { idleMs: 3600000, rng: () => 0.01 });
check(!talkedOut.speak, '两分钟里说过四次就不再说');

const lineA = pickLine('zh-CN', 'chest', 'cover', '');
const lineB = pickLine('zh-CN', 'chest', 'cover', lineA);
check(lineA !== lineB, '同一句不连着说两遍');
const brief = touchBrief('zh-CN', {
  zone: 'chest', tone: 'cover', bond: 0.4,
  knownMs: 3 * 86400000, idleMs: 7200000, sessionMs: 18 * 60000,
  hour: 23, streak: 4, boundary: 'free', lastSpoken: lineA,
});
check(brief.includes('胸') && brief.includes('护住') && brief.includes('不要重复'), '开口简报带着位置、态度和上一句');

saveTouch(7, chest);
const loaded = loadTouch(7, cooledAt, 0.2);
check(Math.abs(loaded.bond - chest.bond) < 0.001, '亲疏写进本地后还在');
check(loaded.zones.chest.streak === 8, '连摸次数写进本地后还在');
check(loaded.knownSince === chest.knownSince, '见面时间写进本地后还在');

if (failed) {
  console.error(`\n${failed} 项没过`);
  process.exit(1);
}
console.log('\n触碰闭环通过');
