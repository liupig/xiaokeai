const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function fixture() {
  const listeners = {};
  const window = { addEventListener: (name, fn) => { listeners[name] = fn; } };
  let bg = '/original.jpg';
  let platform = true;
  const stage = {
    getBackgroundUrl: () => bg,
    setBackground: (_color, url) => { bg = url || ''; listeners['xiaokeai:stage-background']?.({ detail: bg }); },
    setStagePlatform: opts => { platform = !!opts.show; },
    getPlatformVisible: () => platform,
  };
  const character = { currentId: 1 };
  const deps = {
    vue: { reactive: x => x },
    '../../engine/stage': { stage },
    '../../stores/settings': { useSettingsStore: () => ({ quality: { background_color: '#111', stage_show: true } }) },
    '../shell/mode': { isPetShell: false },
    '../../stores/character': { useCharacterStore: () => character },
  };
  const source = fs.readFileSync(require('node:path').join(__dirname, '../src/features/life/stageLife.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => { if (!(id in deps)) throw new Error(id); return deps[id]; }, window });
  return { life: exports, stage, character };
}

test('home, destination and preview restore the original stage only on explicit exit', async () => {
  const { life, stage } = fixture();
  assert.equal(life.enterLifeStage(), true);
  assert.equal(stage.getPlatformVisible(), false);
  assert.equal(stage.getBackgroundUrl(), '/assets/life/room.jpg');
  life.setLifeHome('villa', true);
  assert.equal(stage.getBackgroundUrl(), '/assets/life/villa.jpg');
  life.endLifePreview();
  assert.equal(stage.getBackgroundUrl(), '/assets/life/room.jpg');
  await life.beginMeal('hotpot');
  assert.equal(stage.getBackgroundUrl(), '/assets/life/hotpot_restaurant.jpg');
  life.returnLifeHome();
  assert.equal(stage.getBackgroundUrl(), '/assets/life/room.jpg');
  life.leaveLifeStage();
  assert.equal(stage.getBackgroundUrl(), '/original.jpg');
  assert.equal(stage.getPlatformVisible(), true);
  assert.equal(life.stageLife.active, false);
});

test('explicit external background takes ownership and cannot be overwritten on exit', () => {
  const { life, stage } = fixture();
  life.enterLifeStage();
  stage.setBackground('#111', '/chosen-scene.jpg');
  assert.equal(life.stageLife.active, false);
  assert.equal(stage.getPlatformVisible(), true);
  life.leaveLifeStage();
  assert.equal(stage.getBackgroundUrl(), '/chosen-scene.jpg');
});

test('catalog themes keep their identity while rendering their configured artwork', async () => {
  const { life, stage } = fixture();
  life.configureLifeItems([
    { id: 'loft', category: 'home', art: 'apartment' },
    { id: 'tomato_noodles', category: 'meal', art: 'noodles', destination: 'restaurant' },
    { id: 'city_bike', category: 'vehicle', art: 'bicycle', destination: 'park' },
  ]);
  life.setLifeHome('loft');
  life.enterLifeStage();
  assert.equal(stage.getBackgroundUrl(), '/assets/life/apartment.jpg');
  await life.beginMeal('tomato_noodles');
  assert.equal(life.stageLife.activity, 'tomato_noodles');
  assert.equal(life.stageLife.activityArt, 'noodles');
  await life.beginRide('city_bike');
  assert.equal(life.stageLife.activity, 'city_bike');
  assert.equal(life.stageLife.activityArt, 'bicycle');
});

test('life interaction is one-shot and only consumed by a life reply', () => {
  const { life } = fixture();
  life.enterLifeStage();
  life.setLifeInteraction('preview', 'tomato_noodles');
  assert.equal(life.lifeChatContext(1).interaction, null);
  assert.equal(life.lifeChatContext(1, true).interaction.item_id, 'tomato_noodles');
  assert.equal(life.lifeChatContext(1, true).interaction, null);
});

test('reapplying the life stage keeps the original background and character context isolated', () => {
  const { life, stage, character } = fixture();
  life.enterLifeStage();
  life.refreshLifeStage();
  assert.equal(life.lifeChatContext(1).active, true);
  character.currentId = 2;
  assert.equal(life.lifeChatContext(2), undefined);
  life.setLifeCharacter(2);
  assert.equal(life.lifeChatContext(2).active, true);
  assert.equal(life.lifeChatContext(1), undefined);
  life.leaveLifeStage();
  assert.equal(stage.getBackgroundUrl(), '/original.jpg');
});

 test('an in-flight automatic scene response cannot replace a space entered meanwhile', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const life = { active: false };
  const stage = { setBackground: () => { throw new Error('background should not change'); } };
  const deps = {
    vue: { reactive: x => x },
    '../../api/client': { api: { listScenes: async () => [], getCurrentScene: () => pending } },
    '../../stores/character': { useCharacterStore: () => ({ currentId: 1 }) },
    '../../stores/settings': { useSettingsStore: () => ({ modules: { scenes: true }, quality: {} }) },
    '../../engine/stage': { stage },
    '../performance/shotConductor': { shots: {} },
    '../../i18n': { featureOn: () => true, replyLang: () => 'zh-CN' },
    './catalog': { LOCAL_SCENES: [{ id: 'old' }], scenePool: () => [] },
    '../keepsake/session': { noteSceneTookBg: () => {} },
    '../life/stageLife': { stageLife: life },
  };
  const source = fs.readFileSync(require('node:path').join(__dirname, '../src/features/scenes/session.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  const localStorage = { getItem: () => null, setItem: () => {} };
  vm.runInNewContext(code, { exports, require: id => { if (!(id in deps)) throw new Error(id); return deps[id]; }, localStorage });
  const result = exports.restoreOrRotateScene({ characterId: 1, lastChatAt: 0 });
  await new Promise(resolve => setImmediate(resolve));
  life.active = true;
  finish({ card: { id: 'new', background: '/new.jpg' }, rotated: true });
  const value = await result;
  assert.equal(value.rotated, false);
  assert.equal(exports.sceneSession.current, null);
});
