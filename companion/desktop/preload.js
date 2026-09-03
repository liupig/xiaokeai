'use strict';

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('companionDesktop', { isShell: true });
