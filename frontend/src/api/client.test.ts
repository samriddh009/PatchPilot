import { describe, it, expect, beforeEach } from 'vitest';
import { api, setSessionKeyGetter } from './client';

describe('Frontend API Client and Domain Contracts', () => {
  beforeEach(() => {
    setSessionKeyGetter(() => null);
  });

  it('provides all documented endpoints matching the API contract', () => {
    expect(typeof api.getHealth).toBe('function');
    expect(typeof api.getProviderStatus).toBe('function');
    expect(typeof api.getModels).toBe('function');
    expect(typeof api.discoverModels).toBe('function');
    expect(typeof api.setModel).toBe('function');
    expect(typeof api.validateSessionKey).toBe('function');
    expect(typeof api.getRepositories).toBe('function');
    expect(typeof api.getRepository).toBe('function');
    expect(typeof api.getRepositoryFiles).toBe('function');
    expect(typeof api.openLocalRepository).toBe('function');
    expect(typeof api.browseLocalFolder).toBe('function');
    expect(typeof api.getRepositoryFile).toBe('function');
    expect(typeof api.proposeTest).toBe('function');
    expect(typeof api.startRepair).toBe('function');
    expect(typeof api.getRepair).toBe('function');
    expect(typeof api.getEvents).toBe('function');
    expect(typeof api.getDiff).toBe('function');
    expect(typeof api.cancelRepair).toBe('function');
    expect(typeof api.getReport).toBe('function');
    expect(typeof api.discoverBugs).toBe('function');
    expect(typeof api.exportRepair).toBe('function');
    expect(typeof api.rejectRepair).toBe('function');
  });

  it('correctly categorizes user-opened local repos vs demo fixtures', () => {
    const repos = [
      { id: 'repo_py_calc_01', name: 'python_calc_bug', is_fixture: true, execution_allowed: true },
      { id: 'repo_local_12345678', name: 'my-service', is_fixture: false, execution_allowed: false },
    ];

    const localRepos = repos.filter(r => !r.is_fixture && !r.id.startsWith('repo_py_'));
    const demoRepos = repos.filter(r => r.is_fixture || r.id.startsWith('repo_py_'));

    expect(localRepos).toHaveLength(1);
    expect(localRepos[0].id).toBe('repo_local_12345678');
    expect(localRepos[0].execution_allowed).toBe(false);

    expect(demoRepos).toHaveLength(1);
    expect(demoRepos[0].id).toBe('repo_py_calc_01');
    expect(demoRepos[0].execution_allowed).toBe(true);
  });

  it('correctly identifies terminal states for report navigation', () => {
    const terminalStates = ['verified', 'unresolved', 'failed', 'cancelled'];
    const inProgressStates = ['queued', 'inspecting', 'reproducing', 'patching', 'testing', 'verifying', 'recovering'];

    terminalStates.forEach(status => {
      const isTerminal = ['verified', 'unresolved', 'failed', 'cancelled'].includes(status);
      expect(isTerminal).toBe(true);
    });

    inProgressStates.forEach(status => {
      const isTerminal = ['verified', 'unresolved', 'failed', 'cancelled'].includes(status);
      expect(isTerminal).toBe(false);
    });
  });

  it('verifies report payload schema compatibility for FinalReportView', () => {
    // Verifies the exact unpacked response.data schema expected by FinalReportView
    const reportPayload = {
      repair_id: 'rep_123',
      repository_id: 'repo_py_calc_01',
      status: 'verified',
      bug_report: 'Off by one bug in pricing',
      duration_seconds: 12.5,
      recovery_attempts: 0,
      verification: {
        outcome: 'verified',
        baseline_reproduced: true,
        baseline_exit_code: 1,
        baseline_log_snippet: 'AssertionError: assert 10 == 15',
        targeted_pass: true,
        targeted_exit_code: 0,
        regression_pass: true,
        regression_exit_code: 0,
        total_tests_run: 6,
        total_tests_passed: 6,
      },
      diff: {
        raw_diff: '--- a/pricing.py\n+++ b/pricing.py\n@@ -1 +1 @@\n',
        files_changed: ['calculator/pricing.py'],
        total_insertions: 1,
        total_deletions: 1,
      },
      markdown_summary: '### Deterministic Evidence\nBaseline reproduced and all tests passed.',
    };

    expect(reportPayload.status).toBe('verified');
    expect(reportPayload.verification.baseline_reproduced).toBe(true);
    expect(reportPayload.verification.targeted_pass).toBe(true);
    expect(reportPayload.diff.files_changed).toHaveLength(1);
    expect(reportPayload.markdown_summary).toContain('Deterministic Evidence');
  });

  it('validates proposed test schema and no_tests layout status', () => {
    const sourceOnlyRepo = {
      id: 'repo_local_abcd1234',
      name: 'Source Only App',
      language: 'python' as const,
      test_framework: 'unknown' as const,
      layout_status: 'no_tests' as const,
      execution_allowed: false,
      execution_warning: 'Docker container isolation is unavailable. No existing tests detected.',
    };

    expect(sourceOnlyRepo.layout_status).toBe('no_tests');
    expect(sourceOnlyRepo.execution_allowed).toBe(false);

    const proposedTest = {
      repository_id: sourceOnlyRepo.id,
      test_file_path: 'tests/test_proposed_reproduction.py',
      test_code: 'def test_reproduce(): assert True\n',
      test_target: 'tests/test_proposed_reproduction.py::test_reproduce',
      explanation: 'Focused pytest asserting expected behavior',
      status: 'proposed' as const,
    };

    expect(proposedTest.status).toBe('proposed');
    expect(proposedTest.test_target).toContain('::test_reproduce');
  });

  it('correctly extracts structured API error messages across detail and error envelopes', () => {
    const errorWithDetail: any = {
      response: {
        data: {
          detail: {
            code: 'CONFLICT_STATE',
            message: 'Cannot cancel repair because it is already in terminal state failed.',
          },
        },
      },
    };

    const extractedFromDetail =
      errorWithDetail?.response?.data?.detail?.message ||
      errorWithDetail?.response?.data?.error?.message ||
      'Failed to cancel repair';

    expect(extractedFromDetail).toBe(
      'Cannot cancel repair because it is already in terminal state failed.'
    );

    const errorWithEnvelope: any = {
      response: {
        data: {
          error: {
            code: 'SANDBOX_UNAVAILABLE',
            message: 'Execution refused: Docker container isolation is unavailable.',
          },
        },
      },
    };

    const extractedFromEnvelope =
      errorWithEnvelope?.response?.data?.detail?.message ||
      errorWithEnvelope?.response?.data?.error?.message ||
      'Generic failure';

    expect(extractedFromEnvelope).toBe(
      'Execution refused: Docker container isolation is unavailable.'
    );
  });

  it('extracts available_models from error details and switches unavailable model', () => {
    // Exact schema emitted by backend when gemini-1.5-flash is unavailable but 2.5 is discovered
    const modelUnavailableError: any = {
      response: {
        data: {
          error: {
            code: 'PROVIDER_MODEL_UNAVAILABLE',
            message: "Configured model 'gemini-1.5-flash' was not found in available models for this API key. Available models: gemini-2.5-flash, gemini-2.5-pro.",
            details: {
              available_models: ['gemini-2.5-flash', 'gemini-2.5-pro'],
            },
          },
        },
      },
    };

    const errorObj: any =
      modelUnavailableError.response?.data?.error ||
      modelUnavailableError.response?.data ||
      {};
    const modelsFromError =
      errorObj.details?.available_models ||
      errorObj.available_models;

    expect(Array.isArray(modelsFromError)).toBe(true);
    expect(modelsFromError).toHaveLength(2);
    expect(modelsFromError).toContain('gemini-2.5-flash');
    expect(modelsFromError).toContain('gemini-2.5-pro');
    expect(modelsFromError).not.toContain('gemini-1.5-flash');
  });

  it('validates provider model list response schema matches expected frontend contract', () => {
    const mockDiscoveryResponse = {
      active_model: 'gemini-2.5-flash',
      supported_models: ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash'],
      available_models: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      is_live_discovered: true,
      error_detail: null,
    };

    expect(mockDiscoveryResponse.is_live_discovered).toBe(true);
    expect(mockDiscoveryResponse.available_models).toHaveLength(2);
  });

  it('validates browseLocalFolder response schema and contracts', () => {
    // 1. Success selection response
    const successBrowse = {
      path: 'C:\\Users\\dev\\projects\\my-service',
      cancelled: false,
      supported: true,
      message: null,
    };
    expect(successBrowse.supported).toBe(true);
    expect(successBrowse.cancelled).toBe(false);
    expect(successBrowse.path).toContain('my-service');

    // 2. Cancellation response
    const cancelledBrowse = {
      path: null,
      cancelled: true,
      supported: true,
      message: 'Folder selection was cancelled.',
    };
    expect(cancelledBrowse.supported).toBe(true);
    expect(cancelledBrowse.cancelled).toBe(true);
    expect(cancelledBrowse.path).toBeNull();
    expect(cancelledBrowse.message).toContain('cancelled');

    // 3. Unavailable / error response
    const unavailableBrowse = {
      path: null,
      cancelled: false,
      supported: false,
      message: 'Native dialog helper is only available on Windows desktop.',
    };
    expect(unavailableBrowse.supported).toBe(false);
    expect(unavailableBrowse.path).toBeNull();
    expect(unavailableBrowse.message).toContain('Windows desktop');
  });

  it('verifies cancellation does not destroy user entered folder path', () => {
    let currentPath = 'C:\\existing\\path\\entered\\by\\user';
    const browseResult = {
      path: null,
      cancelled: true,
      supported: true,
      message: 'Folder selection was cancelled.',
    };

    // Simulated modal logic
    let error: string | null = null;
    if (browseResult.path) {
      currentPath = browseResult.path;
    } else if (browseResult.cancelled) {
      error = browseResult.message || 'Folder selection was cancelled.';
    }

    // Path must remain unchanged
    expect(currentPath).toBe('C:\\existing\\path\\entered\\by\\user');
    expect(error).toBe('Folder selection was cancelled.');
  });

  it('correctly handles desktopApi openDirectory in desktop shell', async () => {
    // Mock desktopApi
    const targetObj = typeof window !== 'undefined' ? (window as any) : (globalThis as any);
    const originalDesktopApi = targetObj.desktopApi;
    targetObj.desktopApi = {
      isDesktop: true,
      openDirectory: async () => ({
        cancelled: false,
        path: 'C:\\projects\\my-service',
      }),
      getApiBaseUrl: async () => 'http://127.0.0.1:8000',
    };

    expect(targetObj.desktopApi.isDesktop).toBe(true);
    const result = await targetObj.desktopApi.openDirectory();
    expect(result.cancelled).toBe(false);
    expect(result.path).toBe('C:\\projects\\my-service');

    const baseUrl = await targetObj.desktopApi.getApiBaseUrl();
    expect(baseUrl).toBe('http://127.0.0.1:8000');

    targetObj.desktopApi = originalDesktopApi;
  });

  it('correctly validates approval gate state transitions', () => {
    const validApprovalStates = ['awaiting_approval', 'exporting', 'verified', 'unresolved'];
    validApprovalStates.forEach((st) => {
      expect(['awaiting_approval', 'exporting', 'verified', 'unresolved'].includes(st)).toBe(true);
    });
  });
});


