import React, { useState, useEffect, useCallback } from 'react';
import { SessionKeyProvider, useSessionKeyContext } from './context/SessionKeyContext';
import { useSessionKey } from './hooks/useSessionKey';
import { useRepairPolling } from './hooks/useRepairPolling';
import { Navbar } from './components/Navbar';
import { GeminiKeyModal } from './components/GeminiKeyModal';
import { RepositorySelector } from './components/RepositorySelector';
import { BugReportForm } from './components/BugReportForm';
import { RepairTimeline } from './components/RepairTimeline';
import { DiffViewer } from './components/DiffViewer';
import { TestOutputConsole } from './components/TestOutputConsole';
import { FinalReportView } from './components/FinalReportView';
import { Button } from './components/Common/Button';
import { Badge } from './components/Common/Badge';
import { SourceExplorer } from './components/SourceExplorer';
import { AutonomousFindingsView } from './components/AutonomousFindingsView';
import { api } from './api/client';
import { RepairStatus, Repository } from './types/domain';
import { AlertCircle, Shield, AlertTriangle, FileText, FileCode } from 'lucide-react';

import { extractTestTarget } from './utils/testTargetUtils';

function AppContent() {
  const [step, setStep] = useState<'welcome' | 'setup' | 'repo-select' | 'autonomous-findings' | 'bug-report' | 'repair' | 'result'>('welcome');
  const [repositoryId, setRepositoryId] = useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [isSourceExplorerOpen, setIsSourceExplorerOpen] = useState<boolean>(false);
  const [bugReport, setBugReport] = useState<string>('');
  const [testTarget, setTestTargetState] = useState<string>('');

  const setTestTarget = useCallback((target: any) => {
    const clean = extractTestTarget(target);
    setTestTargetState(clean || (typeof target === 'string' && target !== '[object Object]' && target !== 'undefined' && target !== 'null' ? target : ''));
  }, []);

  const [repairId, setRepairId] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  
  const { 
    sessionKey, 
    setSessionKey, 
    selectedModel, 
    setSelectedModel, 
    availableModels,
    isLiveDiscovered,
    discoverModels,
    connectionValid, 
    testConnection, 
    clearSessionKey,
    error: sessionKeyError 
  } = useSessionKey();
  const { repairData, events, diff, hasDiff, isPolling, error: pollingError } = useRepairPolling(repairId);
  
  // Handle polling errors
  useEffect(() => {
    if (pollingError) {
      setError(pollingError);
    }
  }, [pollingError]);

  // Load repository details when repositoryId changes
  useEffect(() => {
    if (repositoryId) {
      api.getRepository(repositoryId)
        .then((res) => setSelectedRepo(res.data))
        .catch(() => setSelectedRepo(null));
    } else {
      setSelectedRepo(null);
    }
  }, [repositoryId]);
  
  // Fetch report when repair is complete (Fix B & C)
  const fetchReport = useCallback(async () => {
    if (!repairId) return;
    
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.getReport(repairId);
      // Fix B: API response payload is in response.data
      setReport(response.data);
      setStep('result');
    } catch (err: any) {
      console.error('Failed to fetch report:', err);
      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.error?.message ||
        (typeof err?.response?.data?.detail === 'string' ? err?.response?.data?.detail : null) ||
        err?.message ||
        'Failed to fetch report';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [repairId]);
  
  // Handle starting a repair
  const handleStartRepair = useCallback(async () => {
    if (!repositoryId || !bugReport) {
      setError('Please select a repository and enter a bug report');
      return;
    }
    if (isLoading) return;
    
    try {
      setIsLoading(true);
      setError(null);
      const cleanTarget = extractTestTarget(testTarget);
      const payload: any = {
        repository_id: repositoryId,
        bug_report: bugReport.trim(),
      };
      if (cleanTarget) {
        payload.test_target = cleanTarget;
      }
      if (selectedModel && selectedModel.trim()) {
        payload.model = selectedModel.trim();
      }

      const response = await api.startRepair(payload, sessionKey || undefined);
      setRepairId(response.data.id);
      setStep('repair');
    } catch (err: any) {
      const errorObj = err?.response?.data?.error || err?.response?.data?.detail;
      let msg =
        errorObj?.message ||
        err?.response?.data?.error?.message ||
        err?.response?.data?.detail?.message ||
        (typeof errorObj === 'string' ? errorObj : null) ||
        err?.message ||
        'Failed to start repair';

      if (errorObj?.details?.errors && Array.isArray(errorObj.details.errors)) {
        const fieldErrors = errorObj.details.errors
          .map((e: any) => `${e.field || e.loc?.slice(1)?.join('.') || 'field'}: ${e.message || e.msg}`)
          .join(', ');
        if (fieldErrors && !msg.includes(fieldErrors)) {
          msg = `Validation failed: ${fieldErrors}`;
        }
      }
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [repositoryId, bugReport, testTarget, sessionKey, isLoading]);
  
  // Handle testing the Gemini connection
  const handleTestConnection = useCallback(async (modelToTest?: string, keyToTest?: string) => {
    try {
      setIsLoading(true);
      await testConnection(modelToTest, keyToTest);
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.error?.message ||
        (typeof err?.response?.data?.detail === 'string' ? err?.response?.data?.detail : null) ||
        err?.message ||
        'Connection test failed';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [testConnection]);
  
  // Handle canceling a repair
  const handleCancelRepair = useCallback(async () => {
    if (!repairId || isLoading) return;
    
    try {
      setIsLoading(true);
      await api.cancelRepair(repairId);
      // The polling will detect the cancelled state and stop
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.error?.message ||
        (typeof err?.response?.data?.detail === 'string' ? err?.response?.data?.detail : null) ||
        err?.message ||
        'Failed to cancel repair';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [repairId, isLoading]);
  
  // Handle retrying a repair
  const handleRetryRepair = useCallback(() => {
    setStep('welcome');
    setRepositoryId(null);
    setSelectedRepo(null);
    setBugReport('');
    setTestTarget('');
    setRepairId(null);
    setReport(null);
    setError(null);
  }, []);
  
  // Handle going back from setup to welcome
  const handleBackToWelcome = useCallback(() => {
    setStep('welcome');
    clearSessionKey();
  }, [clearSessionKey]);

  // Welcome step
  if (step === 'welcome') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-blue-400 mb-4 flex items-center justify-center gap-2">
            <Shield className="h-10 w-10" />
            PatchPilot
          </h1>
          <p className="text-xl text-charcoal-300 mb-6 max-w-md">
            From bug report to tested, reviewable repair — in one controlled workflow.
          </p>
          <button 
            onClick={() => setStep(sessionKey && connectionValid ? 'repo-select' : 'setup')}
            className="btn-primary"
          >
            Start Repair
          </button>
        </div>
      </div>
    );
  }
  
  // Setup step (Gemini API configuration)
  if (step === 'setup') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8">
        <div className="w-full max-w-md">
          <h1 className="text-2xl font-bold text-blue-400 mb-6 flex items-center gap-2">
            <AlertCircle className="h-6 w-6" />
            Gemini API Setup
          </h1>
          <GeminiKeyModal 
            sessionKey={sessionKey}
            setSessionKey={setSessionKey}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            availableModels={availableModels}
            isLiveDiscovered={isLiveDiscovered}
            onDiscoverModels={discoverModels}
            connectionValid={connectionValid}
            onTestConnection={handleTestConnection}
            onCancel={handleBackToWelcome}
            onSuccess={() => setStep('repo-select')}
            error={sessionKeyError || error}
            isLoading={isLoading}
          />
        </div>
      </div>
    );
  }
  
  // Repository selection step
  if (step === 'repo-select') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-2xl">
          <RepositorySelector 
            selectedRepositoryId={repositoryId}
            onRepositorySelect={(id: string) => {
              setRepositoryId(id);
              setError(null);
            }}
            onContinue={(id: string) => {
              setRepositoryId(id);
              setError(null);
              setStep('bug-report');
            }}
            onFindBugs={(id: string) => {
              setRepositoryId(id);
              setError(null);
              setStep('autonomous-findings');
            }}
            onBack={() => setStep(sessionKey && connectionValid ? 'setup' : 'welcome')}
            error={error}
          />
        </div>
      </div>
    );
  }

  // Autonomous Bug Discovery step
  if (step === 'autonomous-findings') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4 sm:p-8 bg-charcoal-900">
        <div className="w-full max-w-4xl">
          <AutonomousFindingsView 
            repository={selectedRepo}
            onBack={() => setStep('repo-select')}
            onStartRepairForFinding={(finding) => {
              setBugReport(`${finding.title}\n\nFile: ${finding.file_path}${finding.line_start ? ':' + finding.line_start : ''}\n\nExplanation:\n${finding.explanation}\n\nSuggested Fix:\n${finding.suggested_fix || ''}`);
              const target = extractTestTarget(finding.test_evidence);
              setTestTarget(target || '');
              setStep('bug-report');
            }}
            onCandidateRepairReady={(cid) => {
              setRepairId(cid);
              setStep('repair');
            }}
            onDiscoverBugs={async (opts) => {
              if (!repositoryId) throw new Error("No repository selected");
              const res = await api.discoverBugs(repositoryId, opts);
              return res.data;
            }}
          />
        </div>
        <SourceExplorer 
          repository={selectedRepo}
          isOpen={isSourceExplorerOpen}
          onClose={() => setIsSourceExplorerOpen(false)}
        />
      </div>
    );
  }
  
  // Bug report step
  if (step === 'bug-report') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-bold text-blue-400 flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Repair Specification
            </h1>
            {selectedRepo && (
              <button
                type="button"
                onClick={() => setIsSourceExplorerOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-200 hover:text-white border border-charcoal-700 transition-colors"
                title="Open Source Explorer"
              >
                <FileCode className="h-3.5 w-3.5 text-blue-400" />
                <span>Explore Source Code</span>
              </button>
            )}
          </div>
          <BugReportForm 
            repositoryId={repositoryId || ''}
            repository={selectedRepo}
            bugReport={bugReport}
            setBugReport={setBugReport}
            testTarget={testTarget}
            setTestTarget={setTestTarget}
            onBack={() => setStep('repo-select')}
            onStartRepair={handleStartRepair}
            error={error}
            isLoading={isLoading}
          />
        </div>
        <SourceExplorer 
          repository={selectedRepo}
          isOpen={isSourceExplorerOpen}
          onClose={() => setIsSourceExplorerOpen(false)}
        />
      </div>
    );
  }
  
  // Repair step
  if (step === 'repair') {
    const restrictedMode = repairData?.restricted_mode === true;
    const isTerminal = ['verified', 'unresolved', 'failed', 'cancelled'].includes(repairData?.status || '');
    
    return (
      <div className="min-h-screen flex flex-col overflow-hidden p-4 bg-charcoal-900">
        {restrictedMode && (
          <div className="mb-4 p-3 bg-yellow-600/20 border border-yellow-600/50 rounded-lg flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-400 flex-shrink-0" />
            <div className="text-sm text-yellow-300">
              <strong>Restricted Demonstration Mode Active</strong> — Process running on host without container jail. 
              Execution restricted to trusted local fixtures only.
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-600/20 border border-red-600/50 rounded-lg flex items-center justify-between gap-2 text-sm text-red-400">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <button 
              onClick={() => setError(null)} 
              className="text-xs underline hover:text-red-300"
            >
              Dismiss
            </button>
          </div>
        )}

        <Navbar 
          repositoryId={repositoryId} 
          bugReport={bugReport} 
          testTarget={testTarget} 
          onCancel={handleCancelRepair}
          status={repairData?.status}
          onViewReport={fetchReport}
          isLoadingReport={isLoading}
        />

        {isTerminal && (
          <div className="my-4 p-4 bg-charcoal-800 border border-charcoal-700 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-4 shadow-lg">
            <div className="flex items-center gap-3">
              <Badge variant={repairData?.status as any} className="text-sm px-3 py-1 uppercase font-semibold">
                {repairData?.status}
              </Badge>
              <div>
                <p className="text-sm font-medium text-charcoal-100">
                  {repairData?.status === 'verified' ? 'Repair successfully verified!' :
                   repairData?.status === 'unresolved' ? 'Repair concluded without full verification.' :
                   repairData?.status === 'failed' ? 'Repair failed.' : 'Repair was cancelled.'}
                </p>
                <p className="text-xs text-charcoal-400">
                  {repairData?.status === 'verified' ? 'Deterministic baseline reproduced and all test suites passed.' :
                   repairData?.status === 'unresolved' ? 'Baseline or regression checks did not pass within budget.' :
                   repairData?.status === 'failed' ? (repairData?.error_message || 'The repair job encountered an unrecoverable failure.') :
                   'Ephemeral workspace cleaned up.'}
                </p>
              </div>
            </div>
            <Button 
              variant="primary" 
              onClick={fetchReport} 
              disabled={isLoading}
              className="flex-shrink-0"
            >
              <FileText className="h-4 w-4 mr-1" />
              {isLoading ? 'Loading Report...' : 'Open Final Report'}
            </Button>
          </div>
        )}

        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="flex h-full gap-4 flex-1">
            {/* Left panel: Timeline and controls */}
            <div className="w-64 flex flex-col gap-4 flex-shrink-0">
              <RepairTimeline 
                repairData={repairData} 
                events={events} 
              />
            </div>
            
            {/* Right panel: Main content */}
            <div className="flex-1 flex flex-col gap-4 min-w-0">
              {/* Diff viewer */}
              <div className="flex-1 min-h-0">
                <DiffViewer 
                  diff={diff} 
                  hasDiff={hasDiff} 
                />
              </div>
              
              {/* Test output console */}
              <div className="h-96 flex-shrink-0">
                <TestOutputConsole 
                  repairData={repairData} 
                  events={events}
                />
              </div>
            </div>
          </div>
        </div>
        <SourceExplorer 
          repository={selectedRepo}
          isOpen={isSourceExplorerOpen}
          onClose={() => setIsSourceExplorerOpen(false)}
        />
      </div>
    );
  }
  
  // Result step
  if (step === 'result') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8 bg-charcoal-900">
        <div className="w-full max-w-4xl">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold text-blue-400 flex items-center gap-2">
              <Shield className="h-6 w-6" />
              Repair Report
            </h1>
            {selectedRepo && (
              <button
                type="button"
                onClick={() => setIsSourceExplorerOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-200 hover:text-white border border-charcoal-700 transition-colors"
                title="Open Source Explorer"
              >
                <FileCode className="h-3.5 w-3.5 text-blue-400" />
                <span>Explore Source Code</span>
              </button>
            )}
          </div>
          <FinalReportView 
            report={report} 
            onRetry={handleRetryRepair}
            onClose={() => setStep('repair')}
            repairId={repairId}
          />
        </div>
        <SourceExplorer 
          repository={selectedRepo}
          isOpen={isSourceExplorerOpen}
          onClose={() => setIsSourceExplorerOpen(false)}
        />
      </div>
    );
  }
  
  // Fallback
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-blue-400">PatchPilot</h1>
        <p className="text-charcoal-300">Loading...</p>
      </div>
    </div>
  );
}

const App = () => {
  return (
    <SessionKeyProvider>
      <AppContent />
    </SessionKeyProvider>
  );
};

export default App;