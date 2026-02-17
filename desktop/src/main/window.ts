/**
 * Window — Frameless transparent BrowserWindow for the floating orb.
 * Supports fullscreen toggle via IPC, keyboard shortcut, and tray menu.
 */

import { BrowserWindow, screen, ipcMain, globalShortcut } from 'electron'
import * as path from 'path'

const PORT = 8420
let mainWindow: BrowserWindow | null = null

export function createWindow(): BrowserWindow {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize

  mainWindow = new BrowserWindow({
    width: 600,
    height: 600,
    x: Math.round(width / 2 - 300),
    y: Math.round(height / 2 - 300),
    frame: false,
    transparent: true,
    resizable: true,
    fullscreenable: true,
    alwaysOnTop: false,
    hasShadow: false,
    skipTaskbar: false,
    backgroundColor: '#00000000',
    titleBarStyle: 'hidden',
    trafficLightPosition: { x: -20, y: -20 }, // hide native buttons off-screen
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  mainWindow.loadURL(`http://localhost:${PORT}/ui/`)

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // Adjust opacity/vibrancy when entering/leaving fullscreen
  mainWindow.on('enter-full-screen', () => {
    mainWindow?.setBackgroundColor('#000000')
    mainWindow?.webContents.send('fullscreen-change', true)
  })

  mainWindow.on('leave-full-screen', () => {
    mainWindow?.setBackgroundColor('#00000000')
    mainWindow?.webContents.send('fullscreen-change', false)
  })

  // Register global shortcut for fullscreen toggle
  globalShortcut.register('CmdOrCtrl+Shift+F', () => {
    toggleFullscreen()
  })

  // IPC handler for renderer-triggered fullscreen toggle
  ipcMain.on('toggle-fullscreen', () => {
    toggleFullscreen()
  })

  return mainWindow
}

export function toggleFullscreen(): void {
  if (!mainWindow) return
  const isFull = mainWindow.isFullScreen()
  mainWindow.setFullScreen(!isFull)
}

export function maximizeWindow(): void {
  if (!mainWindow) return
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize()
  } else {
    mainWindow.maximize()
  }
}

export function getWindow(): BrowserWindow | null {
  return mainWindow
}

export function toggleWindow(): void {
  if (!mainWindow) {
    createWindow()
    return
  }

  if (mainWindow.isVisible()) {
    mainWindow.hide()
  } else {
    mainWindow.show()
    mainWindow.focus()
  }
}

export function isFullscreen(): boolean {
  return mainWindow?.isFullScreen() ?? false
}
