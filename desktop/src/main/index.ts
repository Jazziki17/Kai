/**
 * Kai Desktop — Electron Main Process
 * Starts the Python API server, opens a native frameless window.
 */

import { app } from 'electron'
import { createWindow, getWindow } from './window'
import { createTray } from './tray'
import { PythonBridge } from './python-bridge'

let pythonBridge: PythonBridge | null = null

app.whenReady().then(async () => {
  pythonBridge = new PythonBridge()
  await pythonBridge.start()

  createWindow()
  createTray(pythonBridge)
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  const win = getWindow()
  if (win) {
    win.show()
  } else {
    createWindow()
  }
})

app.on('before-quit', async () => {
  if (pythonBridge) {
    await pythonBridge.stop()
  }
})
