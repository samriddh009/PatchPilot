/**
 * Utility functions for extracting, validating, and sanitizing test target identifiers.
 * Prevents literal '[object Object]', 'undefined', or 'null' from ever entering form state,
 * input fields, or API request payloads.
 */

export function extractTestTarget(target: unknown): string | null {
  if (target === undefined || target === null) {
    return null;
  }

  if (typeof target === 'string') {
    const trimmed = target.trim();
    if (!trimmed || isInvalidLiteral(trimmed)) {
      return null;
    }
    return trimmed;
  }

  if (typeof target === 'object') {
    const candidate =
      (target as any).test_target ??
      (target as any).target ??
      (target as any).test_identifier ??
      (target as any).test_file_path;

    if (typeof candidate === 'string') {
      const trimmed = candidate.trim();
      if (trimmed && !isInvalidLiteral(trimmed)) {
        return trimmed;
      }
    }
    return null;
  }

  return null;
}

function isInvalidLiteral(val: string): boolean {
  const lower = val.toLowerCase();
  return (
    lower === '[object object]' ||
    lower === 'undefined' ||
    lower === 'null' ||
    lower === 'nan'
  );
}

export function formatTestEvidenceDisplay(evidence: unknown): string {
  if (!evidence) return '';
  if (typeof evidence === 'string') {
    return isInvalidLiteral(evidence) ? '' : evidence;
  }
  if (typeof evidence === 'object') {
    const target = (evidence as any).test_target;
    if (typeof target === 'string' && !isInvalidLiteral(target)) {
      return target;
    }
    const snippet = (evidence as any).log_snippet;
    if (typeof snippet === 'string' && !isInvalidLiteral(snippet)) {
      return snippet;
    }
    const classification = (evidence as any).classification;
    if (typeof classification === 'string' && !isInvalidLiteral(classification)) {
      return classification;
    }
  }
  return '';
}
