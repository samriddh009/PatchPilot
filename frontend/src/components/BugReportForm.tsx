import React, { useState } from 'react';
import { Button } from './Common/Button';
import { Repository, ProposedTest } from '../types/domain';
import { proposeTest } from '../api/endpoints';
import { 
  ChevronLeft, 
  Bug, 
  TestTube, 
  AlertCircle, 
  Loader2, 
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Check,
  FileCode,
  Info
} from 'lucide-react';
import { extractTestTarget } from '../utils/testTargetUtils';

interface BugReportFormProps {
  repositoryId: string;
  repository?: Repository | null;
  bugReport: string;
  setBugReport: (report: string) => void;
  testTarget: string;
  setTestTarget: (target: string) => void;
  onBack: () => void;
  onStartRepair: () => void;
  error: string | null;
  isLoading: boolean;
}

export const BugReportForm = ({ 
  repositoryId, 
  repository,
  bugReport, 
  setBugReport, 
  testTarget, 
  setTestTarget, 
  onBack, 
  onStartRepair,
  error,
  isLoading
}: BugReportFormProps) => {
  const [formError, setFormError] = useState<string | null>(null);
  const [isProposingTest, setIsProposingTest] = useState(false);
  const [proposedTest, setProposedTest] = useState<ProposedTest | null>(null);
  const [proposalSuccessMsg, setProposalSuccessMsg] = useState<string | null>(null);

  const handleSubmit = (e?: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement>) => {
    if (e && 'preventDefault' in e) {
      e.preventDefault();
    }
    setFormError(null);
    
    if (!bugReport.trim() || bugReport.trim().length < 10) {
      setFormError('Please enter a detailed bug report (at least 10 characters)');
      return;
    }
    
    const clean = extractTestTarget(testTarget);
    setTestTarget(clean || '');
    onStartRepair();
  };

  const handleProposeTest = async () => {
    if (!bugReport.trim() || bugReport.trim().length < 10) {
      setFormError('Please describe the bug before generating a proposed test');
      return;
    }
    setFormError(null);
    try {
      setIsProposingTest(true);
      const res = await proposeTest(repositoryId, bugReport.trim());
      setProposedTest(res.data);
      setProposalSuccessMsg('Focused test proposal generated successfully!');
      setTimeout(() => setProposalSuccessMsg(null), 3000);
    } catch (err: any) {
      const errorObj = err?.response?.data?.error || err?.response?.data?.detail;
      let msg =
        errorObj?.message ||
        err?.response?.data?.error?.message ||
        err?.response?.data?.detail?.message ||
        'Failed to generate test proposal.';

      if (errorObj?.details?.errors && Array.isArray(errorObj.details.errors)) {
        const fieldErrors = errorObj.details.errors
          .map((e: any) => `${e.field || e.loc?.slice(1)?.join('.') || 'field'}: ${e.message || e.msg}`)
          .join(', ');
        if (fieldErrors && !msg.includes(fieldErrors)) {
          msg = `Validation failed: ${fieldErrors}`;
        }
      }
      setFormError(msg);
    } finally {
      setIsProposingTest(false);
    }
  };

  const handleApplyProposedTest = () => {
    if (!proposedTest) return;
    const clean = extractTestTarget(proposedTest.test_target) || extractTestTarget(proposedTest);
    setTestTarget(clean || '');
  };

  const isNoTests = repository?.layout_status === 'no_tests' || (repository?.test_targets && repository.test_targets.length === 0);

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-blue-400 flex items-center gap-2">
            <Bug className="h-6 w-6" />
            Describe Bug & Select Test
          </h2>
          <p className="text-xs text-charcoal-400 mt-0.5">
            Target repository: <span className="font-semibold text-charcoal-200">{repository?.name || repositoryId}</span>
          </p>
        </div>
        <Button variant="secondary" onClick={onBack} size="sm" disabled={isLoading}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      </div>
      
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-600/10 border border-red-600/20 rounded-lg text-sm text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {repository?.execution_allowed === false && (
        <div className="p-4 bg-yellow-600/15 border border-yellow-600/35 rounded-lg flex items-start gap-3 text-xs text-yellow-300">
          <ShieldAlert className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-yellow-200">Execution Restricted on Host (Mode A: Static Inspection)</p>
            <p className="text-yellow-300/90 leading-relaxed">
              Docker container isolation is currently unavailable. PatchPilot strictly refuses to execute untrusted user repository code on an uncontained host.
            </p>
            <p className="text-yellow-400/80">
              Source file inspection and AI test proposals remain fully available without Docker. To run tests on user projects, start Docker Desktop.
            </p>
          </div>
        </div>
      )}

      {repository?.execution_allowed && !repository?.is_fixture && (
        <div className="p-3.5 bg-emerald-600/10 border border-emerald-600/25 rounded-lg flex items-start gap-2.5 text-xs text-emerald-300">
          <ShieldCheck className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-emerald-200">Isolated Container Execution Active (Mode C): </span>
            Repairs and tests will run inside an isolated ephemeral Docker container with network disabled and bounded limits. Your original repository is strictly read-only.
          </div>
        </div>
      )}

      {isNoTests && (
        <div className="p-3.5 bg-blue-600/10 border border-blue-600/25 rounded-lg flex items-start gap-2.5 text-xs text-blue-300">
          <Info className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-blue-200">No Existing Test Suite Detected: </span>
            This project has no configured test runner. PatchPilot can inspect your source code and propose focused reproduction tests based on your bug description.
          </div>
        </div>
      )}
      
      {formError && (
        <div className="flex items-center gap-2 p-3 bg-red-600/10 border border-red-600/20 rounded-lg text-sm text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{formError}</span>
        </div>
      )}

      {proposalSuccessMsg && (
        <div className="flex items-center gap-2 p-3 bg-emerald-600/15 border border-emerald-600/30 rounded-lg text-xs text-emerald-300">
          <Check className="h-4 w-4 flex-shrink-0 text-emerald-400" />
          <span>{proposalSuccessMsg}</span>
        </div>
      )}
      
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-charcoal-50 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Bug className="h-4 w-4 text-blue-400" />
            Bug Report
          </span>
          <span className="text-[11px] text-charcoal-400 font-normal">Min 10 characters</span>
        </label>
        <textarea
          value={bugReport}
          onChange={(e) => setBugReport(e.target.value)}
          placeholder="Enter a detailed description of the bug...&#10;&#10;Example: The calculate_discount function fails to apply a 15% discount when the cart total equals exactly $100.00."
          className="w-full textarea font-mono text-sm bg-charcoal-950 border border-charcoal-700 rounded-lg p-3 text-charcoal-100 placeholder-charcoal-500 focus:outline-none focus:border-blue-500"
          rows={5}
          disabled={isLoading}
        />
        <p className="text-xs text-charcoal-400">
          Provide a clear description of the defect, including expected vs actual behavior.
        </p>
      </div>

      {/* Test Proposal Generator Section */}
      <div className="p-4 bg-charcoal-900 border border-charcoal-800 rounded-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-400" />
            <span className="text-xs font-semibold text-white">AI Test Proposal Generator</span>
          </div>
          <button
            type="button"
            onClick={handleProposeTest}
            disabled={isProposingTest || !bugReport.trim() || bugReport.trim().length < 10}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium transition-colors"
          >
            {isProposingTest ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Generating Test...
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                Propose Focused Test
              </>
            )}
          </button>
        </div>

        {proposedTest && (
          <div className="mt-3 p-3 bg-charcoal-950 border border-charcoal-700 rounded-md space-y-2.5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <FileCode className="h-4 w-4 text-emerald-400" />
                <span className="font-mono text-xs text-charcoal-200 font-semibold">{proposedTest.test_file_path}</span>
              </div>
              <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                PROPOSED (Not Executed)
              </span>
            </div>

            <p className="text-xs text-charcoal-300 leading-relaxed">
              {proposedTest.explanation}
            </p>

            <div className="bg-charcoal-900 p-2.5 rounded border border-charcoal-800 overflow-x-auto max-h-36">
              <pre className="font-mono text-[11px] text-charcoal-200 whitespace-pre">
                {proposedTest.test_code}
              </pre>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-charcoal-400">Target: <code className="font-mono text-charcoal-300">{proposedTest.test_target}</code></span>
              <button
                type="button"
                onClick={handleApplyProposedTest}
                className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded transition-colors ${
                  testTarget === proposedTest.test_target
                    ? 'bg-emerald-600 text-white font-semibold'
                    : 'bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-200 border border-charcoal-700'
                }`}
              >
                {testTarget === proposedTest.test_target ? (
                  <>
                    <Check className="h-3 w-3" />
                    Target Selected
                  </>
                ) : (
                  'Use as Test Target'
                )}
              </button>
            </div>
          </div>
        )}
      </div>
      
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-charcoal-50 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <TestTube className="h-4 w-4 text-green-400" />
            Target Test Identifier
          </span>
          {isNoTests && (
            <span className="text-[11px] text-amber-400 font-normal">Optional for source-only</span>
          )}
        </label>
        <input
          type="text"
          value={extractTestTarget(testTarget) || (typeof testTarget === 'string' && testTarget !== '[object Object]' && testTarget !== 'undefined' && testTarget !== 'null' ? testTarget : '')}
          onChange={(e) => {
            const val = e.target.value;
            setTestTarget(val === '[object Object]' || val === 'undefined' || val === 'null' ? '' : val);
          }}
          placeholder="e.g., tests/test_calculator.py::test_discount_boundary"
          className="w-full input font-mono text-sm bg-charcoal-950 border border-charcoal-700 rounded-lg p-2.5 text-charcoal-100 placeholder-charcoal-500 focus:outline-none focus:border-blue-500"
          disabled={isLoading}
        />
        <p className="text-xs text-charcoal-400">
          Specify a test to reproduce the bug. If left blank, PatchPilot uses available discovered tests or proposed tests.
        </p>
      </div>
      
      <div className="flex justify-end pt-4 border-t border-charcoal-700">
        <Button 
          variant="primary" 
          onClick={handleSubmit} 
          disabled={isLoading || !bugReport.trim() || repository?.execution_allowed === false}
          loading={isLoading}
        >
          <Loader2 className="h-4 w-4" />
          {repository?.execution_allowed === false ? 'Execution Blocked (Docker Required)' : 'Start Controlled Repair'}
        </Button>
      </div>
    </form>
  );
};