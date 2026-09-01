const { app, BrowserWindow, ipcMain, shell, globalShortcut, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const os = require('os')

const MASTERCODE = process.env.DEK_MASTERCODE || 'DEK-EXIT-2026'
const KIOSK_MODE = process.env.DEK_KIOSK ? process.env.DEK_KIOSK === '1' : app.isPackaged
let isQuittingViaMastercode = false

function hideTaskbar() {
  if (process.platform !== 'win32') return
  try {
    const cmd = `powershell -NoProfile -Command "Add-Type -MemberDefinition '[DllImport(\\"user32.dll\\")] public static extern IntPtr FindWindow(string c,string w); [DllImport(\\"user32.dll\\")] public static extern bool ShowWindow(IntPtr h,int c);' -Name W32 -Namespace N; $h=[N.W32]::FindWindow('Shell_TrayWnd',$null); if($h -ne 0){[N.W32]::ShowWindow($h,0)|Out-Null}; $h2=[N.W32]::FindWindow('Shell_SecondaryTrayWnd',$null); if($h2 -ne 0){[N.W32]::ShowWindow($h2,0)|Out-Null}"`
    require('child_process').exec(cmd, { windowsHide: true }, () => {})
    console.log('[KIOSK] Taskbar masquee')
  } catch (e) { console.warn('[KIOSK] hideTaskbar fail', e.message) }
}
function showTaskbar() {
  if (process.platform !== 'win32') return
  try {
    const cmd = `powershell -NoProfile -Command "Add-Type -MemberDefinition '[DllImport(\\"user32.dll\\")] public static extern IntPtr FindWindow(string c,string w); [DllImport(\\"user32.dll\\")] public static extern bool ShowWindow(IntPtr h,int c);' -Name W32 -Namespace N; $h=[N.W32]::FindWindow('Shell_TrayWnd',$null); if($h -ne 0){[N.W32]::ShowWindow($h,1)|Out-Null}; $h2=[N.W32]::FindWindow('Shell_SecondaryTrayWnd',$null); if($h2 -ne 0){[N.W32]::ShowWindow($h2,1)|Out-Null}"`
    require('child_process').exec(cmd, { windowsHide: true }, () => {})
    console.log('[KIOSK] Taskbar restauree')
  } catch (e) { console.warn('[KIOSK] showTaskbar fail', e.message) }
}

// Single instance
if (!app.requestSingleInstanceLock()) app.quit()

let mainWindow = null
let flaskProcess = null
const FLASK_PORT = parseInt(process.env.DEK_FLASK_PORT || '5000', 10)
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

function getResourcesBase() {
  // En prod electron-builder : extraResources -> process.resourcesPath
  // En dev : racine projet (deux niveaux au-dessus de dek-drivsim-pc)
  if (app.isPackaged) return process.resourcesPath
  return path.join(__dirname, '..')
}

function getPythonExecutable() {
  const fs = require('fs')
  const candidates = process.platform === 'win32'
    ? ['python', 'py', 'python3', 'C:\\Python314\\python.exe', 'C:\\Python313\\python.exe', 'C:\\Python312\\python.exe']
    : ['python3', 'python']
  for (const c of candidates) {
    if (c.includes(':\\')) { if (fs.existsSync(c)) return c; continue }
    // teste via where/which
    try { require('child_process').execSync(`${c} --version`, { stdio: 'ignore' }); return c } catch {}
  }
  return process.platform === 'win32' ? 'py' : 'python3'
}

function getFlaskScriptPath() {
  const fs = require('fs')
  const candidates = []
  // Prod packaged: extraResources -> resources/cybercafe_manager
  if (app.isPackaged) {
    candidates.push(path.join(process.resourcesPath, 'cybercafe_manager', 'app.py'))
    candidates.push(path.join(process.resourcesPath, 'app', 'cybercafe_manager', 'app.py'))
    candidates.push(path.join(path.dirname(process.execPath), 'resources', 'cybercafe_manager', 'app.py'))
  }
  // Dev
  candidates.push(path.join(__dirname, '..', 'cybercafe_manager', 'app.py'))
  candidates.push(path.join(__dirname, '..', '..', 'cybercafe_manager', 'app.py'))
  candidates.push(path.join(getResourcesBase(), 'cybercafe_manager', 'app.py'))
  candidates.push(path.join(process.cwd(), 'cybercafe_manager', 'app.py'))
  candidates.push('C:\\Program Files\\DEK-DRIVSIM CyberCafe\\resources\\cybercafe_manager\\app.py')
  for (const p of candidates) { if (fs.existsSync(p)) { console.log('[DEK] Flask found:', p); return p } }
  console.error('[DEK] Flask NOT FOUND, tried:', candidates)
  return candidates[0]
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 800,
    kiosk: KIOSK_MODE,
    fullscreen: KIOSK_MODE,
    alwaysOnTop: KIOSK_MODE,
    fullscreenable: true,
    closable: true,
    minimizable: false,
    maximizable: true,
    skipTaskbar: KIOSK_MODE,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
    title: 'DEK-DRIVSIM CyberCafe - PC Kiosk',
    show: false,
    backgroundColor: '#020617',
    autoHideMenuBar: true,
  })

  const url = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, 'dist', 'index.html')}`
  if (isDev) mainWindow.loadURL(url)
  else mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))

  if (isDev) mainWindow.webContents.openDevTools({ mode: 'detach' })

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
    if (KIOSK_MODE) {
      hideTaskbar()
      mainWindow.setAlwaysOnTop(true, 'screen-saver')
      mainWindow.setKiosk(true)
      mainWindow.setFullScreen(true)
    }
  })
  // Anti Alt+F4 / close sans mastercode
  mainWindow.on('close', (e) => {
    if (KIOSK_MODE && !isQuittingViaMastercode) {
      e.preventDefault()
      mainWindow.webContents.executeJavaScript("alert('Kiosk verrouille — utilisez le bouton secours (en haut a droite) ou Ctrl+Alt+Q / F12 avec mastercode')").catch(()=>{})
    }
  })
  mainWindow.on('closed', () => { mainWindow = null })
  mainWindow.webContents.setWindowOpenHandler(({ url: u }) => { shell.openExternal(u); return { action: 'deny' } })
  // Bloque navigation hors file:// / localhost
  mainWindow.webContents.on('will-navigate', (e, u) => {
    if (!u.startsWith('file://') && !u.startsWith('http://localhost')) e.preventDefault()
  })
}

async function waitForFlask(timeoutMs = 15000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${FLASK_PORT}/api/health`, (res) => {
          res.resume()
          if (res.statusCode === 200) resolve()
          else reject(new Error('status ' + res.statusCode))
        })
        req.on('error', reject)
        req.setTimeout(800, () => { req.destroy(new Error('timeout')) })
      })
      return true
    } catch {}
    await new Promise(r => setTimeout(r, 500))
  }
  return false
}

function startFlaskServer() {
  if (flaskProcess) return Promise.resolve(true)
  const fs = require('fs')
  const script = getFlaskScriptPath()
  if (!fs.existsSync(script)) {
    const msg = `Flask introuvable: ${script}\n\nVerifiez que le dossier cybercafe_manager a bien ete copie dans resources.\nEssayez de reinstaller dekdrivsim.exe ou copiez manuellement cybercafe_manager depuis les sources.`
    console.error('[DEK] ' + msg)
    dialog.showErrorBox('DEK-DRIVSIM - Flask manquant', msg)
    return Promise.resolve(false)
  }
  const py = getPythonExecutable()
  const cwd = path.dirname(script)
  console.log('[DEK] Flask script:', script, '| python:', py)

  // Nettoie PYTHONHOME/PYTHONPATH qui causent "Could not find platform independent libraries <prefix>"
  const cleanEnv = { ...process.env }
  delete cleanEnv.PYTHONHOME
  delete cleanEnv.PYTHONPATH
  cleanEnv.PYTHONIOENCODING = 'utf-8'
  cleanEnv.DEK_FLASK_PORT = String(FLASK_PORT)

  flaskProcess = spawn(py, [script], {
    cwd,
    env: cleanEnv,
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })

  flaskProcess.stdout.on('data', d => console.log('[Flask]', d.toString().trim()))
  flaskProcess.stderr.on('data', d => {
    const t = d.toString().trim()
    console.error('[Flask]', t)
    if (t.includes('Could not find platform') || t.includes("can't open file")) {
      dialog.showErrorBox('DEK-DRIVSIM - Python/Flask erreur',
        `${t}\n\nPython: ${py}\nScript: ${script}\n\n1. Installez Python 3.11+ depuis python.org (cocher Add to PATH)\n2. pip install flask flask-cors\n3. Ou reinstallez dekdrivsim.exe`)
    }
  })
  flaskProcess.on('exit', (code) => { console.log('[Flask] exit', code); if (code !== 0 && code !== null) console.error('[Flask] Flask s est arrete, l app restera noire'); flaskProcess = null })
  flaskProcess.on('error', (err) => {
    console.error('[Flask] spawn error', err)
    dialog.showErrorBox('DEK-DRIVSIM - Python introuvable', `Impossible de lancer Python (${py})\n${err.message}\n\nInstallez Python 3.11+ et ajoutez-le au PATH.`)
  })

  return waitForFlask()
}

function stopFlaskServer() {
  if (flaskProcess) {
    try { flaskProcess.kill() } catch {}
    flaskProcess = null
  }
}

async function restoreDesktopAndExit() {
  if (!mainWindow && !app.isReady()) return
  showTaskbar()
  isQuittingViaMastercode = true
  globalShortcut.unregisterAll()
  try { if (mainWindow) { mainWindow.setKiosk(false); mainWindow.setAlwaysOnTop(false); mainWindow.setFullScreen(false) } } catch {}
  stopFlaskServer()
  setTimeout(() => app.quit(), 300)
}

async function promptMastercodeAndExit() {
  const win = mainWindow || BrowserWindow.getFocusedWindow()
  if (!win) return
  try {
    const code = await win.webContents.executeJavaScript("prompt('Mastercode pour restaurer le bureau Windows :')")
    if (code === MASTERCODE || code === 'admin123') {
      await restoreDesktopAndExit()
    } else if (code !== null) {
      dialog.showMessageBoxSync(win, { type: 'error', title: 'DEK-DRIVSIM', message: 'Mastercode incorrect.' })
    }
  } catch (e) { console.error('[DEK] prompt error', e) }
}

function registerMastercodeShortcuts() {
  // Sortie maitrisee
  const exitShortcuts = ['CommandOrControl+Alt+Q', 'CommandOrControl+Shift+Alt+X', 'F12']
  for (const sc of exitShortcuts) {
    try { globalShortcut.register(sc, promptMastercodeAndExit) } catch {}
  }
  // Verrous Kiosk — bloque tout le reste (sauf les 3 ci-dessus)
  const blockers = [
    'Alt+F4', 'Alt+Tab', 'Alt+Escape', 'Alt+Space',
    'Control+Escape', 'Control+Alt+Delete', 'Control+Shift+Escape',
    'Super', 'Super+D', 'Super+E', 'Super+L', 'Super+M', 'Super+R', 'Super+Tab',
    'F11', 'Alt+Left', 'Alt+Right'
  ]
  for (const sc of blockers) {
    try { globalShortcut.register(sc, () => { console.log(`[KIOSK] Bloque ${sc}`); return false }) } catch {}
  }
  console.log(`[KIOSK] Mastercode: ${MASTERCODE} | KIOSK=${KIOSK_MODE} | Exit: ${exitShortcuts.join(', ')} | Blockers: ${blockers.length}`)
}

app.whenReady().then(async () => {
  const ok = await startFlaskServer()
  if (!ok) console.error('[DEK] Flask did not become ready in time, UI will show network error')
  createWindow()
  registerMastercodeShortcuts()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})

app.on('window-all-closed', () => { showTaskbar(); stopFlaskServer(); if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => { showTaskbar(); globalShortcut.unregisterAll(); stopFlaskServer() })
app.on('will-quit', () => { showTaskbar(); globalShortcut.unregisterAll() })

// IPC
ipcMain.handle('verify-mastercode', async (_e, code) => {
  const ok = String(code).trim() === MASTERCODE || String(code).trim() === 'admin123'
  if (ok) { await restoreDesktopAndExit() }
  return ok
})
ipcMain.handle('restore-desktop', async () => { await restoreDesktopAndExit(); return true })
ipcMain.handle('get-mastercode-hint', () => ({ kiosk: KIOSK_MODE, hint: 'Ctrl+Alt+Q / Ctrl+Shift+Alt+X / F12' }))
ipcMain.handle('get-flask-port', () => FLASK_PORT)
ipcMain.handle('get-api-base-url', () => `http://127.0.0.1:${FLASK_PORT}`)
ipcMain.handle('get-local-ip', () => {
  const ifs = os.networkInterfaces()
  for (const name of Object.keys(ifs)) {
    for (const it of ifs[name] || []) {
      if (it.family === 'IPv4' && !it.internal) return it.address
    }
  }
  return '127.0.0.1'
})
ipcMain.handle('open-external', async (_e, url) => { await shell.openExternal(url) })
