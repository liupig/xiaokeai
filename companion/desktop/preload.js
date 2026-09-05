'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('companionDesktop', {
  isShell: true,
  pickFolder: () => ipcRenderer.invoke('pick-folder'),
});
