export interface Repository {
  id: string;
  name: string;
  language: 'python' | 'javascript' | 'typescript' | 'java' | 'unknown';
  test_framework: 'pytest' | 'vitest' | 'jest' | 'maven_junit' | 'gradle_junit' | 'unknown';
  file_count?: number;
  test_targets?: string[];
  is_fixture?: boolean;
  execution_allowed?: boolean;
  execution_warning?: string | null;
  layout_status?: 'supported' | 'unsupported' | 'missing_test_tooling' | 'no_tests';
  created_at: string;
}

export interface RepositoryFileContent {
  repository_id: string;
  file_path: string;
  content: string;
  total_lines: number;
  offset_line: number;
  limit_lines: number;
  language: string;
}

export interface ProposedTest {
  repository_id: string;
  test_file_path: string;
  test_code: string;
  test_target: string;
  explanation: string;
  status: 'proposed';
}

export interface Repair {
  id: string;
  repository_id: string;
  bug_report: string;
  test_target?: string;
  status: RepairStatus;
  recovery_attempts: number;
  baseline_passed?: boolean | null;
  baseline_failure_classification?: string | null;
  targeted_passed?: boolean | null;
  regression_passed?: boolean | null;
  has_diff: boolean;
  restricted_mode: boolean;
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface RepairEvent {
  id: string;
  repair_id: string;
  sequence_id: number;
  event_type: 'state_transition' | 'tool_invocation' | 'tool_result' | 'diff_generated' | 'test_execution_started' | 'test_execution_completed' | 'recovery_triggered' | 'verification_verdict' | 'error_encountered';
  payload: any;
  created_at: string;
}

export interface DiffResponse {
  repair_id: string;
  has_diff: boolean;
  raw_diff: string;
  files_changed: Array<{
    path: string;
    insertions: number;
    deletions: number;
  }>;
  total_insertions: number;
  total_deletions: number;
}

export interface ReportResponse {
  repair_id: string;
  repository_id: string;
  status: RepairStatus;
  bug_report: string;
  duration_seconds: number;
  recovery_attempts: number;
  verification: {
    outcome: 'verified' | 'unresolved' | 'failed';
    baseline_reproduced: boolean;
    baseline_exit_code?: number | null;
    baseline_log_snippet?: string | null;
    targeted_pass: boolean;
    targeted_exit_code?: number | null;
    regression_pass: boolean;
    regression_exit_code?: number | null;
    total_tests_run: number;
    total_tests_passed: number;
  };
  diff: {
    raw_diff: string;
    files_changed: string[];
  };
  markdown_summary: string;
}

export type RepairStatus = 
  | 'queued'
  | 'inspecting'
  | 'reproducing'
  | 'patching'
  | 'testing'
  | 'verifying'
  | 'recovering'
  | 'awaiting_approval'
  | 'exporting'
  | 'verified'
  | 'unresolved'
  | 'failed'
  | 'cancelled';

export interface TestEvidence {
  test_target?: string;
  exit_code?: number;
  classification?: string;
  log_snippet?: string;
}

export interface Finding {
  id: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  severity_rationale: string;
  confidence: 'confirmed' | 'likely' | 'inconclusive';
  confidence_rationale: string;
  file_path: string;
  line_start?: number | null;
  line_end?: number | null;
  code_excerpt?: string | null;
  explanation: string;
  expected_behavior?: string | null;
  observed_behavior?: string | null;
  reproduction_steps?: string[];
  test_evidence?: TestEvidence | string | null;
  suggested_fix?: string | null;
  category: string;
}

export interface DiscoverBugsResponse {
  repository_id: string;
  findings: Finding[];
  total_findings: number;
  scan_duration_seconds: number;
  files_scanned: number;
  test_suite_status: string;
  candidate_repair_id?: string | null;
}