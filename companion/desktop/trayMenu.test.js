'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeTrayLocale,
  trayLabels,
  normalizeTrayPrefs,
  applyTrayPatch,
  shouldHideToTray,
} = require('./trayMenu');

test('没写过的开关默认都收进托盘', () => {
  assert.deepEqual(normalizeTrayPrefs(null), { minimize: true, close: true });
  assert.deepEqual(normalizeTrayPrefs({}), { minimize: true, close: true });
});

test('只有明确的 false 才会关掉', () => {
  assert.deepEqual(normalizeTrayPrefs({ minimize: false }), { minimize: false, close: true });
  assert.deepEqual(normalizeTrayPrefs({ close: false, minimize: false }), { minimize: false, close: false });
  assert.deepEqual(normalizeTrayPrefs({ close: 0, minimize: 'no' }), { minimize: true, close: true });
});

test('改一个开关不动另一个', () => {
  const next = applyTrayPatch({ minimize: false, close: true }, { close: false });
  assert.deepEqual(next, { minimize: false, close: false });
});

test('正在退出或换窗口时，关闭和最小化都放行', () => {
  const prefs = { minimize: true, close: true };
  assert.equal(shouldHideToTray('close', prefs, { quitting: true }), false);
  assert.equal(shouldHideToTray('minimize', prefs, { swapping: true }), false);
  assert.equal(shouldHideToTray('close', prefs, {}), true);
  assert.equal(shouldHideToTray('minimize', { minimize: false, close: true }, {}), false);
  assert.equal(shouldHideToTray('close', { minimize: true, close: false }, {}), false);
});

test('托盘菜单跟着界面语言', () => {
  assert.equal(normalizeTrayLocale('en-US'), 'en');
  assert.equal(normalizeTrayLocale('ja_JP'), 'ja');
  assert.equal(normalizeTrayLocale('ko'), 'ko');
  assert.equal(normalizeTrayLocale(''), 'zh-CN');
  assert.equal(trayLabels('zh-CN').pet, '放到桌面');
  assert.equal(trayLabels('en').stage, 'Back to stage');
  assert.equal(trayLabels('ja').quit, '終了');
  assert.equal(trayLabels('ko').show, '창 보이기');
});
