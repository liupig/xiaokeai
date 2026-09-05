'use strict';

/**
 * 自带 Chromium 的桌面壳：不依赖本机安装 Chrome。
 * 隐藏系统标题栏，用深色顶栏 + Windows 原生最小化/最大化/关闭。
 * 页面仍是现有 Vue 前端（打包 5211 / 开发 5175）。
 */
const { app, BrowserWindow, dialog, ipcMain, session, shell } = require('electron');
const fs = require('fs');
const path = require('path');

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

const MEDIA_PERMS = new Set([
  'media',
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
  win.show();
}

function focusWindow(win) {
  if (!win || win.isDestroyed()) return;
  if (win.isMinimized()) win.restore();
  reveal(win);
  win.focus();
}

function createWindow() {
  const existing = BrowserWindow.getAllWindows()[0];
  if (existing && !existing.isDestroyed()) {
    focusWindow(existing);
    return existing;
  }
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
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
    webPreferences: {
      preload: PRELOAD,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      backgroundThrottling: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.once('ready-to-show', () => reveal(win));
  win.webContents.once('did-finish-load', () => reveal(win));
  setTimeout(() => reveal(win), 4000);

  let tries = 0;
  const load = () => {
    if (win.isDestroyed()) return;
    win.loadURL(HOME);
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
  return win;
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

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = BrowserWindow.getAllWindows()[0];
    if (win) focusWindow(win);
    else createWindow();
  });
  app.whenReady().then(() => {
    grantPermissions();
    createWindow();
  });
  app.on('window-all-closed', () => {
    app.quit();
  });
}
