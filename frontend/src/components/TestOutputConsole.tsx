import React from 'react';
import { Terminal, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

interface TestOutputConsoleProps {
  repairData: any;
  events: any[];
}

export const TestOutputConsole = ({ repairData, events }: TestOutputConsoleProps) => {
  // Extract test execution events
  const testEvents = events.filter(e => 
    e.event_type === 'test_execution_started' || 
    e.event_type === 'test_execution_completed' ||
    e.event_type === 'tool_result' && e.payload?.tool === 'run_targeted_test' ||
    e.event_type === 'tool_result' && e.payload?.tool === 'run_regression_tests'
  );

  const getTestOutput = () => {
    if (!repairData) return 'Waiting for repair to start...';
    
    let output = '';
    
    // Show baseline test result
    if (repairData.baseline_failure_classification) {
      output += `=== BASELINE TEST EXECUTION ===\n`;
      output += `Exit code: ${repairData.baseline_passed === false ? 1 : 0}\n`;
      output += `Classification: ${repairData.baseline_failure_classification}\n`;
      if (repairData.baseline_failure_classification === 'assertion_failure') {
        output += `Status: FAIL (Expected for reproduction)\n`;
      } else {
        output += `Status: INFRASTRUCTURE FAILURE\n`;
      }
      output += `\n`;
    }
    
    // Show targeted test result
    if (repairData.targeted_passed !== undefined) {
      output += `=== TARGETED TEST (AFTER PATCH) ===\n`;
      output += `Exit code: ${repairData.targeted_passed === true ? 0 : 1}\n`;
      output += `Status: ${repairData.targeted_passed === true ? 'PASS' : 'FAIL'}\n`;
      output += `\n`;
    }
    
    // Show regression test result
    if (repairData.regression_passed !== undefined) {
      output += `=== REGRESSION TEST SUITE ===\n`;
      output += `Exit code: ${repairData.regression_passed === true ? 0 : 1}\n`;
      output += `Status: ${repairData.regression_passed === true ? 'PASS' : 'FAIL'}\n`;
      output += `\n`;
    }
    
    // Add event-based output
    if (testEvents.length > 0) {
      output += `=== EVENT LOG ===\n`;
      testEvents.forEach(event => {
        const time = new Date(event.created_at).toLocaleTimeString();
        output += `[${time}] ${event.event_type}: `;
        if (event.payload?.stdout_snippet) {
          output += event.payload.stdout_snippet;
        } else if (event.payload?.tool) {
          output += `Tool: ${event.payload.tool}`;
          if (event.payload?.exit_code !== undefined) {
            output += `, Exit: ${event.payload.exit_code}`;
          }
        }
        output += '\n';
      });
    }
    
    return output || 'Waiting for test output...';
  };

  return (
    <div className="space-y-4 flex flex-col h-full">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-blue-400 flex items-center gap-2">
          <Terminal className="h-5 w-5" />
          Test Output
        </h3>
        {repairData && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-charcoal-400">Status:</span>
            <span className={`px-2 py-0.5 text-xs rounded ${
              repairData.status === 'verified' ? 'bg-green-600/20 text-green-400' :
              repairData.status === 'unresolved' ? 'bg-yellow-600/20 text-yellow-400' :
              repairData.status === 'failed' ? 'bg-red-600/20 text-red-400' :
              repairData.status === 'cancelled' ? 'bg-gray-600/20 text-gray-400' :
              'bg-blue-600/20 text-blue-400 animate-pulse'
            }`}>
              {repairData.status?.toUpperCase()}
            </span>
          </div>
        )}
      </div>
      
      <div className="bg-charcoal-900 border border-charcoal-800 rounded-lg p-4 font-mono text-sm overflow-auto flex-1 min-h-0">
        <pre className="whitespace-pre-wrap text-charcoal-300">{getTestOutput()}</pre>
      </div>
      
      {/* Status badges */}
      {repairData && (
        <div className="flex flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-charcoal-400">Baseline:</span>
            <span className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${
              repairData.baseline_passed === false ? 'bg-red-600/20 text-red-400' : 
              repairData.baseline_passed === true ? 'bg-green-600/20 text-green-400' : 
              'bg-gray-600/20 text-gray-400'
            }`}>
              {repairData.baseline_passed === false && <XCircle className="h-3 w-3" />}
              {repairData.baseline_passed === true && <CheckCircle className="h-3 w-3" />}
              {repairData.baseline_passed === false ? 'FAIL' : repairData.baseline_passed === true ? 'PASS' : 'N/A'}
            </span>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-xs text-charcoal-400">Targeted:</span>
            <span className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${
              repairData.targeted_passed === false ? 'bg-red-600/20 text-red-400' : 
              repairData.targeted_passed === true ? 'bg-green-600/20 text-green-400' : 
              'bg-gray-600/20 text-gray-400'
            }`}>
              {repairData.targeted_passed === false && <XCircle className="h-3 w-3" />}
              {repairData.targeted_passed === true && <CheckCircle className="h-3 w-3" />}
              {repairData.targeted_passed === false ? 'FAIL' : repairData.targeted_passed === true ? 'PASS' : 'N/A'}
            </span>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-xs text-charcoal-400">Regression:</span>
            <span className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${
              repairData.regression_passed === false ? 'bg-red-600/20 text-red-400' : 
              repairData.regression_passed === true ? 'bg-green-600/20 text-green-400' : 
              'bg-gray-600/20 text-gray-400'
            }`}>
              {repairData.regression_passed === false && <XCircle className="h-3 w-3" />}
              {repairData.regression_passed === true && <CheckCircle className="h-3 w-3" />}
              {repairData.regression_passed === false ? 'FAIL' : repairData.regression_passed === true ? 'PASS' : 'N/A'}
            </span>
          </div>
          
          {repairData.recovery_attempts > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-charcoal-400">Recovery:</span>
              <span className="px-2 py-0.5 text-xs rounded bg-yellow-600/20 text-yellow-400 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                Attempt {repairData.recovery_attempts}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};