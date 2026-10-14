'use strict';

/**
 * 桌宠该落在哪块屏上。
 * 记住屏幕指纹（id + 当时的矩形）和窗口矩形。
 * 重启时先确认那块屏还在：还在就用它现在的工作区（窗口若只占屏幕一角，按相对位置夹回工作区）；
 * 不在就改落到主屏的工作区，不用上次的坐标，避免窗停在已经拔掉的屏幕上。
 * 这次运行里已经因拔屏挪走过的，插回显示器时不突然拽回去；下次启动那块屏还在才会回去。
 */

const MIN_EDGE = 80;

function rectOf(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const x = Number(raw.x);
  const y = Number(raw.y);
  const width = Number(raw.width);
  const height = Number(raw.height);
  if (![x, y, width, height].every(Number.isFinite)) return null;
  if (width < 1 || height < 1 || width > 20000 || height > 20000) return null;
  return { x, y, width, height };
}

function roundRect(r) {
  return {
    x: Math.round(r.x),
    y: Math.round(r.y),
    width: Math.max(1, Math.round(r.width)),
    height: Math.max(1, Math.round(r.height)),
  };
}

function overlapArea(a, b) {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);
  const w = x2 - x1;
  const h = y2 - y1;
  return w > 0 && h > 0 ? w * h : 0;
}

function pointIn(p, r) {
  return p.x >= r.x && p.x < r.x + r.width && p.y >= r.y && p.y < r.y + r.height;
}

function nearBounds(a, b) {
  if (!a || !b) return false;
  return Math.abs(a.x - b.x) <= 1
    && Math.abs(a.y - b.y) <= 1
    && Math.abs(a.width - b.width) <= 1
    && Math.abs(a.height - b.height) <= 1;
}

function workBounds(display) {
  if (!display) return null;
  const area = rectOf(display.workArea);
  if (area && area.width >= MIN_EDGE && area.height >= MIN_EDGE) return roundRect(area);
  const bounds = rectOf(display.bounds);
  if (bounds && bounds.width >= MIN_EDGE && bounds.height >= MIN_EDGE) return roundRect(bounds);
  return null;
}

function fingerprint(display) {
  const box = rectOf(display && display.bounds);
  if (!display || !box || !Number.isFinite(Number(display.id))) return null;
  return {
    id: display.id,
    x: box.x,
    y: box.y,
    width: box.width,
    height: box.height,
    scaleFactor: Number(display.scaleFactor) || 1,
  };
}

function normalizeSavedScreen(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const id = Number(raw.id);
  const box = rectOf(raw);
  if (!Number.isFinite(id) || !box) return null;
  return {
    id,
    x: box.x,
    y: box.y,
    width: box.width,
    height: box.height,
    scaleFactor: Number(raw.scaleFactor) || 1,
  };
}

function findById(displays, id) {
  return displays.find((d) => d.id === id) || null;
}

/** 位置还对得上就认位置（id 可能被系统改过）；对不上再认 id（屏幕被挪到了别处）。都没有就是拔掉了。 */
function findDisplay(displays, saved) {
  const screenBox = normalizeSavedScreen(saved);
  if (!screenBox || !displays || !displays.length) return null;
  const area = screenBox.width * screenBox.height;
  let best = null;
  let bestScore = 0;
  for (const d of displays) {
    const b = rectOf(d.bounds);
    if (!b) continue;
    const score = overlapArea(screenBox, b) / area;
    if (score > bestScore) {
      bestScore = score;
      best = d;
    }
  }
  if (best && bestScore >= 0.5 && workBounds(best)) return best;
  const byId = findById(displays, screenBox.id);
  if (byId && workBounds(byId)) return byId;
  return null;
}

function centerOf(rect) {
  const r = rectOf(rect);
  if (!r) return null;
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}

function displayContaining(displays, rect) {
  const c = centerOf(rect);
  if (!c || !displays) return null;
  for (const d of displays) {
    const b = rectOf(d.bounds);
    if (b && pointIn(c, b) && workBounds(d)) return d;
  }
  return null;
}

function fallbackDisplay(displays, primaryId) {
  const primary = findById(displays, primaryId);
  if (primary && workBounds(primary)) return primary;
  return displays.find((d) => workBounds(d)) || null;
}

function coversDisplay(windowRect, displayRect) {
  const w = rectOf(windowRect);
  const d = rectOf(displayRect);
  if (!w || !d) return true;
  const displayArea = d.width * d.height;
  const windowArea = w.width * w.height;
  if (displayArea <= 0 || windowArea <= 0) return true;
  const hit = overlapArea(w, d);
  return hit / Math.min(windowArea, displayArea) >= 0.9 && windowArea / displayArea >= 0.7;
}

function clampInto(rect, area) {
  const r = rectOf(rect);
  const a = rectOf(area);
  if (!r || !a) return null;
  const width = Math.max(1, Math.min(r.width, a.width));
  const height = Math.max(1, Math.min(r.height, a.height));
  let x = r.x;
  let y = r.y;
  if (x < a.x) x = a.x;
  if (y < a.y) y = a.y;
  if (x + width > a.x + a.width) x = a.x + a.width - width;
  if (y + height > a.y + a.height) y = a.y + a.height - height;
  return roundRect({ x, y, width, height });
}

function mapOnto(savedWindow, oldBounds, newBounds, workArea) {
  const w = rectOf(savedWindow);
  const oldBox = rectOf(oldBounds);
  const nextBox = rectOf(newBounds);
  const area = rectOf(workArea);
  if (!w || !oldBox || !nextBox || !area || oldBox.width < 1 || oldBox.height < 1) {
    return area ? roundRect(area) : null;
  }
  const mapped = {
    x: nextBox.x + ((w.x - oldBox.x) / oldBox.width) * nextBox.width,
    y: nextBox.y + ((w.y - oldBox.y) / oldBox.height) * nextBox.height,
    width: Math.max(300, (w.width / oldBox.width) * nextBox.width),
    height: Math.max(420, (w.height / oldBox.height) * nextBox.height),
  };
  return clampInto(mapped, area);
}

function restoredBounds(display, savedScreen, savedWindow) {
  const area = workBounds(display);
  if (!area) return null;
  const oldBox = normalizeSavedScreen(savedScreen);
  const win = rectOf(savedWindow);
  if (!oldBox || !win || coversDisplay(win, oldBox)) return area;
  return mapOnto(win, oldBox, display.bounds, area);
}

/**
 * @returns {{ display: object, bounds: {x,y,width,height}, commit: boolean, holdingFallback: boolean } | null}
 * commit：把这块屏写成记住的选择。临时落点不 commit，拔掉的屏下次还在仍会回去。
 */
function placement(opts) {
  const displays = Array.isArray(opts && opts.displays) ? opts.displays : [];
  if (!displays.length) return null;
  const savedScreen = normalizeSavedScreen(opts.savedScreen);
  const savedWindow = rectOf(opts.savedWindow);

  if (opts.fill && savedScreen) {
    const chosen = findDisplay(displays, savedScreen);
    if (chosen) {
      const bounds = workBounds(chosen);
      if (!bounds) return null;
      return { display: chosen, bounds, commit: true, holdingFallback: false };
    }
  }

  if (opts.holdingFallback) {
    const parked = displayContaining(displays, opts.windowBounds) || fallbackDisplay(displays, opts.primaryId);
    if (!parked) return null;
    const bounds = workBounds(parked);
    if (!bounds) return null;
    return { display: parked, bounds, commit: false, holdingFallback: true };
  }

  if (!savedScreen) {
    const adopted = displayContaining(displays, savedWindow) || fallbackDisplay(displays, opts.primaryId);
    if (!adopted) return null;
    const bounds = workBounds(adopted);
    if (!bounds) return null;
    return { display: adopted, bounds, commit: true, holdingFallback: false };
  }

  const matched = findDisplay(displays, savedScreen);
  if (matched) {
    const bounds = restoredBounds(matched, savedScreen, savedWindow);
    if (!bounds) return null;
    return { display: matched, bounds, commit: true, holdingFallback: false };
  }

  const fb = fallbackDisplay(displays, opts.primaryId);
  if (!fb) return null;
  const bounds = workBounds(fb);
  if (!bounds) return null;
  return { display: fb, bounds, commit: false, holdingFallback: true };
}

function separated(a, b) {
  if (!a || !b || a.id === b.id) return false;
  const ab = rectOf(a.bounds);
  const bb = rectOf(b.bounds);
  if (!ab || !bb) return false;
  const hit = overlapArea(ab, bb);
  const area = Math.min(ab.width * ab.height, bb.width * bb.height);
  return area > 0 && hit / area < 0.2;
}

function displayUnderPoint(displays, p, inset) {
  if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) return null;
  const pad = Number.isFinite(inset) ? inset : 0;
  for (const d of displays) {
    const b = rectOf(d.bounds);
    if (!b) continue;
    if (p.x >= b.x + pad && p.x < b.x + b.width - pad && p.y >= b.y + pad && p.y < b.y + b.height - pad) {
      return d;
    }
  }
  return null;
}

/** 拖到另一块屏的内侧才跳。镜像/复制屏重叠很大，不跳。 */
function hopTarget(displays, currentId, point) {
  const current = findById(displays || [], currentId);
  const under = displayUnderPoint(displays || [], point, 12);
  if (!current || !under || !separated(current, under)) return null;
  return under.id;
}

module.exports = {
  rectOf,
  nearBounds,
  workBounds,
  fingerprint,
  normalizeSavedScreen,
  findDisplay,
  displayContaining,
  clampInto,
  coversDisplay,
  placement,
  hopTarget,
};
