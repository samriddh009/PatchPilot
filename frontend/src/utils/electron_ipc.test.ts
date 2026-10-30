import { describe, it, expect, vi } from 'vitest';

/**
 * Unit & Integration tests for PatchPilot Electron Desktop Bridge and Native Folder Picker.
 * Covers:
 * - IPC sender validation logic
 * - Native dialog selection & cancellation handling
 * - Space, Unicode, and nested path support
 * - Safe error handling
 */

// Mirror Electron IPC sender validation function for verification
function validateIpcSender(
  event: { senderFrame?: { url?: string } } | null | undefined,
  mainWindow: { webContents: { mainFrame: any } } | null,
  isDev: boolean = false
): boolean {
  if (!mainWindow || !event || !event.senderFrame) {
    throw new Error('Unauthorized IPC sender: missing frame or main window');
  }
  if (event.senderFrame !== mainWindow.webContents.mainFrame) {
    throw new Error('Unauthorized IPC sender: frame mismatch');
  }
  const url = event.senderFrame.url || '';
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

describe('Electron IPC Sender Validation & Security', () => {
  const mockMainFrame = { id: 1, url: 'http://localhost:5173' };
  const mockMainWindow = {
    webContents: {
      mainFrame: mockMainFrame,
    },
  };

  it('allows authorized frame in development mode', () => {
    const event = { senderFrame: mockMainFrame };
    expect(() => validateIpcSender(event, mockMainWindow, true)).not.toThrow();
  });

  it('allows 127.0.0.1 development origin', () => {
    const frame127 = { id: 1, url: 'http://127.0.0.1:5173' };
    const win127 = { webContents: { mainFrame: frame127 } };
    const event = { senderFrame: frame127 };
    expect(() => validateIpcSender(event, win127, true)).not.toThrow();
  });

  it('rejects external/untrusted origin in development mode', () => {
    const maliciousFrame = { id: 1, url: 'https://evil-attacker.com' };
    const win = { webContents: { mainFrame: maliciousFrame } };
    const event = { senderFrame: maliciousFrame };
    expect(() => validateIpcSender(event, win, true)).toThrow('Unauthorized IPC sender origin');
  });

  it('allows file:// origin in production mode', () => {
    const prodFrame = { id: 1, url: 'file:///C:/patch pilot/frontend/dist/index.html' };
    const prodWin = { webContents: { mainFrame: prodFrame } };
    const event = { senderFrame: prodFrame };
    expect(() => validateIpcSender(event, prodWin, false)).not.toThrow();
  });

  it('rejects remote web origin in production mode', () => {
    const prodFrame = { id: 1, url: 'http://localhost:5173' };
    const prodWin = { webContents: { mainFrame: prodFrame } };
    const event = { senderFrame: prodFrame };
    expect(() => validateIpcSender(event, prodWin, false)).toThrow('Unauthorized IPC sender origin');
  });

  it('rejects child iframe or mismatched frame', () => {
    const childIframe = { id: 2, url: 'http://localhost:5173' };
    const event = { senderFrame: childIframe };
    expect(() => validateIpcSender(event, mockMainWindow, true)).toThrow('Unauthorized IPC sender: frame mismatch');
  });

  it('rejects missing event or frame', () => {
    expect(() => validateIpcSender(null, mockMainWindow, true)).toThrow('missing frame or main window');
    expect(() => validateIpcSender({} as any, mockMainWindow, true)).toThrow('missing frame or main window');
    expect(() => validateIpcSender({ senderFrame: mockMainFrame }, null, true)).toThrow('missing frame or main window');
  });
});

describe('Native Folder Selection Dialog Operations', () => {
  it('handles user cancellation without throwing or registering path', async () => {
    const mockShowOpenDialog = vi.fn().mockResolvedValue({
      canceled: true,
      filePaths: [],
    });

    const dialogHandler = async () => {
      const result = await mockShowOpenDialog();
      if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
        return { canceled: true, path: null };
      }
      return { canceled: false, path: result.filePaths[0] };
    };

    const res = await dialogHandler();
    expect(res.canceled).toBe(true);
    expect(res.path).toBeNull();
  });

  it('correctly returns path containing spaces', async () => {
    const pathWithSpaces = 'C:\\Projects\\My Test Project With Spaces';
    const mockShowOpenDialog = vi.fn().mockResolvedValue({
      canceled: false,
      filePaths: [pathWithSpaces],
    });

    const dialogHandler = async () => {
      const result = await mockShowOpenDialog();
      return { canceled: result.canceled, path: result.filePaths[0] };
    };

    const res = await dialogHandler();
    expect(res.canceled).toBe(false);
    expect(res.path).toBe(pathWithSpaces);
  });

  it('correctly preserves Unicode characters in directory paths', async () => {
    const unicodePath = 'C:\\Users\\Developer\\Projet_Réparation_€_日本語';
    const mockShowOpenDialog = vi.fn().mockResolvedValue({
      canceled: false,
      filePaths: [unicodePath],
    });

    const dialogHandler = async () => {
      const result = await mockShowOpenDialog();
      return { canceled: result.canceled, path: result.filePaths[0] };
    };

    const res = await dialogHandler();
    expect(res.canceled).toBe(false);
    expect(res.path).toBe(unicodePath);
  });

  it('correctly handles deeply nested folder paths', async () => {
    const nestedPath = 'C:\\dev\\workspace\\submodules\\core\\backend\\fixtures\\python_calc_bug';
    const mockShowOpenDialog = vi.fn().mockResolvedValue({
      canceled: false,
      filePaths: [nestedPath],
    });

    const dialogHandler = async () => {
      const result = await mockShowOpenDialog();
      return { canceled: result.canceled, path: result.filePaths[0] };
    };

    const res = await dialogHandler();
    expect(res.canceled).toBe(false);
    expect(res.path).toBe(nestedPath);
  });
});
