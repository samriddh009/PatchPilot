/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface DesktopApi {
  isDesktop: boolean;
  openDirectory: () => Promise<{ canceled: boolean; path: string | null }>;
  getApiBaseUrl?: () => Promise<string>;
  openLocalRepository?: (path: string, name?: string) => Promise<any>;
}

interface Window {
  desktopApi?: DesktopApi;
}