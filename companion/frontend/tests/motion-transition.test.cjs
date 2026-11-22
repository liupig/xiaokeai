const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const THREE = require('three');
const ts = require('typescript');

function fixture() {
  const root = new THREE.Group();
  const shoulder = new THREE.Bone();
  shoulder.name = 'shoulder';
  const wrist = new THREE.Bone();
  wrist.name = 'wrist';
  shoulder.add(wrist);
  root.add(shoulder);
  const clips = {
    'a.fbx': new THREE.AnimationClip('a', 2, [
      new THREE.NumberKeyframeTrack('shoulder.position[x]', [0, 2], [1, 1]),
      new THREE.NumberKeyframeTrack('wrist.position[y]', [0, 2], [4, 4]),
    ]),
    'b.fbx': new THREE.AnimationClip('b', 2, [
      new THREE.NumberKeyframeTrack('shoulder.position[x]', [0, 2], [2, 2]),
    ]),
    'idle.fbx': new THREE.AnimationClip('idle', 2, [
      new THREE.QuaternionKeyframeTrack('shoulder.quaternion', [0, 1, 2], [
        0, 0, 0, 1, 0, 0.6, 0, 0.8, 0, 0, 0, 1,
      ]),
    ]),
  };
  const loads = [];
  const deps = {
    three: THREE,
    'three-stdlib': require('three-stdlib'),
    './mixamo': {
      createMixamoRig: () => ({
        bones: [shoulder, wrist], pairs: [{ source: 'mixamorigLeftShoulder', target: shoulder }],
      }),
      loadMixamoClip: async (url) => {
        loads.push(url);
        return clips[url];
      },
    },
    './xkMotion': {},
  };
  const source = fs.readFileSync(path.join(__dirname, '../src/engine/motion.ts'), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: (id) => deps[id] });
  const player = new exports.MotionPlayer();
  player.attach(root, 'glb');
  return { player, shoulder, wrist, loads };
}

test('cold and cached actions blend directly while clearing unkeyed bones', async () => {
  const { player, shoulder, wrist, loads } = fixture();
  assert.equal(await player.play('a.fbx'), true);
  player.update(0.5);
  assert.equal(wrist.position.y, 4);

  for (const [url, target, previous] of [['b.fbx', 2, 1], ['a.fbx', 1, 2]]) {
    let started = false;
    const switching = player.play(url, { onStart: () => { started = true; } });
    assert.equal(await switching, true);
    assert.equal(shoulder.position.x, previous);
    player.update(0.07);
    assert.ok(shoulder.position.x > 1 && shoulder.position.x < 2);
    assert.equal(started, false);
    player.update(0.5);
    assert.equal(shoulder.position.x, target);
    assert.equal(wrist.position.y, target === 2 ? 0 : 4);
    assert.equal(started, true);
  }
  assert.deepEqual(loads, ['a.fbx', 'b.fbx']);
});

test('a stopped action returns to the idle clip at its current phase', async () => {
  const { player, shoulder } = fixture();
  await player.loadIdle('idle.fbx');
  player.updateIdle(0.5);
  const idleFrame = shoulder.quaternion.clone();
  assert.ok(idleFrame.y > 0.2);
  assert.equal(await player.play('a.fbx'), true);
  player.update(0.5);
  assert.equal(shoulder.quaternion.y, 0);
  player.stop();
  player.update(0.5);
  assert.equal(player.active, false);
  assert.ok(Math.abs(shoulder.quaternion.dot(idleFrame)) > 0.9999);
  player.updateIdle(0.5);
  assert.ok(shoulder.quaternion.y > idleFrame.y);
});

test('stopping while an incoming action loads cancels the switch', async () => {
  const { player, shoulder } = fixture();
  assert.equal(await player.play('a.fbx'), true);
  player.update(0.5);
  const switching = player.play('b.fbx', { onStart: () => assert.fail('cancelled action started') });
  player.stop();
  player.update(0.5);
  assert.equal(await switching, false);
  assert.equal(shoulder.position.x, 0);
  assert.equal(player.active, false);
});
