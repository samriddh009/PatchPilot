import { describe, it, expect, vi } from 'vitest';
import {
  isSecretFile,
  isBinaryFile,
  detectLanguageFromExtension,
  DesktopProjectAdapter,
  WebProjectAdapter,
  ProjectAccessService,
  ProjectSelectionMetadata,
} from './projectAccess';
import { api } from '../api/client';

describe('Project Access Architecture — Utilities', () => {
  it('identifies secret files and excludes them from ingestion', () => {
    expect(isSecretFile('.env')).toBe(true);
    expect(isSecretFile('.env.production')).toBe(true);
    expect(isSecretFile('.env.local')).toBe(true);
    expect(isSecretFile('id_rsa')).toBe(true);
    expect(isSecretFile('id_ed25519')).toBe(true);
    expect(isSecretFile('credentials.json')).toBe(true);
    expect(isSecretFile('client_secret_123.json')).toBe(true);
    expect(isSecretFile('service-account.json')).toBe(true);
    expect(isSecretFile('server.key')).toBe(true);
    expect(isSecretFile('cert.pem')).toBe(true);
    expect(isSecretFile('keystore.jks')).toBe(true);

    // Normal files must NOT be marked secret
    expect(isSecretFile('pricing.py')).toBe(false);
    expect(isSecretFile('index.ts')).toBe(false);
    expect(isSecretFile('package.json')).toBe(false);
    expect(isSecretFile('App.tsx')).toBe(false);
  });

  it('identifies binary files and prevents reading non-text content', () => {
    expect(isBinaryFile('image.png')).toBe(true);
    expect(isBinaryFile('photo.jpg')).toBe(true);
    expect(isBinaryFile('binary.exe')).toBe(true);
    expect(isBinaryFile('library.dll')).toBe(true);
    expect(isBinaryFile('module.pyc')).toBe(true);
    expect(isBinaryFile('archive.zip')).toBe(true);

    // Code files are not binary
    expect(isBinaryFile('calculator.py')).toBe(false);
    expect(isBinaryFile('pricing.ts')).toBe(false);
    expect(isBinaryFile('Main.java')).toBe(false);
  });

  it('accurately maps file extensions to language categories', () => {
    expect(detectLanguageFromExtension('main.py')).toBe('Python');
    expect(detectLanguageFromExtension('component.tsx')).toBe('TypeScript');
    expect(detectLanguageFromExtension('index.ts')).toBe('TypeScript');
    expect(detectLanguageFromExtension('server.js')).toBe('JavaScript');
    expect(detectLanguageFromExtension('Main.java')).toBe('Java');
    expect(detectLanguageFromExtension('config.toml')).toBe('Configuration');
    expect(detectLanguageFromExtension('schema.json')).toBe('Configuration');
    expect(detectLanguageFromExtension('notes.txt')).toBeNull();
  });
});

describe('DesktopProjectAdapter', () => {
  it('detects desktop support based on window.desktopApi', () => {
    const adapter = new DesktopProjectAdapter();
    // In test environment window.desktopApi might be undefined
    const isSupp = adapter.isSupported();
    expect(typeof isSupp).toBe('boolean');
  });

  it('delegates directory opening to window.desktopApi.openDirectory', async () => {
    const mockOpen = vi.fn().mockResolvedValue({ canceled: false, path: 'C:\\Projects\\Test' });
    (globalThis as any).window = { desktopApi: { openDirectory: mockOpen, isDesktop: true } };

    const adapter = new DesktopProjectAdapter();
    expect(adapter.isSupported()).toBe(true);

    const res = await adapter.selectDirectory();
    expect(mockOpen).toHaveBeenCalled();
    expect(res.path).toBe('C:\\Projects\\Test');
    delete (globalThis as any).window;
  });
});

describe('WebProjectAdapter', () => {
  it('detects showDirectoryPicker capability', () => {
    const adapter = new WebProjectAdapter();
    expect(typeof adapter.hasDirectoryPicker()).toBe('boolean');
  });
});

describe('ProjectAccessService', () => {
  it('ingestWebProject calls api.ingestRepository with validated payload', async () => {
    const mockIngest = vi.spyOn(api, 'ingestRepository').mockResolvedValue({
      data: {
        id: 'repo_web_12345',
        name: 'test_project',
        language: 'python',
        test_framework: 'pytest',
        file_count: 2,
        is_fixture: false,
        execution_allowed: true,
        layout_status: 'supported',
        created_at: '2026-10-16T00:00:00Z',
      },
    } as any);

    const service = new ProjectAccessService();
    const metadata: ProjectSelectionMetadata = {
      adapterType: 'web',
      name: 'test_project',
      folderName: 'test_project',
      fileCount: 2,
      excludedCount: 1,
      detectedLanguages: ['Python'],
      files: [
        { path: 'main.py', content: 'print("hi")', size: 12 },
        { path: 'test_main.py', content: 'assert True', size: 11 },
      ],
    };

    const repo = await service.ingestWebProject(metadata);
    expect(mockIngest).toHaveBeenCalledWith({
      name: 'test_project',
      files: [
        { path: 'main.py', content: 'print("hi")' },
        { path: 'test_main.py', content: 'assert True' },
      ],
    });
    expect(repo.id).toBe('repo_web_12345');
    mockIngest.mockRestore();
  });

  it('registerLocalPath normalizes surrounding quotes and calls api.openLocalRepository', async () => {
    const mockOpen = vi.spyOn(api, 'openLocalRepository').mockResolvedValue({
      data: {
        id: 'repo_local_99999',
        name: 'my-app',
        language: 'python',
        test_framework: 'pytest',
        file_count: 5,
        is_fixture: false,
        execution_allowed: true,
        layout_status: 'supported',
        created_at: '2026-10-16T00:00:00Z',
      },
    } as any);

    const service = new ProjectAccessService();
    const repo = await service.registerLocalPath('"C:\\Users\\Dev\\my-app"', 'my-app');

    expect(mockOpen).toHaveBeenCalledWith('C:\\Users\\Dev\\my-app', 'my-app');
    expect(repo.id).toBe('repo_local_99999');
    mockOpen.mockRestore();
  });

  it('registerLocalPath throws an error for empty path input', async () => {
    const service = new ProjectAccessService();
    await expect(service.registerLocalPath('   ')).rejects.toThrow('Project path cannot be empty.');
  });

  it('handles project directories containing spaces in folder names', async () => {
    const mockOpen = vi.spyOn(api, 'openLocalRepository').mockResolvedValue({
      data: {
        id: 'repo_local_spaces',
        name: 'My Special Project',
        language: 'python',
        test_framework: 'pytest',
        file_count: 3,
        is_fixture: false,
        execution_allowed: true,
        layout_status: 'supported',
        created_at: '2026-10-16T00:00:00Z',
      },
    } as any);

    const service = new ProjectAccessService();
    const repo = await service.registerLocalPath('C:\\Work\\My Special Project', 'My Special Project');

    expect(mockOpen).toHaveBeenCalledWith('C:\\Work\\My Special Project', 'My Special Project');
    expect(repo.name).toBe('My Special Project');
    mockOpen.mockRestore();
  });

  it('handles desktop folder selection cancellation cleanly without errors', async () => {
    const mockOpen = vi.fn().mockResolvedValue({ canceled: true, path: null });
    (globalThis as any).window = { desktopApi: { openDirectory: mockOpen, isDesktop: true } };

    const adapter = new DesktopProjectAdapter();
    const res = await adapter.selectDirectory();

    expect(res.canceled).toBe(true);
    expect(res.path).toBeNull();
    delete (globalThis as any).window;
  });

  it('detects multiple programming languages across project files', () => {
    const testPaths = [
      'src/backend/app.py',
      'src/frontend/App.tsx',
      'src/frontend/index.ts',
      'scripts/build.js',
      'backend/service/Main.java',
      'config/settings.json',
      'README.md',
    ];

    const detected = new Set<string>();
    for (const p of testPaths) {
      const lang = detectLanguageFromExtension(p);
      if (lang) detected.add(lang);
    }

    expect(detected.has('Python')).toBe(true);
    expect(detected.has('TypeScript')).toBe(true);
    expect(detected.has('JavaScript')).toBe(true);
    expect(detected.has('Java')).toBe(true);
    expect(detected.has('Configuration')).toBe(true);
  });

  it('excludes nested paths containing node_modules, .git, and .venv', () => {
    const isExcludedRelPath = (relPath: string): boolean => {
      const parts = relPath.replace(/\\/g, '/').split('/');
      const fileName = parts[parts.length - 1];
      if (isSecretFile(fileName) || isBinaryFile(fileName)) return true;
      return parts.slice(0, -1).some((p) => p === 'node_modules' || p === '.git' || p === '.venv' || p.startsWith('.'));
    };

    expect(isExcludedRelPath('node_modules/lodash/index.js')).toBe(true);
    expect(isExcludedRelPath('.git/HEAD')).toBe(true);
    expect(isExcludedRelPath('.venv/lib/site-packages/pkg.py')).toBe(true);
    expect(isExcludedRelPath('.github/workflows/ci.yml')).toBe(true);
    expect(isExcludedRelPath('src/.cache/data.json')).toBe(true);
    expect(isExcludedRelPath('src/components/.env')).toBe(true);

    // Valid nested source files must NOT be excluded
    expect(isExcludedRelPath('src/components/Button.tsx')).toBe(false);
    expect(isExcludedRelPath('calculator/math_ops.py')).toBe(false);
    expect(isExcludedRelPath('src/main/java/App.java')).toBe(false);
  });
});

