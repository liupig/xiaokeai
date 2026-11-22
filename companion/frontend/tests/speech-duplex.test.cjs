const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const source = (name) => fs.readFileSync(path.join(__dirname, '../src/features/voice', name), 'utf8');
const target = ts.ScriptTarget.ES2021;
const duplex = {};
vm.runInNewContext(ts.transpileModule(source('duplex.ts'), {
  compilerOptions: { target, module: ts.ModuleKind.CommonJS },
}).outputText, { exports: duplex });

const file = ts.createSourceFile('tts.ts', source('tts.ts'), target, true);
const player = file.statements.find(node => ts.isClassDeclaration(node) && node.name.text === 'SpeechPlayer');
const methodNames = ['resolveFor', 'isSameQa', 'remainingSec', 'audible', 'currentType', 'onUserBargeIn', 'applyTurnDuplex'];
const methods = player.members.filter(node => methodNames.includes(node.name?.getText(file)));
assert.equal(methods.length, methodNames.length);
const Probe = vm.runInNewContext(ts.transpile('(class {' + methods.map(node => node.getText(file)).join('\n') + '})', { target }), {
  ...duplex,
  estimateSpeechSec: () => 20,
  isSidecarClip: clip => clip?.duplexCmd === 'skip_on_new',
});

function makePlayer(secondsLeft) {
  const result = new Probe();
  Object.assign(result, {
    inputGen: 2, duplexCmd: 'interrupt', duplexRemainSec: 3, playing: true,
    currentClip: { inputGen: 1, kind: 'body' }, clipStartTime: 7,
    pending: [], waitQueue: [], ctx: { currentTime: 10 }, pcmHorizon: 10 + secondsLeft,
    ensureCtx() {},
  });
  return result;
}

test('uses the incoming sentence label and its active predecessor’s measured remaining audio', () => {
  const next = cmd => ({ inputGen: 2, kind: 'body', duplexCmd: cmd });
  const long = makePlayer(4);
  assert.equal(long.resolveFor(next('queue')), 'queue');
  assert.equal(long.resolveFor(next('interrupt_or_queue')), 'interrupt');
  assert.equal(long.resolveFor(next('conditional_queue')), 'skip');
  const short = makePlayer(2.9);
  assert.equal(short.resolveFor(next('interrupt_or_queue')), 'queue');
  assert.equal(short.resolveFor(next('interrupt')), 'interrupt');
  assert.equal(makePlayer(3).resolveFor(next('interrupt_or_queue')), 'queue');
  assert.equal(makePlayer(0).remainingSec(), 0);
});

test('keeps new reply segments in order without letting them hide the queue head', () => {
  const speech = makePlayer(4);
  const first = { inputGen: 2, kind: 'body', duplexCmd: 'interrupt_or_queue' };
  const second = { inputGen: 2, kind: 'body', duplexCmd: 'interrupt' };
  speech.pending.push(first);
  assert.equal(speech.resolveFor(second), 'queue');
  assert.equal(speech.resolveFor({ ...second, duplexCmd: 'skip' }), 'skip');
  speech.pending.push(second);
  assert.equal(speech.resolveFor(first, first), 'interrupt');
});

test('normal barge-in clears the old queue but leaves the current line available for the 3-second decision', () => {
  const speech = makePlayer(2);
  let dropped = 0;
  let cut = 0;
  speech.discardQueued = () => { dropped += 1; };
  speech.cutCurrent = () => { cut += 1; };
  speech.onUserBargeIn();
  assert.equal(dropped, 1);
  assert.equal(cut, 0);
  speech.onUserBargeIn(true);
  assert.equal(cut, 1);
  speech.currentClip.duplexCmd = 'skip_on_new';
  speech.onUserBargeIn();
  assert.equal(cut, 2);
});

test('latches the first model decision at its arrival and cuts at most once', () => {
  const long = makePlayer(4);
  const short = makePlayer(2);
  let cuts = 0;
  long.cutCurrent = short.cutCurrent = () => { cuts += 1; };
  long.applyTurnDuplex('interrupt_or_queue');
  long.applyTurnDuplex('interrupt');
  assert.equal(cuts, 1);
  assert.equal(long.turnDuplex.cmd, 'queue');
  short.applyTurnDuplex('interrupt_or_queue');
  short.applyTurnDuplex('interrupt');
  assert.equal(cuts, 1);
  assert.equal(short.turnDuplex.cmd, 'queue');
});
