/**
 * Tray — macOS menu bar icon with show/hide, dynamic start/stop server, launch at login, quit.
 * Rebuilds menu on server state changes.
 */

import { Tray, Menu, app, nativeImage } from 'electron'
import { toggleWindow, toggleFullscreen, isFullscreen } from './window'
import { PythonBridge } from './python-bridge'

let tray: Tray | null = null
let bridge: PythonBridge | null = null

function buildMenu(): Menu {
  const pb = bridge!
  const isLoginItem = app.getLoginItemSettings().openAtLogin
  const running = pb.isRunning

  return Menu.buildFromTemplate([
    {
      label: 'Show/Hide Nex',
      click: () => toggleWindow(),
    },
    {
      label: isFullscreen() ? 'Exit Fullscreen' : 'Enter Fullscreen',
      accelerator: 'CmdOrCtrl+Shift+F',
      click: () => {
        toggleFullscreen()
        rebuildMenu()
      },
    },
    {
      type: 'separator',
    },
    {
      label: 'Status',
      sublabel: running ? 'Running' : 'Stopped',
      enabled: false,
    },
    {
      type: 'separator',
    },
    {
      label: running ? 'Stop Server' : 'Start Server',
      click: async () => {
        if (running) {
          await pb.stop()
        } else {
          await pb.start()
        }
        rebuildMenu()
      },
    },
    {
      label: 'Restart Server',
      enabled: running,
      click: async () => {
        await pb.restart()
        rebuildMenu()
      },
    },
    {
      type: 'separator',
    },
    {
      label: 'Launch at Login',
      type: 'checkbox',
      checked: isLoginItem,
      click: (menuItem) => {
        app.setLoginItemSettings({
          openAtLogin: menuItem.checked,
          openAsHidden: true,
        })
      },
    },
    {
      type: 'separator',
    },
    {
      label: 'Quit',
      click: () => {
        app.quit()
      },
    },
  ])
}

function rebuildMenu(): void {
  if (tray) {
    tray.setContextMenu(buildMenu())
  }
}

export function createTray(pythonBridge: PythonBridge): void {
  bridge = pythonBridge

  // Create a simple tray icon (small circle)
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAAACXBIWXMAAAsTAAALEwEAmpwYAAABHUlEQVQ4y62TvUoDQRSFv5lNNouFYGEhWNj4AG7hA/gA2lj5AG5hZWHhA2hjYWFhYWFhIYKFhYVgIcQf4u5mZ+baJCuyuwnBAxeGO3PO3Lkz8M9SVEV7qmt7qrOqHxp4p/pT9UP1QnVTdTUkbKreJsnW49t76rcJX6ke6YhZDL4n+FRnU8GBVHBf1aN0RVkhSJeBCq4kUoE1xwvHs3I6GyVYc5R9T3AzEawCG44n1rKE1cAFICpBJCpOAD2AlSI44WiPdxbYd7yA5cAz4KFE+Iw5XpXTYSJojnLGEVwrJoJ+Br43BU+Ad8CeI/gdBT/QOU08F51PUkcjoIPVQ/TjLSqb/p8BU8Cv6vuqh6ntgepV0ny67+FX+xfeKI5WL4/AAAAABJRU5ErkJggg=='
  )

  // Make it template for macOS dark/light mode
  icon.setTemplateImage(true)
  tray = new Tray(icon)
  tray.setToolTip('Nex AI Assistant')

  tray.setContextMenu(buildMenu())

  // Click tray icon to toggle window
  tray.on('click', () => {
    toggleWindow()
  })
}

export { rebuildMenu }
