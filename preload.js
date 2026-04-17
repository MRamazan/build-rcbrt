const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {

  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close:    () => ipcRenderer.send('window-close'),
  isMaximized: () => ipcRenderer.invoke('window-is-maximized'),

  onMaximizeChange: (callback) => {
    ipcRenderer.on('maximize-changed', (event, isMaximized) => callback(isMaximized));
  },

  openExternal: (url) => ipcRenderer.send('open-external', url),

  platform: process.platform
});
