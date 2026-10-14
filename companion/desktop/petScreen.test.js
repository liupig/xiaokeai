'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  placement,
  hopTarget,
  clampInto,
  findDisplay,
} = require('./petScreen');

const primary = {
  id: 1,
  bounds: { x: 0, y: 0, width: 1920, height: 1080 },
  workArea: { x: 0, y: 40, width: 1920, height: 1040 },
  scaleFactor: 1,
};

const side = {
  id: 2,
  bounds: { x: 1920, y: 0, width: 2560, height: 1440 },
  workArea: { x: 1920, y: 0, width: 2560, height: 1400 },
  scaleFactor: 1.25,
};

function savedOf(display) {
  return {
    id: display.id,
    x: display.bounds.x,
    y: display.bounds.y,
    width: display.bounds.width,
    height: display.bounds.height,
    scaleFactor: display.scaleFactor,
  };
}

test('没有记录时落在主屏工作区', () => {
  const plan = placement({ displays: [primary, side], primaryId: 1 });
  assert.equal(plan.display.id, 1);
  assert.deepEqual(plan.bounds, { x: 0, y: 40, width: 1920, height: 1040 });
  assert.equal(plan.commit, true);
  assert.equal(plan.holdingFallback, false);
});

test('记住的副屏还在，铺满它现在的工作区', () => {
  const plan = placement({
    displays: [primary, side],
    primaryId: 1,
    savedScreen: savedOf(side),
    savedWindow: { x: 1920, y: 0, width: 2560, height: 1400 },
  });
  assert.equal(plan.display.id, 2);
  assert.deepEqual(plan.bounds, { x: 1920, y: 0, width: 2560, height: 1400 });
  assert.equal(plan.commit, true);
});

test('分辨率变了仍认同一块屏，用新的工作区而不是旧像素', () => {
  const shrunk = {
    id: 1,
    bounds: { x: 0, y: 0, width: 1600, height: 900 },
    workArea: { x: 0, y: 40, width: 1600, height: 860 },
    scaleFactor: 1,
  };
  const plan = placement({
    displays: [shrunk],
    primaryId: 1,
    savedScreen: savedOf(primary),
    savedWindow: { x: 0, y: 40, width: 1920, height: 1040 },
  });
  assert.equal(plan.display.id, 1);
  assert.deepEqual(plan.bounds, { x: 0, y: 40, width: 1600, height: 860 });
});

test('屏幕被挪走但 id 还在，跟到新位置', () => {
  const moved = {
    id: 2,
    bounds: { x: -2560, y: 0, width: 2560, height: 1440 },
    workArea: { x: -2560, y: 0, width: 2560, height: 1400 },
    scaleFactor: 1,
  };
  const plan = placement({
    displays: [primary, moved],
    primaryId: 1,
    savedScreen: savedOf(side),
    savedWindow: { x: 1920, y: 0, width: 2560, height: 1400 },
  });
  assert.equal(plan.display.id, 2);
  assert.equal(plan.bounds.x, -2560);
  assert.notEqual(plan.bounds.x, 1920);
});

test('id 变了但还占着原来的位置，按位置认', () => {
  const renamed = { ...side, id: 9 };
  const found = findDisplay([primary, renamed], savedOf(side));
  assert.equal(found.id, 9);
});

test('副屏拔了就落到主屏，不用原来的负坐标或屏外坐标', () => {
  const plan = placement({
    displays: [primary],
    primaryId: 1,
    savedScreen: savedOf(side),
    savedWindow: { x: 1920, y: 0, width: 2560, height: 1400 },
  });
  assert.equal(plan.display.id, 1);
  assert.deepEqual(plan.bounds, { x: 0, y: 40, width: 1920, height: 1040 });
  assert.equal(plan.commit, false);
  assert.equal(plan.holdingFallback, true);
});

test('这次已经因拔屏挪走后，屏幕插回来也不要突然拽回去', () => {
  const plan = placement({
    displays: [primary, side],
    primaryId: 1,
    savedScreen: savedOf(side),
    savedWindow: { x: 1920, y: 0, width: 2560, height: 1400 },
    holdingFallback: true,
    windowBounds: { x: 0, y: 40, width: 1920, height: 1040 },
  });
  assert.equal(plan.display.id, 1);
  assert.equal(plan.commit, false);
  assert.equal(plan.holdingFallback, true);
});

test('没有屏幕指纹但窗口中心还在副屏上，就认副屏', () => {
  const plan = placement({
    displays: [primary, side],
    primaryId: 1,
    savedWindow: { x: 2000, y: 100, width: 800, height: 600 },
  });
  assert.equal(plan.display.id, 2);
  assert.equal(plan.bounds.x, 1920);
  assert.equal(plan.commit, true);
});

test('旧坐标已经不在任何屏上，改落主屏并记住主屏', () => {
  const plan = placement({
    displays: [primary],
    primaryId: 1,
    savedWindow: { x: -2400, y: 80, width: 400, height: 500 },
  });
  assert.equal(plan.display.id, 1);
  assert.equal(plan.bounds.x, 0);
  assert.equal(plan.commit, true);
  assert.equal(plan.holdingFallback, false);
});

test('只占屏幕一角时，跟着屏幕挪并夹进工作区', () => {
  const plan = placement({
    displays: [primary, side],
    primaryId: 1,
    savedScreen: savedOf(primary),
    savedWindow: { x: 100, y: 80, width: 400, height: 500 },
  });
  assert.equal(plan.display.id, 1);
  assert.ok(plan.bounds.x >= 0);
  assert.ok(plan.bounds.y >= 40);
  assert.ok(plan.bounds.x + plan.bounds.width <= 1920);
  assert.ok(plan.bounds.y + plan.bounds.height <= 1080);
  assert.ok(plan.bounds.width < 1920);
});

test('主屏自己没了就用还在的屏', () => {
  const plan = placement({
    displays: [side],
    primaryId: 1,
    savedScreen: savedOf(primary),
    savedWindow: { x: 0, y: 40, width: 1920, height: 1040 },
  });
  assert.equal(plan.display.id, 2);
  assert.equal(plan.holdingFallback, true);
  assert.equal(plan.bounds.x, 1920);
});

test('窗口被拖出工作区时夹回去', () => {
  const next = clampInto(
    { x: -30, y: 20, width: 400, height: 500 },
    primary.workArea,
  );
  assert.equal(next.x, 0);
  assert.ok(next.y >= 40);
  assert.ok(next.x + next.width <= 1920);
});

test('拖进另一块屏的内侧才切换，贴边和镜像不跳', () => {
  assert.equal(hopTarget([primary, side], 1, { x: 2200, y: 400 }), 2);
  assert.equal(hopTarget([primary, side], 1, { x: 1924, y: 400 }), null);
  assert.equal(hopTarget([primary, side], 1, { x: 400, y: 400 }), null);
  const mirror = { ...side, bounds: { ...primary.bounds }, workArea: { ...primary.workArea } };
  assert.equal(hopTarget([primary, mirror], 1, { x: 400, y: 400 }), null);
});
