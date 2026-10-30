export interface APIError {
  error: {
    code: string;
    message: string;
    details: Record<string, any>;
    timestamp: string;
  };
}

import { Repository } from './domain';

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  environment: {
    python_version: string;
    sandbox_backend: string;
    docker_cli_available: boolean;
    docker_daemon_responsive: boolean;
    sandbox_image_available: boolean;
    restricted_mode: boolean;
    active_model: string;
    database_connected: boolean;
  };
}

export interface ProviderStatusResponse {
  configured: boolean;
  source: 'session_header' | 'environment_variable' | 'none';
  model: string;
  connection_valid: boolean;
  available_models?: string[];
  error_message?: string | null;
  privacy_notice: string;
}

export interface ValidateSessionKeyResponse {
  valid: boolean;
  model_available?: string;
  message: string;
}

export interface RepositoriesResponse {
  items: Repository[];
  total: number;
}

export interface RepositoryResponse extends Repository {}

export interface RepositoryFilesResponse {
  repository_id: string;
  files: string[];
}

// Repair-related types are in domain.ts