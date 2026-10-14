'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('companionDesktop', {
  isShell: true,
  pickFolder: () => ipcRenderer.invoke('pick-folder'),
  getShellMode: () => ipcRenderer.invoke('get-shell-mode'),
  setShellMode: (mode) => ipcRenderer.invoke('set-shell-mode', mode),
  setIgnoreMouse: (ignore) => ipcRenderer.send('set-ignore-mouse', !!ignore),
  setPetHitRegion: (region) => ipcRenderer.send('pet-hit-region', region),
  dragBy: (dx, dy) => ipcRenderer.send('pet-drag', { dx, dy }),
  resizeBy: (dx, dy) => ipcRenderer.send('pet-resize', { dx, dy }),
  listDisplays: () => ipcRenderer.invoke('list-displays'),
  setPetDisplay: (id) => ipcRenderer.invoke('set-pet-display', id),
  onDisplaysChanged: (cb) => {
    const fn = () => cb();
    ipcRenderer.on('displays-changed', fn);
    return () => ipcRenderer.removeListener('displays-changed', fn);
  },
  getPetSpot: () => ipcRenderer.invoke('get-pet-spot'),
  setPetSpot: (spot) => ipcRenderer.send('set-pet-spot', spot),
  minimize: () => ipcRenderer.send('window-minimize'),
  close: () => ipcRenderer.send('window-close'),
});
