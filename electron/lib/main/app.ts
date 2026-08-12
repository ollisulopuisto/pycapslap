import { BrowserWindow, shell, app, protocol, net, ipcMain, dialog } from 'electron'
import { join } from 'path'
import * as fs from 'node:fs'
import { Readable } from 'node:stream'
import { registerWindowIPC } from '@/lib/window/ipcEvents'
import appIcon from '@/resources/build/icon.png?asset'
import { pathToFileURL } from 'url'
import { Sidecar } from './sidecar'

let core: Sidecar | null = null
let ipcRegistered = false
let protocolRegistered = false

export function createAppWindow(): void {
  // Register custom protocol for resources only once
  if (!protocolRegistered) {
    registerResourcesProtocol()
    protocolRegistered = true
  }

  // Initialize Rust sidecar
  if (!core) {
    core = new Sidecar()
  }

  // Create the main window.
  const mainWindow = new BrowserWindow({
    width: 1200,
    height: 900,
    minWidth: 1200,
    minHeight: 800,
    show: false,
    backgroundColor: '#0a0a0a',
    icon: appIcon,
    frame: false,
    titleBarStyle: 'hiddenInset',
    title: 'CapSlap',
    maximizable: true,
    resizable: true,
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Register IPC events only once (handlers resolve the live window from the
  // event sender, so they keep working even if macOS recreates the window).
  if (!ipcRegistered) {
    registerWindowIPC(mainWindow)
    registerRustIPC()
    ipcRegistered = true
  }

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (!app.isPackaged && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// Register custom protocol for assets
function registerResourcesProtocol() {
  if (!protocol.isProtocolHandled('res')) {
    protocol.handle('res', async (request) => {
      try {
        const url = new URL(request.url)
        const relativePath = url.href.replace('res://', '')

        let filePath: string | null = null

        if (relativePath.startsWith('local/')) {
          // Absolute local path: res://local/<absolute path>
          filePath = relativePath.slice('local/'.length)
          // Decode generic URL encoding if needed (spaces etc)
          filePath = decodeURIComponent(filePath)
          console.log('Loading local file:', filePath)
        } else {
          const possiblePaths = [
            join(__dirname, '../../resources', relativePath),
            join(__dirname, '../../../resources', relativePath),
            join(process.resourcesPath, relativePath),
            join(process.resourcesPath, 'app.asar.unpacked', 'resources', relativePath),
          ]

          for (const path of possiblePaths) {
            if (fs.existsSync(path)) {
              filePath = path
              break
            }
          }
        }

        if (!filePath || !fs.existsSync(filePath)) {
          console.error('File not found:', filePath)
          return new Response('Resource not found', { status: 404 })
        }

        // Check for video extensions to serve with correct content type
        // and real byte-range support so large files stream instead of being
        // loaded fully into memory on every request.
        const ext = relativePath.split('.').pop()?.toLowerCase()
        const videoExtensions = ['mp4', 'mov', 'mkv', 'avi', 'webm', 'wmv', 'flv', 'mpeg', 'mpg', 'm4v', '3gp', 'ts']

        if (ext && videoExtensions.includes(ext)) {
          const stat = fs.statSync(filePath)
          const size = stat.size

          let contentType = 'video/mp4' // Default fallback
          switch (ext) {
            case 'mov':
              contentType = 'video/quicktime'
              break
            case 'webm':
              contentType = 'video/webm'
              break
            case 'avi':
              contentType = 'video/x-msvideo'
              break
            case 'wmv':
              contentType = 'video/x-ms-wmv'
              break
            case 'flv':
              contentType = 'video/x-flv'
              break
            case 'mpeg':
            case 'mpg':
              contentType = 'video/mpeg'
              break
            case '3gp':
              contentType = 'video/3gpp'
              break
            case 'ts':
              contentType = 'video/mp2t'
              break
            // mp4, m4v stay as video/mp4
          }

          const baseHeaders: Record<string, string> = {
            'Content-Type': contentType,
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
          }

          // Honor byte ranges (used by <video> elements for seeking).
          const rangeHeader = request.headers.get('range')
          if (rangeHeader) {
            const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader)
            if (match && (match[1] || match[2])) {
              const start = match[1] ? parseInt(match[1], 10) : 0
              const end = match[2] ? Math.min(parseInt(match[2], 10), size - 1) : size - 1

              if (start <= end && start < size) {
                const stream = fs.createReadStream(filePath, { start, end })
                return new Response(Readable.toWeb(stream) as ReadableStream, {
                  status: 206,
                  headers: {
                    ...baseHeaders,
                    'Content-Length': String(end - start + 1),
                    'Content-Range': `bytes ${start}-${end}/${size}`,
                  },
                })
              }
            }
          }

          // No (or invalid) range header: stream the whole file without
          // buffering it in memory.
          const stream = fs.createReadStream(filePath)
          return new Response(Readable.toWeb(stream) as ReadableStream, {
            status: 200,
            headers: {
              ...baseHeaders,
              'Content-Length': String(size),
            },
          })
        }

        const response = await net.fetch(pathToFileURL(filePath).toString())
        return response
      } catch (error) {
        console.error('Protocol error:', error)
        return new Response('Resource not found', { status: 404 })
      }
    })
  }
}

function registerRustIPC() {
  ipcMain.handle('dialog:openFiles', async (evt, payload) => {
    console.log('[MAIN] File dialog requested:', payload)
    const win = BrowserWindow.fromWebContents(evt.sender)
    const props: any[] = ['openFile', 'multiSelections']
    const filters = payload?.filters ?? undefined
    const options = { properties: props, filters }
    const res = win && !win.isDestroyed()
      ? await dialog.showOpenDialog(win, options)
      : await dialog.showOpenDialog(options)
    if (res.canceled || res.filePaths.length === 0) {
      console.log('[MAIN] File dialog cancelled')
      return null
    }
    console.log('[MAIN] File selected:', res.filePaths)
    return res.filePaths
  })

  ipcMain.handle('core:call', async (evt, payload) => {
    console.log('[MAIN] Core call:', payload.method, payload.params, payload.requestId)
    if (!core) {
      console.error('[MAIN] Core sidecar not initialized')
      throw new Error('Core sidecar not initialized')
    }
    const win = BrowserWindow.fromWebContents(evt.sender)
    // Pass requestId if present
    return core.call(
      payload.method,
      payload.params,
      (p) => {
        console.log('[MAIN] Core progress:', p)
        // Only forward progress to a live window (window may be recreated on macOS)
        if (win && !win.isDestroyed()) {
          win.webContents.send('core:progress', p)
        }
      },
      payload.requestId
    )
  })
}
