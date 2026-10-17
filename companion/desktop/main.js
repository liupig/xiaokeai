'use strict';

/**
 * 自带 Chromium 的桌面壳：不依赖本机安装 Chrome。
 * 舞台模式：隐藏系统标题栏，用深色顶栏 + Windows 原生最小化/最大化/关闭。
 * 桌宠模式：透明无边框小窗，只留人物，空白处点击穿透到桌面。
 * 页面仍是现有 Vue 前端（打包 5211 / 开发 5175）。
 */
const { app, BrowserWindow, dialog, ipcMain, screen, session, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const petScreen = require('./petScreen');

function isLocalHost(hostname) {
  return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '::1';
}

function homeUrl() {
  const arg = process.argv.find((a) => a.startsWith('--url='));
  if (arg) return arg.slice('--url='.length);
  if (process.env.COMPANION_HOME) return process.env.COMPANION_HOME;
  if (process.argv.includes('--dev')) return 'http://127.0.0.1:5175/';
  return 'http://127.0.0.1:5211/';
}

function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return '';
  }
}

const HOME = homeUrl();
const HOME_ORIGIN = originOf(HOME);
const ICON = path.join(__dirname, 'icon.png');
const PRELOAD = path.join(__dirname, 'preload.js');

app.setName('xiaoke.ai');
app.setPath('userData', path.join(app.getPath('appData'), 'xiaoke-ai'));
if (process.platform === 'win32') {
  app.setAppUserModelId('ai.xiaoke.app');
}

app.commandLine.appendSwitch('ignore-gpu-blocklist');
app.commandLine.appendSwitch('enable-gpu-rasterization');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
// 桌面壳没有网页那种麦克风弹窗，不自动选默认设备的话 getUserMedia 会一直挂着。
app.commandLine.appendSwitch('use-fake-ui-for-media-stream');

const shellState = { mode: 'stage', stage: null, pet: null, petScreen: null, petSpot: null };
const roleOf = new WeakMap();
let swapping = false;
let saveTimer = null;
let holdingFallback = false;
let placingPet = false;
let layingOut = false;
let activePetDisplayId = 0;
let petHopAt = 0;
let displayTimer = null;

function statePath() {
  return path.join(app.getPath('userData'), 'shell-mode.json');
}

function loadState() {
  try {
    const raw = JSON.parse(fs.readFileSync(statePath(), 'utf8'));
    if (raw.mode === 'pet' || raw.mode === 'stage') shellState.mode = raw.mode;
    if (raw.stage) shellState.stage = raw.stage;
    if (raw.pet) shellState.pet = raw.pet;
    const savedScreen = petScreen.normalizeSavedScreen(raw.petScreen);
    if (savedScreen) shellState.petScreen = savedScreen;
    const spot = normalizeSpot(raw.petSpot);
    if (spot) shellState.petSpot = spot;
  } catch { /* 第一次打开 */ }
}

function saveState() {
  try {
    fs.mkdirSync(path.dirname(statePath()), { recursive: true });
    fs.writeFileSync(statePath(), JSON.stringify(shellState));
  } catch { /* 位置记不住也不影响使用 */ }
}

function saveSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveState, 400);
}

function boundsOf(win) {
  const b = win.getBounds();
  return { x: b.x, y: b.y, width: b.width, height: b.height };
}

function normalizeSpot(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const x = Number(raw.x);
  const y = Number(raw.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    x: Math.max(-1, Math.min(1, x)),
    y: Math.max(-1, Math.min(1, y)),
  };
}

function sameFingerprint(a, b) {
  if (!a || !b) return false;
  return a.id === b.id && a.x === b.x && a.y === b.y
    && a.width === b.width && a.height === b.height
    && Number(a.scaleFactor) === Number(b.scaleFactor);
}

function remember(win, immediate) {
  const key = roleOf.get(win);
  if (!key || !win || win.isDestroyed()) return;
  // 临时落在替补屏时，别把替补屏的矩形写成她原本的位置。
  if (!(key === 'pet' && holdingFallback)) shellState[key] = boundsOf(win);
  if (immediate) {
    clearTimeout(saveTimer);
    saveState();
  } else {
    saveSoon();
  }
}

function usable(b) {
  if (!b || !Number.isFinite(b.width) || !Number.isFinite(b.height)) return false;
  if (b.width < 280 || b.height < 360) return false;
  const cx = b.x + b.width / 2;
  const cy = b.y + b.height / 2;
  return screen.getAllDisplays().some((d) => {
    const a = d.workArea;
    return cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height;
  });
}

function shellPage(mode) {
  const u = new URL(HOME);
  if (mode === 'pet') u.searchParams.set('shell', 'pet');
  else u.searchParams.delete('shell');
  return u.toString();
}

const MEDIA_PERMS = new Set([
  'media',
  'microphone',
  'camera',
  'audioCapture',
  'videoCapture',
  'mediaKeySystem',
  'display-capture',
  'clipboard-sanitized-write',
  'clipboard-read',
]);

function allowMedia(permission, requestingUrl) {
  if (!MEDIA_PERMS.has(permission) && permission !== 'notifications') return false;
  if (!requestingUrl) return true;
  try {
    const u = new URL(requestingUrl);
    return isLocalHost(u.hostname);
  } catch {
    return HOME_ORIGIN && requestingUrl.startsWith(HOME_ORIGIN);
  }
}

function grantPermissions() {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback, details) => {
    const url = (details && details.requestingUrl) || HOME;
    callback(allowMedia(permission, url));
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission, requestingOrigin) => {
    if (permission === 'media' || MEDIA_PERMS.has(permission)) {
      return allowMedia(permission === 'media' ? 'media' : permission, requestingOrigin || HOME);
    }
    return false;
  });
}

function reveal(win) {
  if (!win || win.isDestroyed() || win.isVisible()) return;
  // 桌宠不要在弹出时抢走键盘，否则点她那一下不算用户操作，语音上下文会一直停着。
  if (roleOf.get(win) === 'pet') win.showInactive();
  else win.show();
}

function focusWindow(win) {
  if (!win || win.isDestroyed()) return;
  if (win.isMinimized()) win.restore();
  reveal(win);
  win.focus();
}

function webPrefs() {
  return {
    preload: PRELOAD,
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
    webSecurity: true,
    backgroundThrottling: false,
  };
}

function attachPage(win, mode) {
  roleOf.set(win, mode);
  win.setMenuBarVisibility(false);
  win.once('ready-to-show', () => reveal(win));
  win.webContents.once('did-finish-load', () => reveal(win));
  setTimeout(() => reveal(win), 4000);
  const save = () => remember(win, false);
  win.on('move', save);
  win.on('resize', save);
  win.on('close', () => remember(win, true));

  let tries = 0;
  const page = shellPage(mode);
  const load = () => {
    if (win.isDestroyed()) return;
    win.loadURL(page);
  };
  win.webContents.on('did-fail-load', (_e, code, _desc, _url, isMain) => {
    if (!isMain || win.isDestroyed()) return;
    if (code === -3) return; // ERR_ABORTED
    tries += 1;
    if (tries <= 10) setTimeout(load, 400);
    else reveal(win);
  });
  load();

  win.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const u = new URL(url);
      if (u.protocol === 'https:' || u.protocol === 'http:') {
        if (!isLocalHost(u.hostname)) shell.openExternal(url).catch(() => {});
      }
    } catch { /* 忽略坏链 */ }
    return { action: 'deny' };
  });
}

function createStageWindow() {
  const b = usable(shellState.stage) ? shellState.stage : null;
  const opts = {
    width: b ? b.width : 1440,
    height: b ? b.height : 900,
    minWidth: 960,
    minHeight: 600,
    title: 'xiaoke.ai',
    icon: fs.existsSync(ICON) ? ICON : undefined,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#141420',
    roundedCorners: true,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#141420',
      symbolColor: '#d0d0e4',
      height: 36,
    },
    webPreferences: webPrefs(),
  };
  if (b) {
    opts.x = b.x;
    opts.y = b.y;
  }
  const win = new BrowserWindow(opts);
  attachPage(win, 'stage');
  return win;
}

function plainDisplay(display) {
  return {
    id: display.id,
    bounds: {
      x: display.bounds.x,
      y: display.bounds.y,
      width: display.bounds.width,
      height: display.bounds.height,
    },
    workArea: {
      x: display.workArea.x,
      y: display.workArea.y,
      width: display.workArea.width,
      height: display.workArea.height,
    },
    scaleFactor: display.scaleFactor || 1,
    internal: !!display.internal,
    label: typeof display.label === 'string' ? display.label : '',
  };
}

function allPlainDisplays() {
  return screen.getAllDisplays().map(plainDisplay);
}

function planFor(win, fill) {
  const displays = allPlainDisplays();
  const primary = screen.getPrimaryDisplay();
  return petScreen.placement({
    displays,
    primaryId: primary ? primary.id : (displays[0] && displays[0].id),
    savedScreen: shellState.petScreen,
    savedWindow: shellState.pet,
    holdingFallback,
    windowBounds: win && !win.isDestroyed() ? boundsOf(win) : null,
    fill: !!fill,
  });
}

function notifyDisplays() {
  const wins = BrowserWindow.getAllWindows();
  for (let i = 0; i < wins.length; i += 1) {
    const w = wins[i];
    if (w.isDestroyed() || roleOf.get(w) !== 'pet' || w.webContents.isDestroyed()) continue;
    w.webContents.send('displays-changed');
  }
}

function applyPlacement(win, plan) {
  if (!plan || !win || win.isDestroyed()) return;
  holdingFallback = plan.holdingFallback;
  activePetDisplayId = plan.display.id;
  let screenChanged = false;
  if (plan.commit) {
    const next = petScreen.fingerprint(plan.display);
    screenChanged = !sameFingerprint(shellState.petScreen, next);
    if (next) shellState.petScreen = next;
  }
  if (!petScreen.nearBounds(win.getBounds(), plan.bounds)) {
    placingPet = true;
    try { win.setBounds(plan.bounds); }
    finally { placingPet = false; }
  } else if (screenChanged) {
    saveSoon();
  }
}

function layoutPetWindow(win, fill) {
  if (!win || win.isDestroyed() || roleOf.get(win) !== 'pet' || layingOut) return;
  layingOut = true;
  try {
    const plan = planFor(win, fill);
    if (!plan) return;
    applyPlacement(win, plan);
    notifyDisplays();
  } finally {
    layingOut = false;
  }
}

function placeOnDisplay(win, display) {
  if (!win || win.isDestroyed() || !display) return;
  holdingFallback = false;
  const fp = petScreen.fingerprint(plainDisplay(display));
  if (fp) shellState.petScreen = fp;
  layoutPetWindow(win, true);
  saveState();
}

function schedulePetLayout() {
  clearTimeout(displayTimer);
  displayTimer = setTimeout(() => {
    const win = petWindow();
    if (win) layoutPetWindow(win);
  }, 160);
}

function describeDisplays() {
  const displays = allPlainDisplays();
  const primary = screen.getPrimaryDisplay();
  const win = petWindow();
  const current = win ? petScreen.displayContaining(displays, boundsOf(win)) : null;
  const sorted = displays.slice().sort((a, b) => {
    const aPrimary = primary && a.id === primary.id;
    const bPrimary = primary && b.id === primary.id;
    if (aPrimary !== bPrimary) return aPrimary ? -1 : 1;
    if (a.bounds.x !== b.bounds.x) return a.bounds.x - b.bounds.x;
    return a.bounds.y - b.bounds.y;
  });
  return sorted.map((d, i) => ({
    id: d.id,
    index: i + 1,
    width: Math.round(d.bounds.width),
    height: Math.round(d.bounds.height),
    scaleFactor: d.scaleFactor || 1,
    primary: !!(primary && d.id === primary.id),
    current: !!(current && d.id === current.id),
    internal: !!d.internal,
    label: d.label || '',
  }));
}

function pullPetWindowInside(win) {
  if (!win || win.isDestroyed() || placingPet || layingOut) return;
  if (holdingFallback) {
    layoutPetWindow(win);
    return;
  }
  const displays = allPlainDisplays();
  const b = boundsOf(win);
  const hit = petScreen.displayContaining(displays, b);
  if (!hit) {
    layoutPetWindow(win);
    return;
  }
  const area = petScreen.workBounds(hit);
  if (!area) return;
  const next = petScreen.clampInto(b, area);
  const movedScreen = !shellState.petScreen || shellState.petScreen.id !== hit.id;
  if (movedScreen) {
    holdingFallback = false;
    const fp = petScreen.fingerprint(hit);
    if (fp) shellState.petScreen = fp;
  }
  if (next && !petScreen.nearBounds(b, next)) {
    placingPet = true;
    try { win.setBounds(next); }
    finally { placingPet = false; }
  } else if (movedScreen) {
    saveSoon();
  }
}

function maybeHopPetDisplay(win) {
  if (!petRegion || !petRegion.pressed || !win || win.isDestroyed()) return;
  if (Date.now() - petHopAt < 500) return;
  const nextId = petScreen.hopTarget(allPlainDisplays(), activePetDisplayId, screen.getCursorScreenPoint());
  if (!nextId || nextId === activePetDisplayId) return;
  const display = screen.getAllDisplays().find((d) => d.id === nextId);
  if (!display) return;
  petHopAt = Date.now();
  win.setIgnoreMouseEvents(false);
  placeOnDisplay(win, display);
}

function createPetWindow() {
  const plan = planFor(null);
  const area = plan ? plan.bounds : { x: 0, y: 0, width: 1280, height: 720 };
  const win = new BrowserWindow({
    x: area.x,
    y: area.y,
    width: area.width,
    height: area.height,
    title: 'xiaoke.ai',
    icon: fs.existsSync(ICON) ? ICON : undefined,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    roundedCorners: false,
    thickFrame: false,
    alwaysOnTop: true,
    resizable: false,
    movable: false,
    autoHideMenuBar: true,
    webPreferences: webPrefs(),
  });
  win.setAlwaysOnTop(true, 'floating');
  win.setIgnoreMouseEvents(true, { forward: true });
  attachPage(win, 'pet');
  layoutPetWindow(win);
  return win;
}

function openWindow() {
  return shellState.mode === 'pet' ? createPetWindow() : createStageWindow();
}

function focusExisting() {
  const win = BrowserWindow.getAllWindows()[0];
  if (win) focusWindow(win);
  else openWindow();
}

ipcMain.handle('pick-folder', async () => {
  const win = BrowserWindow.getAllWindows()[0];
  const r = await dialog.showOpenDialog(win ?? undefined, {
    title: '选择资源包（B）目录',
    properties: ['openDirectory'],
  });
  if (r.canceled || !r.filePaths.length) return '';
  return r.filePaths[0];
});

ipcMain.handle('get-shell-mode', () => shellState.mode);

ipcMain.handle('set-shell-mode', (e, mode) => {
  const next = mode === 'pet' ? 'pet' : 'stage';
  const old = BrowserWindow.fromWebContents(e.sender);
  if (old && !old.isDestroyed()) remember(old, true);
  if (shellState.mode === next && old && !old.isDestroyed()) return next;
  shellState.mode = next;
  saveState();
  swapping = true;
  const created = openWindow();
  if (old && !old.isDestroyed() && old !== created) old.close();
  swapping = false;
  return next;
});

ipcMain.on('set-ignore-mouse', (e, ignore) => {
  if (shellState.mode !== 'pet') return;
  const win = BrowserWindow.fromWebContents(e.sender);
  if (!win || win.isDestroyed()) return;
  if (ignore) win.setIgnoreMouseEvents(true, { forward: true });
  else win.setIgnoreMouseEvents(false);
});

let petRegion = null;
let petHot = false;

function finite(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function distToSeg(px, py, ax, ay, bx, by) {
  const abx = bx - ax;
  const aby = by - ay;
  const len2 = abx * abx + aby * aby || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / len2));
  return Math.hypot(px - (ax + abx * t), py - (ay + aby * t));
}

function regionHits(region, x, y, pad) {
  if (!region) return false;
  if (region.r > 0 && distToSeg(x, y, region.ax, region.ay, region.bx, region.by) <= region.r + pad) {
    return true;
  }
  const rects = region.rects || [];
  for (let i = 0; i < rects.length; i += 1) {
    const rc = rects[i];
    if (x >= rc.x - pad && x <= rc.x + rc.w + pad && y >= rc.y - pad && y <= rc.y + rc.h + pad) {
      return true;
    }
  }
  return false;
}

function petWindow() {
  if (shellState.mode !== 'pet') return null;
  const wins = BrowserWindow.getAllWindows();
  for (let i = 0; i < wins.length; i += 1) {
    const win = wins[i];
    if (!win.isDestroyed() && roleOf.get(win) === 'pet') return win;
  }
  return null;
}

function applyPetPointer(win) {
  if (!win || win.isDestroyed()) return;
  const cursor = screen.getCursorScreenPoint();
  const bounds = win.getBounds();
  const x = cursor.x - bounds.x;
  const y = cursor.y - bounds.y;
  const pressed = !!(petRegion && petRegion.pressed);
  const inside = pressed || regionHits(petRegion, x, y, 10);
  const next = inside || (!!petHot && regionHits(petRegion, x, y, 12));
  if (next !== petHot) {
    petHot = next;
    if (next) win.setIgnoreMouseEvents(false);
    else win.setIgnoreMouseEvents(true, { forward: true });
  }
  if (pressed && !win.isFocused()) win.focus();
}

ipcMain.on('pet-hit-region', (e, raw) => {
  if (shellState.mode !== 'pet') return;
  const src = raw && typeof raw === 'object' ? raw : {};
  const rects = Array.isArray(src.rects) ? src.rects.slice(0, 6).map((rc) => ({
    x: finite(rc && rc.x, 0),
    y: finite(rc && rc.y, 0),
    w: Math.max(0, finite(rc && rc.w, 0)),
    h: Math.max(0, finite(rc && rc.h, 0)),
  })) : [];
  petRegion = {
    ax: finite(src.ax, 0),
    ay: finite(src.ay, 0),
    bx: finite(src.bx, 0),
    by: finite(src.by, 0),
    r: Math.max(0, Math.min(220, finite(src.r, 0))),
    rects,
    pressed: !!src.pressed,
    focus: !!src.focus,
  };
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win && !win.isDestroyed()) applyPetPointer(win);
});

function petDelta(delta) {
  return {
    dx: Math.max(-400, Math.min(400, Number(delta && delta.dx) || 0)),
    dy: Math.max(-400, Math.min(400, Number(delta && delta.dy) || 0)),
  };
}

ipcMain.on('pet-drag', (e, delta) => {
  if (shellState.mode !== 'pet') return;
  const win = BrowserWindow.fromWebContents(e.sender);
  if (!win || win.isDestroyed()) return;
  const { dx, dy } = petDelta(delta);
  const [x, y] = win.getPosition();
  win.setPosition(Math.round(x + dx), Math.round(y + dy));
  pullPetWindowInside(win);
});

ipcMain.on('pet-resize', (e, delta) => {
  if (shellState.mode !== 'pet') return;
  const win = BrowserWindow.fromWebContents(e.sender);
  if (!win || win.isDestroyed()) return;
  const { dx, dy } = petDelta(delta);
  const b = win.getBounds();
  win.setBounds({
    x: b.x,
    y: b.y,
    width: Math.max(300, Math.round(b.width + dx)),
    height: Math.max(420, Math.round(b.height + dy)),
  });
  pullPetWindowInside(win);
});

ipcMain.handle('list-displays', () => describeDisplays());

ipcMain.handle('set-pet-display', (e, id) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (shellState.mode === 'pet' && win && !win.isDestroyed() && roleOf.get(win) === 'pet') {
    const display = screen.getAllDisplays().find((d) => d.id === Number(id));
    if (display) placeOnDisplay(win, display);
  }
  return describeDisplays();
});

ipcMain.handle('get-pet-spot', () => shellState.petSpot);

ipcMain.on('set-pet-spot', (_e, raw) => {
  if (raw == null) {
    shellState.petSpot = null;
    saveSoon();
    return;
  }
  const spot = normalizeSpot(raw);
  if (!spot) return;
  const prev = shellState.petSpot;
  if (prev && Math.abs(prev.x - spot.x) < 0.001 && Math.abs(prev.y - spot.y) < 0.001) return;
  shellState.petSpot = spot;
  saveSoon();
});

ipcMain.on('window-minimize', (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win && !win.isDestroyed()) win.minimize();
});

ipcMain.on('window-close', (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win && !win.isDestroyed()) win.close();
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    focusExisting();
  });
  app.whenReady().then(() => {
    loadState();
    grantPermissions();
    openWindow();
    setInterval(() => {
      const win = petWindow();
      if (!win) {
        petHot = false;
        return;
      }
      maybeHopPetDisplay(win);
      applyPetPointer(win);
    }, 16);
    screen.on('display-added', schedulePetLayout);
    screen.on('display-removed', schedulePetLayout);
    screen.on('display-metrics-changed', schedulePetLayout);
  });
  app.on('window-all-closed', () => {
    if (!swapping) app.quit();
  });
}
