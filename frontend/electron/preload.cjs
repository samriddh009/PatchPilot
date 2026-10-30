const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopApi', {
  isDesktop: true,
  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  getApiBaseUrl: () => ipcRenderer.invoke('desktop:getApiBaseUrl'),
  openLocalRepository: (path, name) => ipcRenderer.invoke('desktop:openLocalRepository', path, name),
});

