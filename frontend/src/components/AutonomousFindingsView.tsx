import React, { useState } from 'react';
import { Finding, DiscoverBugsResponse, Repository } from '../types/domain';
import { Button } from './Common/Button';
import { 
  Bug, 
  Search, 
  ChevronLeft, 
  AlertTriangle, 
  CheckCircle2, 
  HelpCircle, 
  FileCode, 
  Wrench, 
  Loader2, 
  Layers, 
  ShieldCheck, 
  Sliders,
  Terminal,
  Code
} from 'lucide-react';
import { formatTestEvidenceDisplay } from '../utils/testTargetUtils';

interface AutonomousFindingsViewProps {
  repository: Repository | null;
  onBack: () => void;
  onStartRepairForFinding: (finding: Finding) => void;
  onCandidateRepairReady?: (repairId: string) => void;
  onDiscoverBugs: (options: {
    scan_depth: 'standard' | 'deep';
    defect_category?: string;
    target_path?: string;
    auto_prepare_fix?: boolean;
  }) => Promise<DiscoverBugsResponse>;
}

export const AutonomousFindingsView: React.FC<AutonomousFindingsViewProps> = ({
  repository,
  onBack,
  onStartRepairForFinding,
  onCandidateRepairReady,
  onDiscoverBugs,
}) => {
  const [scanDepth, setScanDepth] = useState<'standard' | 'deep'>('standard');
  const [defectCategory, setDefectCategory] = useState<string>('all');
  const [targetPath, setTargetPath] = useState<string>('');
  const [autoPrepareFix, setAutoPrepareFix] = useState<boolean>(false);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanResult, setScanResult] = useState<DiscoverBugsResponse | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null);

  const handleScan = async (prepareFixOverride?: boolean) => {
    if (!repository) return;
    setIsScanning(true);
    setScanError(null);
    const prepareFix = prepareFixOverride !== undefined ? prepareFixOverride : autoPrepareFix;

    try {
      const res = await onDiscoverBugs({
        scan_depth: scanDepth,
        defect_category: defectCategory === 'all' ? undefined : defectCategory,
        target_path: targetPath.trim() || undefined,
        auto_prepare_fix: prepareFix,
      });
      setScanResult(res);
      if (res.candidate_repair_id && onCandidateRepairReady) {
        onCandidateRepairReady(res.candidate_repair_id);
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail?.message ||
        err?.response?.data?.error?.message ||
        err?.message ||
        'Autonomous bug discovery scan failed';
      setScanError(msg);
    } finally {
      setIsScanning(false);
    }
  };

  const getSeverityBadge = (severity: Finding['severity']) => {
    switch (severity) {
      case 'critical':
      case 'high':
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase rounded bg-red-500/20 text-red-400 border border-red-500/30">HIGH</span>;
      case 'medium':
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">MEDIUM</span>;
      case 'low':
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">LOW</span>;
      default:
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase rounded bg-charcoal-700 text-charcoal-300">{severity}</span>;
    }
  };

  const getConfidenceBadge = (confidence: Finding['confidence']) => {
    switch (confidence) {
      case 'confirmed':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-semibold uppercase rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="h-3 w-3" /> Confirmed
          </span>
        );
      case 'likely':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-semibold uppercase rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
            <AlertTriangle className="h-3 w-3" /> Likely
          </span>
        );
      case 'inconclusive':
        return (
          <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-semibold uppercase rounded bg-charcoal-700 text-charcoal-400 border border-charcoal-600">
            <HelpCircle className="h-3 w-3" /> Inconclusive
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-blue-400 flex items-center gap-2">
            <Search className="h-6 w-6" />
            Autonomous Bug Discovery
          </h2>
          <p className="text-xs text-charcoal-400 mt-0.5">
            Scan repository <span className="text-charcoal-200 font-semibold">{repository?.name}</span> for defects, boundary faults, and logic errors without needing a bug report.
          </p>
        </div>
        <Button variant="secondary" onClick={onBack} size="sm" disabled={isScanning}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      </div>

      {scanError && (
        <div className="flex items-center gap-2 p-3 bg-red-600/15 border border-red-600/30 rounded-lg text-sm text-red-400">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{scanError}</span>
        </div>
      )}

      {/* Options Panel */}
      <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-charcoal-200 flex items-center gap-1.5">
            <Sliders className="h-4 w-4 text-blue-400" />
            Scan Configuration
          </h3>
          <span className="text-[11px] text-charcoal-400">Default settings optimized for fast, accurate defect discovery</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-charcoal-300 mb-1">Scan Depth</label>
            <select
              value={scanDepth}
              onChange={(e) => setScanDepth(e.target.value as 'standard' | 'deep')}
              disabled={isScanning}
              className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-2.5 py-1.5 text-xs text-charcoal-200 focus:outline-none focus:border-blue-500"
            >
              <option value="standard">Standard (AST & Pattern Scan)</option>
              <option value="deep">Deep (Comprehensive Inspection)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-charcoal-300 mb-1">Defect Category</label>
            <select
              value={defectCategory}
              onChange={(e) => setDefectCategory(e.target.value)}
              disabled={isScanning}
              className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-2.5 py-1.5 text-xs text-charcoal-200 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Categories</option>
              <option value="boundary_condition">Boundary & Inequality Faults</option>
              <option value="logic_error">Logic & Token Processing</option>
              <option value="exception_handling">Exception Handling & Returns</option>
              <option value="mutable_default">Mutable Defaults & State</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-charcoal-300 mb-1">Target Folder / File (Optional)</label>
            <input
              type="text"
              placeholder="e.g. src/ or calculator.py"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              disabled={isScanning}
              className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-2.5 py-1.5 text-xs text-charcoal-200 focus:outline-none focus:border-blue-500 placeholder-charcoal-600"
            />
          </div>
        </div>

        {/* Dual Actions: Find Bugs vs Find Bugs & Prepare Fixes */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-charcoal-700/60">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="autoPrepareToggle"
              checked={autoPrepareFix}
              onChange={(e) => setAutoPrepareFix(e.target.checked)}
              disabled={isScanning}
              className="rounded bg-charcoal-900 border-charcoal-700 text-blue-500 focus:ring-0 focus:outline-none h-4 w-4"
            />
            <label htmlFor="autoPrepareToggle" className="text-xs text-charcoal-300 cursor-pointer">
              Automatically prepare candidate fixes in disposable workspace
            </label>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => handleScan(false)}
              disabled={isScanning}
              size="md"
            >
              {isScanning && !autoPrepareFix ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin text-blue-400" />
                  Scanning Repository...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4 mr-1.5 text-blue-400" />
                  Find Bugs
                </>
              )}
            </Button>

            <Button
              variant="primary"
              onClick={() => handleScan(true)}
              disabled={isScanning}
              size="md"
            >
              {isScanning && autoPrepareFix ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  Scanning & Preparing Fix...
                </>
              ) : (
                <>
                  <Wrench className="h-4 w-4 mr-1.5" />
                  Find Bugs & Prepare Fixes
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Results View */}
      {scanResult && (
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3.5 bg-charcoal-800/80 border border-charcoal-700 rounded-lg">
            <div className="flex items-center gap-3">
              <Layers className="h-5 w-5 text-blue-400" />
              <div>
                <p className="text-sm font-semibold text-charcoal-100">
                  Discovery Scan Complete: {scanResult.total_findings} defect{scanResult.total_findings !== 1 ? 's' : ''} identified
                </p>
                <p className="text-xs text-charcoal-400">
                  Scanned {scanResult.files_scanned} files in {scanResult.scan_duration_seconds}s • Test suite status: <span className="font-mono text-charcoal-300">{scanResult.test_suite_status}</span>
                </p>
              </div>
            </div>
            {scanResult.candidate_repair_id && (
              <span className="text-xs font-semibold px-2.5 py-1 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                Fix In Progress: {scanResult.candidate_repair_id}
              </span>
            )}
          </div>

          {scanResult.findings.length === 0 ? (
            <div className="p-8 text-center bg-charcoal-800 border border-charcoal-700 rounded-lg">
              <ShieldCheck className="h-10 w-10 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm font-medium text-charcoal-200">No Defects Found</p>
              <p className="text-xs text-charcoal-400 mt-1">
                The scanner inspected all source files against implemented defect rules and identified no boundary, logic, or unhandled exception errors.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {scanResult.findings.map((finding) => {
                const isExpanded = expandedFindingId === finding.id;

                return (
                  <div
                    key={finding.id}
                    className="border border-charcoal-700 bg-charcoal-800/90 rounded-lg p-4 space-y-3 transition-colors hover:border-charcoal-600"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-mono font-bold text-blue-400 bg-charcoal-900 px-2 py-0.5 rounded border border-charcoal-700">
                            {finding.id}
                          </span>
                          {getSeverityBadge(finding.severity)}
                          {getConfidenceBadge(finding.confidence)}
                          <span className="text-xs font-mono text-charcoal-400 flex items-center gap-1">
                            <FileCode className="h-3.5 w-3.5 text-charcoal-500" />
                            {finding.file_path}{finding.line_start ? `:${finding.line_start}` : ''}
                          </span>
                        </div>
                        <h4 className="text-sm font-semibold text-charcoal-100">{finding.title}</h4>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => setExpandedFindingId(isExpanded ? null : finding.id)}
                        >
                          {isExpanded ? 'Hide Details' : 'Details'}
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => onStartRepairForFinding(finding)}
                        >
                          <Wrench className="h-3.5 w-3.5 mr-1" />
                          Prepare Fix
                        </Button>
                      </div>
                    </div>

                    <p className="text-xs text-charcoal-300 leading-relaxed">{finding.explanation}</p>

                    {finding.code_excerpt && (
                      <div className="bg-charcoal-900 border border-charcoal-800 rounded p-2.5 font-mono text-xs text-yellow-300/90 overflow-x-auto">
                        <pre>{finding.code_excerpt}</pre>
                      </div>
                    )}

                    {isExpanded && (
                      <div className="pt-3 border-t border-charcoal-700/60 space-y-2.5 text-xs text-charcoal-300">
                        {finding.expected_behavior && (
                          <div>
                            <span className="font-semibold text-emerald-400">Expected: </span>
                            {finding.expected_behavior}
                          </div>
                        )}
                        {finding.observed_behavior && (
                          <div>
                            <span className="font-semibold text-red-400">Observed: </span>
                            {finding.observed_behavior}
                          </div>
                        )}
                        {finding.test_evidence && (
                          <div className="flex items-start gap-1.5 p-2 bg-charcoal-900/80 rounded border border-charcoal-800">
                            <Terminal className="h-4 w-4 text-purple-400 flex-shrink-0 mt-0.5" />
                            <div>
                              <span className="font-semibold text-purple-300">Test Evidence: </span>
                              <span className="font-mono text-charcoal-200">
                                {formatTestEvidenceDisplay(finding.test_evidence)}
                              </span>
                            </div>
                          </div>
                        )}
                        {finding.suggested_fix && (
                          <div>
                            <span className="font-semibold text-blue-400">Suggested Fix: </span>
                            {finding.suggested_fix}
                          </div>
                        )}
                        <div className="text-[11px] text-charcoal-400 pt-1">
                          Severity Rationale: {finding.severity_rationale} • Confidence Rationale: {finding.confidence_rationale}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
