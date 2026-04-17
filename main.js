const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const fs = require('fs');

const logDir    = app.getPath('userData');
const logPath   = path.join(logDir, 'recbert.log');
const logStream = fs.createWriteStream(logPath, { flags: 'a' });

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  logStream.write(line + '\n');
}

let config = {
  backendPath: '',
  pythonExecutable: 'python',
  flaskPort: 5000,
  autoStartBackend: true
};

const configPath = path.join(__dirname, 'config.json');
log(`Config path: ${configPath}`);

if (fs.existsSync(configPath)) {
  try {
    const loaded = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    config = { ...config, ...loaded };
    log(`Config loaded: ${JSON.stringify(config)}`);
  } catch (e) {
    log(`Could not read config.json: ${e.message}`);
  }
} else {
  log(`config.json NOT FOUND at ${configPath}`);
}

const FLASK_URL = `http://localhost:${config.flaskPort}`;

let mainWindow    = null;
let pythonProcess = null;
let isQuitting    = false;

const SCROLLBAR_CSS = `
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: transparent; margin-top: 36px; }
  ::-webkit-scrollbar-thumb { background: rgba(0,102,255,0.35); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(0,102,255,0.6); }
`;

function killPythonProcess() {
  if (!pythonProcess) return;
  const pid = pythonProcess.pid;
  log(`Killing Python process tree — PID: ${pid}`);
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(pid), '/f', '/t']);
    } else {
      process.kill(-pid, 'SIGKILL');
    }
  } catch (e) {
    log(`taskkill error: ${e.message}`);
  }
  pythonProcess = null;
}

function setStatus(msg) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.executeJavaScript(
    `document.getElementById('status').innerHTML = ${JSON.stringify(msg)};`
  ).catch(() => {});
}

function waitForBackend(maxAttempts = 120, interval = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      setStatus(`Connecting to backend... (${attempts}/${maxAttempts})`);
      const req = http.get(FLASK_URL, () => {
        log('Backend is up!');
        resolve();
      });
      req.on('error', () => {
        if (attempts < maxAttempts) setTimeout(check, interval);
        else reject(new Error('Backend did not start in time.'));
      });
      req.setTimeout(800, () => {
        req.destroy();
        if (attempts < maxAttempts) setTimeout(check, interval);
        else reject(new Error('Backend timed out.'));
      });
    };
    check();
  });
}

function startPythonBackend() {
  if (!config.autoStartBackend) {
    log('autoStartBackend is disabled.');
    return;
  }

  let backendDir = config.backendPath || __dirname;
  if (backendDir === '.') backendDir = __dirname;

  log(`Backend dir: ${backendDir}`);
  log(`Python exe:  ${config.pythonExecutable}`);

  if (!fs.existsSync(backendDir)) {
    const msg = `Backend path not found:\n${backendDir}\n\nLog: ${logPath}`;
    log(`ERROR: ${msg}`);
    dialog.showErrorBox('Recbert AI — Startup Error', msg);
    return;
  }

  const scriptPath = path.join(backendDir, 'main_local.py');
  log(`Script path: ${scriptPath}`);

  if (!fs.existsSync(scriptPath)) {
    const msg = `main_local.py not found:\n${scriptPath}\n\nLog: ${logPath}`;
    log(`ERROR: ${msg}`);
    dialog.showErrorBox('Recbert AI — Startup Error', msg);
    return;
  }

  if (!fs.existsSync(config.pythonExecutable)) {
    const msg = `Python executable not found:\n${config.pythonExecutable}\n\nLog: ${logPath}`;
    log(`ERROR: ${msg}`);
    dialog.showErrorBox('Recbert AI — Startup Error', msg);
    return;
  }

  pythonProcess = spawn(`"${config.pythonExecutable}"`, [`"${scriptPath}"`], {
    cwd: backendDir,
    shell: process.platform === 'win32',
    detached: false
  });

  pythonProcess.stdout.on('data', (data) => {
    log(`[python stdout] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    log(`[python stderr] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code, signal) => {
    log(`Python process exited — code: ${code}, signal: ${signal}`);
    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    const msg = `Failed to start Python:\n${err.message}\n\nLog: ${logPath}`;
    log(`ERROR: ${msg}`);
    dialog.showErrorBox('Recbert AI — Startup Error', msg);
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#EBF4FF',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
      allowRunningInsecureContent: true
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'loading.html'));

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.maximize();
  });

  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.insertCSS(SCROLLBAR_CSS);
  });

  try {
    await waitForBackend();
    mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  } catch (err) {
    log(`ERROR waiting for backend: ${err.message}`);
    setStatus(
      `<span style="color:#ff6b6b;">
        ⚠️ Recbert AI could not start.<br>
        <small style="font-size:0.78rem">
          Log: <b>${logPath}</b>
        </small>
      </span>`
    );
  }
}

app.whenReady().then(() => {
  log('App ready — starting backend...');
  startPythonBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  if (isQuitting) return;
  isQuitting = true;
  log('App quitting — killing Python...');
  killPythonProcess();
  logStream.end();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.on('window-minimize', () => { if (mainWindow) mainWindow.minimize(); });

ipcMain.on('window-maximize', () => {
  if (!mainWindow) return;
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});

ipcMain.on('window-close', () => { if (mainWindow) mainWindow.close(); });

ipcMain.handle('window-is-maximized', () => mainWindow ? mainWindow.isMaximized() : false);

ipcMain.on('open-external', (event, url) => { shell.openExternal(url); });

app.on('ready', () => {
  setInterval(() => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('maximize-changed', mainWindow.isMaximized());
    }
  }, 500);
});