import React, { useState, useRef } from 'react';
import { Button } from './Common/Button';
import { Badge } from './Common/Badge';
import { 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  FileCode, 
  Clock, 
  RotateCcw, 
  Terminal, 
  ChevronLeft,
  Shield,
  CheckCheck,
  TestTube,
  UploadCloud,
  Ban,
  Eye,
  FileCheck,
  Loader2,
  AlertTriangle
} from 'lucide-react';
import { api } from '../api/client';

interface FinalReportViewProps {
  report: any;
  onRetry: () => void;
  onClose: () => void;
  repairId?: string | null;
}

type BadgeVariant = 'verified' | 'unresolved' | 'failed' | 'cancelled' | 'inspecting' | 'reproducing' | 'patching' | 'testing' | 'verifying' | 'recovering' | 'queued' | 'awaiting_approval' | 'exporting';

export const FinalReportView = ({ report, onRetry, onClose, repairId }: FinalReportViewProps) => {
  const [exportState, setExportState] = useState<'idle' | 'exporting' | 'exported' | 'rejected' | 'error'>('idle');
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportedFiles, setExportedFiles] = useState<string[]>([]);
  const codeChangesRef = useRef<HTMLDivElement>(null);

  if (!report) {
    return (
      <div className="text-center py-8">
        <FileCode className="h-12 w-12 text-charcoal-600 mx-auto mb-3" />
        <p className="text-charcoal-400">No report available.</p>
      </div>
    );
  }

  const { status, verification, diff, markdown_summary, duration_seconds, recovery_attempts } = report;
  const currentRepairId = repairId || report.repair_id;

  const handleApproveAndExport = async () => {
    if (!currentRepairId) {
      setExportState('error');
      setExportMessage('Repair ID is missing.');
      return;
    }

    try {
      setExportState('exporting');
      setExportMessage(null);
      const res = await api.exportRepair(currentRepairId);
      setExportState('exported');
      setExportedFiles(res.data.files_written || diff?.files_changed || []);
      setExportMessage('Changes successfully verified and exported to the original repository.');
    } catch (err: any) {
      setExportState('error');
      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.error?.message ||
        err?.message ||
        'Failed to export changes to repository';
      setExportMessage(msg);
    }
  };

  const handleRejectChanges = async () => {
    if (!currentRepairId) return;

    try {
      setExportState('exporting');
      await api.rejectRepair(currentRepairId);
      setExportState('rejected');
      setExportMessage('Candidate changes rejected. The original repository remains completely unmodified.');
    } catch (err: any) {
      setExportState('error');
      setExportMessage(err?.message || 'Failed to reject changes');
    }
  };

  const handleReviewDiff = () => {
    if (codeChangesRef.current) {
      codeChangesRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };
  
  // Determine status badge variant and icon
  let badgeVariant: BadgeVariant = 'queued';
  let statusIcon: React.ReactNode = <Shield className="h-4 w-4" />;
  let statusColor: string = 'text-charcoal-400';
  
  if (status === 'verified') {
    badgeVariant = 'verified';
    statusIcon = <CheckCircle className="h-4 w-4" />;
    statusColor = 'text-green-400';
  } else if (status === 'awaiting_approval') {
    badgeVariant = 'awaiting_approval';
    statusIcon = <CheckCircle className="h-4 w-4" />;
    statusColor = 'text-blue-400';
  } else if (status === 'unresolved') {
    badgeVariant = 'unresolved';
    statusIcon = <AlertCircle className="h-4 w-4" />;
    statusColor = 'text-yellow-400';
  } else if (status === 'failed') {
    badgeVariant = 'failed';
    statusIcon = <XCircle className="h-4 w-4" />;
    statusColor = 'text-red-400';
  } else if (status === 'cancelled') {
    badgeVariant = 'cancelled';
    statusIcon = <XCircle className="h-4 w-4" />;
    statusColor = 'text-gray-400';
  }

  const hasCandidateDiff = !!(diff?.raw_diff && diff.raw_diff.trim().length > 0);
  const isCandidateEligibleForExport = (status === 'verified' || status === 'awaiting_approval') && hasCandidateDiff;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${statusColor.replace('text-', 'bg-')}/20`}>
            {statusIcon}
          </div>
          <div>
            <h2 className="text-xl font-bold text-charcoal-50">Repair Report</h2>
            <p className="text-sm text-charcoal-400">Completed in {duration_seconds}s</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={badgeVariant} className="text-sm px-3 py-1">
            {status.toUpperCase()}
          </Badge>
        </div>
      </div>

      {/* Explicit Approval Gate UI */}
      {isCandidateEligibleForExport && (
        <div className="p-4 bg-charcoal-800 border-2 border-blue-500/50 rounded-lg space-y-3 shadow-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-blue-400" />
              <h3 className="text-sm font-bold uppercase tracking-wider text-charcoal-100">
                Patch Application Approval Gate
              </h3>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono">
              Original Repo Unchanged
            </span>
          </div>

          <p className="text-xs text-charcoal-300 leading-relaxed">
            Candidate patch has been verified in a disposable workspace. In accordance with safety policy, the original repository remains unchanged until you explicitly approve export.
          </p>

          {exportState === 'exported' && (
            <div className="p-3 bg-emerald-600/15 border border-emerald-600/30 rounded text-xs text-emerald-300 flex items-start gap-2">
              <FileCheck className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-emerald-200">{exportMessage}</p>
                {exportedFiles.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-emerald-300/90">
                    Files modified: {exportedFiles.join(', ')}
                  </p>
                )}
              </div>
            </div>
          )}

          {exportState === 'rejected' && (
            <div className="p-3 bg-charcoal-900 border border-charcoal-700 rounded text-xs text-charcoal-300 flex items-center gap-2">
              <Ban className="h-4 w-4 text-yellow-400 flex-shrink-0" />
              <span>{exportMessage}</span>
            </div>
          )}

          {exportState === 'error' && (
            <div className="p-3 bg-red-600/15 border border-red-600/30 rounded text-xs text-red-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{exportMessage}</span>
            </div>
          )}

          {/* 4 Explicit Action Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-charcoal-700">
            <Button
              variant="primary"
              size="sm"
              onClick={handleApproveAndExport}
              disabled={exportState === 'exporting' || exportState === 'exported'}
            >
              {exportState === 'exporting' ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  Exporting Changes...
                </>
              ) : (
                <>
                  <UploadCloud className="h-4 w-4 mr-1.5" />
                  Approve and Export
                </>
              )}
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleRejectChanges}
              disabled={exportState === 'exporting' || exportState === 'exported' || exportState === 'rejected'}
            >
              <Ban className="h-4 w-4 mr-1.5 text-red-400" />
              Reject Changes
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={handleReviewDiff}
            >
              <Eye className="h-4 w-4 mr-1.5 text-blue-400" />
              Review Diff
            </Button>

            <Button
              variant="secondary"
              size="sm"
              onClick={onClose}
            >
              Keep Report Without Exporting
            </Button>
          </div>
        </div>
      )}
      
      {/* Prominent Failure Root Cause Banner */}
      {status === 'failed' && (
        <div className="p-4 bg-red-950/40 border border-red-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-red-200">Repair Failure Root Cause</h4>
              <p className="text-xs text-red-300 mt-1">
                {markdown_summary?.includes('not found') || markdown_summary?.includes('PROVIDER_MODEL_UNAVAILABLE') ? (
                  <><strong>Model Unavailable:</strong> The configured Gemini model was rejected or not found by Google AI Studio. Please select a supported model such as <code>gemini-1.5-flash</code> or <code>gemini-1.5-pro</code>.</>
                ) : markdown_summary?.includes('PROVIDER_AUTH_FAILED') || markdown_summary?.includes('API key not valid') ? (
                  <><strong>Authentication Failed:</strong> The supplied Gemini API key was rejected by the provider.</>
                ) : markdown_summary?.includes('PROVIDER_QUOTA_EXHAUSTED') || markdown_summary?.includes('quota') ? (
                  <><strong>Quota Exceeded:</strong> Gemini API rate limit or quota reached (15 requests per minute limit on free tier).</>
                ) : markdown_summary?.includes('RUNNER_CRASH') || markdown_summary?.includes('runner_crash') ? (
                  <><strong>Test Runner Crash:</strong> The test runner process crashed or failed to start.</>
                ) : (
                  markdown_summary?.split('\n*')?.[1]?.replace(/\*$/, '') || 'The repair failed before reaching patch verification.'
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="border-t border-charcoal-700 pt-4">
        <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
          <FileCode className="h-5 w-5" />
          Summary & Diagnosis
        </h3>
        <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4">
          <p className="whitespace-pre-wrap text-sm text-charcoal-300 leading-relaxed">
            {markdown_summary}
          </p>
        </div>
      </div>
      
      <div className="border-t border-charcoal-700 pt-4">
        <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
          <CheckCheck className="h-5 w-5" />
          Verification Details
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Baseline */}
          <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Terminal className="h-4 w-4 text-blue-400" />
              <p className="text-xs text-charcoal-400 font-medium">Baseline Reproduced</p>
            </div>
            {verification?.baseline_exit_code !== null && verification?.baseline_exit_code !== undefined ? (
              <div className="flex items-baseline gap-2">
                <p className={`text-2xl font-bold ${verification?.baseline_reproduced ? 'text-green-400' : 'text-red-400'}`}>
                  {verification?.baseline_reproduced ? 'YES' : 'NO'}
                </p>
                <span className="text-xs text-charcoal-500">Exit: {verification?.baseline_exit_code}</span>
              </div>
            ) : (
              <div>
                <p className="text-xl font-bold text-charcoal-400">NOT EXECUTED</p>
                <span className="text-xs text-charcoal-500">Skipped</span>
              </div>
            )}
            {verification?.baseline_log_snippet && (
              <div className="mt-3">
                <p className="text-xs text-charcoal-400 font-medium mb-1">Failure Snippet</p>
                <div className="bg-charcoal-900 border border-charcoal-800 rounded-lg p-2 text-xs font-mono text-green-400">
                  {verification.baseline_log_snippet}
                </div>
              </div>
            )}
          </div>
          
          {/* Targeted Test */}
          <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <TestTube className="h-4 w-4 text-green-400" />
              <p className="text-xs text-charcoal-400 font-medium">Targeted Test</p>
            </div>
            {verification?.targeted_exit_code !== null && verification?.targeted_exit_code !== undefined ? (
              <div className="flex items-baseline gap-2">
                <p className={`text-2xl font-bold ${verification?.targeted_pass ? 'text-green-400' : 'text-red-400'}`}>
                  {verification?.targeted_pass ? 'PASS' : 'FAIL'}
                </p>
                <span className="text-xs text-charcoal-500">Exit: {verification?.targeted_exit_code}</span>
              </div>
            ) : (
              <div>
                <p className="text-xl font-bold text-charcoal-400">NOT EXECUTED</p>
                <span className="text-xs text-charcoal-500">Skipped (stopped early)</span>
              </div>
            )}
          </div>
          
          {/* Regression Suite */}
          <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <TestTube className="h-4 w-4 text-purple-400" />
              <p className="text-xs text-charcoal-400 font-medium">Regression Suite</p>
            </div>
            {verification?.regression_exit_code !== null && verification?.regression_exit_code !== undefined ? (
              <div className="flex items-baseline gap-2">
                <p className={`text-2xl font-bold ${verification?.regression_pass ? 'text-green-400' : 'text-red-400'}`}>
                  {verification?.regression_pass ? 'PASS' : 'FAIL'}
                </p>
                <span className="text-xs text-charcoal-500">Exit: {verification?.regression_exit_code}</span>
              </div>
            ) : (
              <div>
                <p className="text-xl font-bold text-charcoal-400">NOT EXECUTED</p>
                <span className="text-xs text-charcoal-500">Skipped (stopped early)</span>
              </div>
            )}
            <p className="text-xs text-charcoal-400 mt-1">
              Tests Run: {verification?.total_tests_run ?? 0} • Passed: {verification?.total_tests_passed ?? 0}
            </p>
          </div>
          
          {/* Patch Information */}
          <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4 sm:col-span-2 lg:col-span-1">
            <div className="flex items-center gap-2 mb-2">
              <FileCode className="h-4 w-4 text-blue-400" />
              <p className="text-xs text-charcoal-400 font-medium">Patch Information</p>
            </div>
            <p className="text-lg font-bold text-blue-400">
              {(diff?.files_changed || []).length} file{(diff?.files_changed || []).length !== 1 ? 's' : ''} changed
            </p>
            {diff?.total_insertions !== undefined ? (
              <p className="text-xs text-charcoal-400 mt-1">
                {diff.total_insertions} insertions, {diff.total_deletions} deletions
              </p>
            ) : (
              <p className="text-xs text-charcoal-400 mt-1">
                {(diff?.files_changed || []).length} file(s) modified
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-1">
              {(diff?.files_changed || []).map((file: string, i: number) => (
                <span key={i} className="text-xs bg-charcoal-900 text-charcoal-300 px-2 py-0.5 rounded font-mono">
                  {file}
                </span>
              ))}
            </div>
          </div>
          
          {/* Recovery Attempts */}
          <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <RotateCcw className="h-4 w-4 text-yellow-400" />
              <p className="text-xs text-charcoal-400 font-medium">Recovery Attempts</p>
            </div>
            <p className="text-2xl font-bold text-yellow-400">{recovery_attempts ?? 0}</p>
            {(recovery_attempts ?? 0) > 0 && (
              <p className="text-xs text-charcoal-500 mt-1">Bounded recovery executed</p>
            )}
          </div>
        </div>
      </div>

      {/* Known Limitations & Remaining Risks */}
      <div className="border-t border-charcoal-700 pt-4">
        <h3 className="text-sm font-semibold text-charcoal-300 mb-2 flex items-center gap-1.5">
          <AlertTriangle className="h-4 w-4 text-yellow-400" />
          Safety Verification & Remaining Risks
        </h3>
        <div className="p-3 bg-charcoal-800/60 border border-charcoal-700 rounded text-xs text-charcoal-300 space-y-1">
          <p>• <strong>Isolation:</strong> Patch generated and verified entirely inside an ephemeral disposable workspace.</p>
          <p>• <strong>Regression Guard:</strong> Changes were tested against the full project regression test suite prior to approval.</p>
          <p>• <strong>Remaining Risk:</strong> Uncovered edge cases not present in the existing test suite could exist. Always review the unified diff below prior to exporting.</p>
        </div>
      </div>
      
      {/* Code Changes */}
      <div ref={codeChangesRef} className="border-t border-charcoal-700 pt-4">
        <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
          <FileCode className="h-5 w-5" />
          Code Changes (Unified Diff)
        </h3>
        <div className="bg-charcoal-900 border border-charcoal-800 rounded-lg p-4 font-mono text-sm overflow-auto max-h-80">
          <pre className="whitespace-pre-wrap text-charcoal-300">{diff?.raw_diff || '(No patch changes recorded)'}</pre>
        </div>
      </div>
      
      <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-charcoal-700">
        <Button variant="secondary" onClick={onClose} size="md">
          <ChevronLeft className="h-4 w-4 mr-1" />
          Close
        </Button>
        <Button 
          variant={status === 'verified' ? 'secondary' : 'primary'} 
          onClick={onRetry}
        >
          {status === 'verified' ? 'Exit' : 'Try Another Repair'}
        </Button>
      </div>
    </div>
  );
};