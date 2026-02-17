/**
 * Preload — Exposes a safe IPC bridge to the renderer for fullscreen control.
 */

import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('nexAPI', {
  toggleFullscreen: () => ipcRenderer.send('toggle-fullscreen'),
  onFullscreenChange: (callback: (isFullscreen: boolean) => void) => {
    ipcRenderer.on('fullscreen-change', (_event, isFullscreen: boolean) => {
      callback(isFullscreen)
    })
  },
})
