'use strict';

/** 托盘菜单文案，和设置里的界面语言对齐。主进程读不到 Vue 的语言包。 */

const LABELS = {
  'zh-CN': {
    show: '显示窗口',
    pet: '放到桌面',
    stage: '回到舞台',
    quit: '退出',
  },
  en: {
    show: 'Show window',
    pet: 'Float on desktop',
    stage: 'Back to stage',
    quit: 'Quit',
  },
  ja: {
    show: 'ウィンドウを表示',
    pet: 'デスクトップへ',
    stage: 'ステージに戻る',
    quit: '終了',
  },
  ko: {
    show: '창 보이기',
    pet: '바탕화면에 두기',
    stage: '무대로',
    quit: '종료',
  },
};

function normalizeTrayLocale(lang) {
  const low = String(lang || '').trim().replace('_', '-').toLowerCase();
  if (low === 'en' || low.startsWith('en-')) return 'en';
  if (low.startsWith('ja')) return 'ja';
  if (low.startsWith('ko')) return 'ko';
  return 'zh-CN';
}

function trayLabels(lang) {
  return LABELS[normalizeTrayLocale(lang)];
}

function normalizeTrayPrefs(raw) {
  const src = raw && typeof raw === 'object' ? raw : {};
  return {
    minimize: src.minimize !== false,
    close: src.close !== false,
  };
}

function applyTrayPatch(current, patch) {
  const next = normalizeTrayPrefs(current);
  if (!patch || typeof patch !== 'object') return next;
  if (typeof patch.minimize === 'boolean') next.minimize = patch.minimize;
  if (typeof patch.close === 'boolean') next.close = patch.close;
  return next;
}

function shouldHideToTray(kind, prefs, flags) {
  const gate = flags || {};
  if (gate.quitting || gate.swapping) return false;
  const tray = normalizeTrayPrefs(prefs);
  if (kind === 'close') return tray.close;
  if (kind === 'minimize') return tray.minimize;
  return false;
}

module.exports = {
  normalizeTrayLocale,
  trayLabels,
  normalizeTrayPrefs,
  applyTrayPatch,
  shouldHideToTray,
};
