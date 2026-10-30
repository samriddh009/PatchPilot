import axios from 'axios';

let sessionKeyGetter: () => string | null = () => null;

export const setSessionKeyGetter = (getter: () => string | null) => {
  sessionKeyGetter = getter;
};

// Create an axios instance with default configuration
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add the session key header
apiClient.interceptors.request.use((config) => {
  const sessionKey = sessionKeyGetter();
  if (sessionKey) {
    config.headers['X-Session-Gemini-Key'] = sessionKey;
  }
  return config;
});

// Response interceptor to handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Let the calling code handle the error
    return Promise.reject(error);
  }
);

// In Electron desktop environment, query backend port dynamically if available
if (typeof window !== 'undefined' && window.desktopApi?.getApiBaseUrl) {
  window.desktopApi.getApiBaseUrl().then((url) => {
    if (url) {
      apiClient.defaults.baseURL = `${url}/api/v1`;
    }
  }).catch(() => {});
}

export const api = {
  // Health endpoint
  getHealth: () => apiClient.get('/health'),
  
  // Provider endpoints
  getProviderStatus: () => apiClient.get('/provider/status'),
  getModels: () => apiClient.get('/provider/models'),
  discoverModels: (apiKey?: string) => apiClient.post('/provider/models', { api_key: apiKey }),
  setModel: (model: string) => apiClient.post('/provider/model', { model }),
  validateSessionKey: (apiKey: string, model?: string) => 
    apiClient.post('/provider/session-key', { api_key: apiKey, model }),
  
  // Repository endpoints
  getRepositories: () => apiClient.get('/repositories'),
  getRepository: (id: string) => apiClient.get(`/repositories/${id}`),
  getRepositoryFiles: (id: string, includeTests: boolean = true) => 
    apiClient.get(`/repositories/${id}/files`, { params: { include_tests: includeTests } }),
  openLocalRepository: (path: string, name?: string) =>
    apiClient.post('/repositories/open-local', { path, name }),
  ingestRepository: (payload: { name: string; files: Array<{ path: string; content: string }> }) =>
    apiClient.post('/repositories/ingest', payload),
  browseLocalFolder: () => apiClient.post('/repositories/browse-folder'),
  getRepositoryFile: (id: string, path: string, offsetLine: number = 1, limitLines: number = 500) =>
    apiClient.get(`/repositories/${id}/file`, { params: { path, offset_line: offsetLine, limit_lines: limitLines } }),
  proposeTest: (id: string, bugReport: string, targetFile?: string, sessionKey?: string) =>
    apiClient.post(`/repositories/${id}/propose-test`, { bug_report: bugReport, target_file: targetFile }, {
      headers: sessionKey ? { 'X-Session-Gemini-Key': sessionKey } : {}
    }),
  discoverBugs: (id: string, payload: any = {}) =>
    apiClient.post(`/repositories/${id}/discover-bugs`, payload),
  
  // Repair endpoints
  startRepair: (data: any, sessionKey?: string) => 
    apiClient.post('/repairs', data, {
      headers: sessionKey ? { 'X-Session-Gemini-Key': sessionKey } : {}
    }),
  getRepair: (id: string) => apiClient.get(`/repairs/${id}`),
  getEvents: (id: string, sinceSeq: number = 0, limit: number = 50) => 
    apiClient.get(`/repairs/${id}/events`, { 
      params: { since_seq: sinceSeq, limit } 
    }),
  getDiff: (id: string) => apiClient.get(`/repairs/${id}/diff`),
  cancelRepair: (id: string) => apiClient.post(`/repairs/${id}/cancel`),
  getReport: (id: string) => apiClient.get(`/repairs/${id}/report`),
  exportRepair: (id: string) => apiClient.post(`/repairs/${id}/export`),
  rejectRepair: (id: string) => apiClient.post(`/repairs/${id}/reject`),
};

export default apiClient;