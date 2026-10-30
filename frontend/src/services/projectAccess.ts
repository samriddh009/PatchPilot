/**
 * Shared Project Access Architecture for PatchPilot
 * 
 * Provides unified abstractions across Web and Desktop environments:
 * - WebProjectAdapter: Progressive enhancement with window.showDirectoryPicker() 
 *   and <input webkitdirectory> fallback, client-side secret filtering, and ingestion.
 * - DesktopProjectAdapter: Electron native Windows Explorer folder selection.
 * - ProjectAccessService: Shared validation, language detection, disclosure, and repository ingestion.
 */

import { api } from '../api/client';
import { Repository } from '../types/domain';

export interface IngestedFile {
  path: string;     // Normalized relative path (e.g. "calculator/pricing.py")
  content: string;  // UTF-8 text content
  size: number;
}

export interface ProjectSelectionMetadata {
  adapterType: 'desktop' | 'web' | 'manual';
  name: string;
  folderName: string;
  localPath?: string;
  files?: IngestedFile[];
  fileCount: number;
  excludedCount: number;
  detectedLanguages: string[];
}

export const EXCLUDED_DIR_NAMES = new Set([
  '.git',
  '.venv',
  'venv',
  '__pycache__',
  'node_modules',
  'dist',
  'build',
  'target',
  '.idea',
  '.vscode',
  '.pytest_cache',
  '.mypy_cache',
]);

export const SECRET_FILENAMES = new Set([
  'id_rsa',
  'id_dsa',
  'id_ed25519',
  'id_ecdsa',
  'credentials.json',
  'client_secret.json',
  'token.json',
  'auth.json',
  'secrets.json',
]);

export const SECRET_EXTENSIONS = new Set([
  '.pem',
  '.key',
  '.pkcs12',
  '.pfx',
  '.p12',
  '.keystore',
  '.jks',
]);

export const BINARY_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
  '.exe', '.dll', '.so', '.dylib', '.bin', '.obj',
  '.zip', '.tar', '.gz', '.7z', '.rar',
  '.pyc', '.pyo', '.class', '.jar',
  '.pdf', '.doc', '.docx', '.xls', '.xlsx',
  '.mp3', '.mp4', '.wav', '.mov', '.avi',
  '.woff', '.woff2', '.ttf', '.eot',
]);

export function isSecretFile(name: string): boolean {
  const lower = name.toLowerCase();
  if (lower === '.env' || lower.startsWith('.env.')) return true;
  if (SECRET_FILENAMES.has(lower)) return true;
  if (lower.startsWith('client_secret') && lower.endsWith('.json')) return true;
  if (lower.startsWith('service-account') && lower.endsWith('.json')) return true;
  for (const ext of SECRET_EXTENSIONS) {
    if (lower.endsWith(ext)) return true;
  }
  return false;
}

export function isBinaryFile(name: string): boolean {
  const lower = name.toLowerCase();
  for (const ext of BINARY_EXTENSIONS) {
    if (lower.endsWith(ext)) return true;
  }
  return false;
}

export function detectLanguageFromExtension(path: string): string | null {
  const lower = path.toLowerCase();
  if (lower.endsWith('.py')) return 'Python';
  if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'TypeScript';
  if (lower.endsWith('.js') || lower.endsWith('.jsx') || lower.endsWith('.mjs')) return 'JavaScript';
  if (lower.endsWith('.java')) return 'Java';
  if (lower.endsWith('.json') || lower.endsWith('.toml') || lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'Configuration';
  return null;
}

/**
 * Desktop Project Adapter — uses native Electron IPC bridge
 */
export class DesktopProjectAdapter {
  readonly type = 'desktop' as const;

  private getWindow(): any {
    return typeof window !== 'undefined' ? window : (globalThis as any).window;
  }

  isSupported(): boolean {
    const win = this.getWindow();
    return Boolean(win?.desktopApi?.openDirectory);
  }

  async selectDirectory(): Promise<{ canceled: boolean; path: string | null }> {
    const win = this.getWindow();
    if (!this.isSupported() || !win?.desktopApi?.openDirectory) {
      throw new Error('Desktop project adapter is unavailable outside Electron environment');
    }
    return await win.desktopApi.openDirectory();
  }
}

/**
 * Web Project Adapter — progressive enhancement for browser environments
 */
export class WebProjectAdapter {
  readonly type = 'web' as const;

  isSupported(): boolean {
    return typeof window !== 'undefined';
  }

  hasDirectoryPicker(): boolean {
    return typeof window !== 'undefined' && 'showDirectoryPicker' in window;
  }

  /**
   * Primary Web Method: window.showDirectoryPicker()
   * MUST be invoked directly within user activation click handler
   */
  async selectWithDirectoryPicker(): Promise<ProjectSelectionMetadata | null> {
    if (!this.hasDirectoryPicker()) {
      throw new Error('window.showDirectoryPicker is not supported in this browser');
    }

    let dirHandle: any;
    try {
      dirHandle = await (window as any).showDirectoryPicker({ mode: 'read' });
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return null; // User cancelled dialog cleanly
      }
      throw err;
    }

    const files: IngestedFile[] = [];
    let excludedCount = 0;
    const detectedLangs = new Set<string>();

    const readDirectory = async (handle: any, currentPath: string) => {
      for await (const [name, entry] of handle.entries()) {
        if (entry.kind === 'directory') {
          if (EXCLUDED_DIR_NAMES.has(name) || name.startsWith('.')) {
            excludedCount++;
            continue;
          }
          await readDirectory(entry, currentPath ? `${currentPath}/${name}` : name);
        } else if (entry.kind === 'file') {
          const relPath = currentPath ? `${currentPath}/${name}` : name;
          if (isSecretFile(name) || isBinaryFile(name)) {
            excludedCount++;
            continue;
          }

          const file = await entry.getFile();
          if (file.size > 1_000_000) { // Skip files > 1MB
            excludedCount++;
            continue;
          }

          try {
            const text = await file.text();
            files.push({
              path: relPath.replace(/\\/g, '/'),
              content: text,
              size: file.size,
            });
            const lang = detectLanguageFromExtension(name);
            if (lang) detectedLangs.add(lang);
          } catch {
            excludedCount++;
          }
        }
      }
    };

    await readDirectory(dirHandle, '');

    return {
      adapterType: 'web',
      name: dirHandle.name,
      folderName: dirHandle.name,
      files,
      fileCount: files.length,
      excludedCount,
      detectedLanguages: Array.from(detectedLangs),
    };
  }

  /**
   * Fallback Web Method: HTML input with webkitdirectory
   */
  async selectWithFileInput(): Promise<ProjectSelectionMetadata | null> {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.webkitdirectory = true;
      (input as any).directory = true;
      input.multiple = true;
      input.style.display = 'none';

      let resolved = false;

      input.onchange = async (e: Event) => {
        resolved = true;
        const target = e.target as HTMLInputElement;
        const fileList = target.files;
        if (!fileList || fileList.length === 0) {
          resolve(null);
          return;
        }

        try {
          const files: IngestedFile[] = [];
          let excludedCount = 0;
          const detectedLangs = new Set<string>();
          let rootFolderName = 'uploaded_project';

          for (let i = 0; i < fileList.length; i++) {
            const file = fileList[i];
            const rawRelative = file.webkitRelativePath || file.name;
            const parts = rawRelative.replace(/\\/g, '/').split('/');

            if (parts.length > 1) {
              rootFolderName = parts[0];
            }

            // Path relative to root folder
            const relativeToRoot = parts.slice(1).join('/');
            const fileName = parts[parts.length - 1];

            // Check if any parent directory is excluded
            const inExcludedDir = parts.slice(1, -1).some((p) => EXCLUDED_DIR_NAMES.has(p) || p.startsWith('.'));
            if (inExcludedDir || isSecretFile(fileName) || isBinaryFile(fileName)) {
              excludedCount++;
              continue;
            }

            if (file.size > 1_000_000) { // Limit 1MB per file
              excludedCount++;
              continue;
            }

            try {
              const text = await file.text();
              files.push({
                path: relativeToRoot || fileName,
                content: text,
                size: file.size,
              });
              const lang = detectLanguageFromExtension(fileName);
              if (lang) detectedLangs.add(lang);
            } catch {
              excludedCount++;
            }
          }

          resolve({
            adapterType: 'web',
            name: rootFolderName,
            folderName: rootFolderName,
            files,
            fileCount: files.length,
            excludedCount,
            detectedLanguages: Array.from(detectedLangs),
          });
        } catch (readErr) {
          reject(readErr);
        } finally {
          document.body.removeChild(input);
        }
      };

      // Handle user cancellation if dialog is closed without selection
      window.addEventListener(
        'focus',
        () => {
          setTimeout(() => {
            if (!resolved && document.body.contains(input)) {
              document.body.removeChild(input);
              resolve(null);
            }
          }, 600);
        },
        { once: true }
      );

      document.body.appendChild(input);
      input.click();
    });
  }
}

/**
 * Shared Project Access Service — orchestrates selection and registration
 */
export class ProjectAccessService {
  private desktopAdapter = new DesktopProjectAdapter();
  private webAdapter = new WebProjectAdapter();

  isDesktop(): boolean {
    return this.desktopAdapter.isSupported();
  }

  hasNativeDirectoryPicker(): boolean {
    return this.webAdapter.hasDirectoryPicker();
  }

  /**
   * Ingest project files from browser into PatchPilot isolated backend workspace
   */
  async ingestWebProject(metadata: ProjectSelectionMetadata): Promise<Repository> {
    if (!metadata.files || metadata.files.length === 0) {
      throw new Error('No valid source files were selected for ingestion.');
    }

    const payload = {
      name: metadata.name || metadata.folderName || 'Web Project',
      files: metadata.files.map((f) => ({
        path: f.path,
        content: f.content,
      })),
    };

    const res = await api.ingestRepository(payload);
    return res.data;
  }

  /**
   * Register local path directly (Desktop mode)
   */
  async registerLocalPath(path: string, displayName?: string): Promise<Repository> {
    const cleanPath = path.trim().replace(/^["']|["']$/g, '');
    if (!cleanPath) {
      throw new Error('Project path cannot be empty.');
    }
    const res = await api.openLocalRepository(cleanPath, displayName?.trim() || undefined);
    return res.data;
  }
}

export const projectAccessService = new ProjectAccessService();
