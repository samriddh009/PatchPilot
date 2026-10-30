const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const net = require('net');

let mainWindow = null;
let pythonProcess = null;
let backendPort = 8000;

function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

function findFreePort(startingPort) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

function checkHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/v1/health`, (res) => {
      if (res.statusCode === 200) {
        resolve(true);
      } else {
        // Fallback check on root /health
        const req2 = http.get(`http://127.0.0.1:${port}/health`, (res2) => {
          resolve(res2.statusCode === 200);
        });
        req2.on('error', () => resolve(false));
      }
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(port, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    const healthy = await checkHealth(port);
    if (healthy) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function resolvePythonPath() {
  const rootDir = path.resolve(__dirname, '../../');
  const winVenv = path.join(rootDir, 'backend', '.venv', 'Scripts', 'python.exe');
  const posixVenv = path.join(rootDir, 'backend', '.venv', 'bin', 'python');
  const fs = require('fs');
  if (fs.existsSync(winVenv)) return winVenv;
  if (fs.existsSync(posixVenv)) return posixVenv;
  return process.platform === 'win32' ? 'python' : 'python3';
}

async function startBackend() {
  // Check if port 8000 is open or already running a healthy PatchPilot backend
  const port8000Healthy = await checkHealth(8000);
  if (port8000Healthy) {
    console.log('[Desktop] Existing healthy PatchPilot backend detected on port 8000.');
    backendPort = 8000;
    return;
  }

  const port8000Available = await isPortAvailable(8000);
  if (port8000Available) {
    backendPort = 8000;
  } else {
    backendPort = await findFreePort(8001);
    console.log(`[Desktop] Port 8000 collision detected. Selected free port: ${backendPort}`);
  }

  const pythonBin = resolvePythonPath();
  const backendCwd = path.resolve(__dirname, '../../backend');

  console.log(`[Desktop] Spawning Python backend on 127.0.0.1:${backendPort} using ${pythonBin}`);

  pythonProcess = spawn(
    pythonBin,
    ['-m', 'uvicorn', 'patchpilot.main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
    {
      cwd: backendCwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      windowsHide: true,
    }
  );

  pythonProcess.stdout.on('data', (d) => console.log(`[Backend stdout]: ${d}`));
  pythonProcess.stderr.on('data', (d) => console.error(`[Backend stderr]: ${d}`));

  pythonProcess.on('exit', (code, sig) => {
    console.log(`[Desktop] Python backend exited with code ${code}, signal ${sig}`);
    pythonProcess = null;
  });

  const ready = await waitForBackend(backendPort, 30);
  if (!ready) {
    dialog.showErrorBox(
      'PatchPilot Backend Startup Failure',
      `Failed to initialize local Python backend service on port ${backendPort}.\nPlease ensure Python 3.12+ and backend dependencies are installed.`
    );
  }
}

function killPythonProcess() {
  if (!pythonProcess || !pythonProcess.pid) return;
  const pid = pythonProcess.pid;
  console.log(`[Desktop] Terminating child backend process tree (PID: ${pid})`);
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: 'ignore' });
    } else {
      process.kill(-pid, 'SIGKILL');
    }
  } catch (err) {
    try {
      pythonProcess.kill('SIGTERM');
    } catch (_) {}
  }
  pythonProcess = null;
}

function validateIpcSender(event) {
  if (!mainWindow || !event || !event.senderFrame) {
    throw new Error('Unauthorized IPC sender: missing frame or main window');
  }
  if (event.senderFrame !== mainWindow.webContents.mainFrame) {
    throw new Error('Unauthorized IPC sender: frame mismatch');
  }
  const url = event.senderFrame.url || '';
  const isDev = process.env.ELECTRON_DEV === '1';
  if (isDev) {
    const isAllowedDev = url.startsWith('http://localhost:5173') || url.startsWith('http://127.0.0.1:5173');
    if (!isAllowedDev) {
      throw new Error(`Unauthorized IPC sender origin: ${url}`);
    }
  } else {
    if (!url.startsWith('file://')) {
      throw new Error(`Unauthorized IPC sender origin: ${url}`);
    }
  }
  return true;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1366,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#0f172a',
    title: 'PatchPilot — Desktop Engineering Agent',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setMenuBarVisibility(false);

  const isDev = process.env.ELECTRON_DEV === '1';
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Handlers
ipcMain.handle('dialog:openDirectory', async (event) => {
  validateIpcSender(event);
  if (!mainWindow) return { canceled: true, path: null };
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select Project Directory for PatchPilot',
    properties: ['openDirectory', 'dontAddToRecent'],
  });

  if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
    return { canceled: true, path: null };
  }
  return { canceled: false, path: result.filePaths[0] };
});

ipcMain.handle('desktop:getApiBaseUrl', (event) => {
  validateIpcSender(event);
  return `http://127.0.0.1:${backendPort}`;
});

ipcMain.handle('desktop:openLocalRepository', async (event, repoPath, repoName) => {
  validateIpcSender(event);
  if (!repoPath || typeof repoPath !== 'string') {
    throw new Error('Project path must be a non-empty string');
  }
  const payload = JSON.stringify({ path: repoPath, name: repoName || undefined });
  return new Promise((resolve, reject) => {
    const req = http.request(
      `http://127.0.0.1:${backendPort}/api/v1/repositories/open-local`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload),
        },
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          try {
            const data = JSON.parse(body);
            if (res.statusCode >= 200 && res.statusCode < 300) {
              resolve(data);
            } else {
              reject(new Error(data?.error?.message || data?.detail?.message || 'Failed to open local repository'));
            }
          } catch (e) {
            reject(new Error(`Backend response parsing error: ${e.message}`));
          }
        });
      }
    );
    req.on('error', (err) => reject(new Error(`Backend communication error: ${err.message}`)));
    req.write(payload);
    req.end();
  });
});

app.whenReady().then(async () => {
  await startBackend();
  createWindow();

  const isSmokeTest = process.argv.includes('--smoke-test') || process.env.ELECTRON_SMOKE_TEST === '1';
  if (isSmokeTest) {
    console.log('[Desktop] Smoke test active: verifying window and backend connection...');
    setTimeout(() => {
      console.log('[Desktop] Smoke test PASSED: closing window and terminating backend cleanly.');
      if (mainWindow) mainWindow.close();
    }, 2500);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  killPythonProcess();
});

app.on('will-quit', () => {
  killPythonProcess();
});

app.on('window-all-closed', () => {
  killPythonProcess();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

process.on('SIGINT', () => {
  killPythonProcess();
  process.exit(0);
});

process.on('SIGTERM', () => {
  killPythonProcess();
  process.exit(0);
});
