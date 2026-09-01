const { contextBridge, ipcRenderer } = require('electron')
contextBridge.exposeInMainWorld('electronAPI', {
  getFlaskPort: () => ipcRenderer.invoke('get-flask-port'),
  getApiBaseUrl: () => ipcRenderer.invoke('get-api-base-url'),
  getLocalIP: () => ipcRenderer.invoke('get-local-ip'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  verifyMastercode: (code) => ipcRenderer.invoke('verify-mastercode', code),
  restoreDesktop: () => ipcRenderer.invoke('restore-desktop'),
  getMastercodeHint: () => ipcRenderer.invoke('get-mastercode-hint'),
})
