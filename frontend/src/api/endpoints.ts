import { api } from './client';
export type { AxiosInstance } from 'axios';

// Re-export for convenience
export const {
  getHealth,
  getProviderStatus,
  getModels,
  discoverModels,
  setModel,
  validateSessionKey,
  getRepositories,
  getRepository,
  getRepositoryFiles,
  startRepair,
  getRepair,
  getEvents,
  getDiff,
  cancelRepair,
  getReport,
  openLocalRepository,
  ingestRepository,
  browseLocalFolder,
  getRepositoryFile,
  proposeTest,
  discoverBugs,
  exportRepair,
  rejectRepair,
} = api;

export { api };