import { describe, it, expect } from 'vitest';
import { extractTestTarget, formatTestEvidenceDisplay } from './testTargetUtils';

describe('testTargetUtils', () => {
  describe('extractTestTarget', () => {
    it('returns null for null, undefined, or empty string', () => {
      expect(extractTestTarget(null)).toBeNull();
      expect(extractTestTarget(undefined)).toBeNull();
      expect(extractTestTarget('')).toBeNull();
      expect(extractTestTarget('   ')).toBeNull();
    });

    it('rejects literal [object Object], undefined, null, and nan strings', () => {
      expect(extractTestTarget('[object Object]')).toBeNull();
      expect(extractTestTarget('[object object]')).toBeNull();
      expect(extractTestTarget('undefined')).toBeNull();
      expect(extractTestTarget('UNDEFINED')).toBeNull();
      expect(extractTestTarget('null')).toBeNull();
      expect(extractTestTarget('NULL')).toBeNull();
      expect(extractTestTarget('NaN')).toBeNull();
    });

    it('returns valid string test identifiers correctly trimmed', () => {
      expect(extractTestTarget('tests/test_calc.py::test_boundary')).toBe(
        'tests/test_calc.py::test_boundary'
      );
      expect(extractTestTarget('  tests/test_calc.py::test_boundary  ')).toBe(
        'tests/test_calc.py::test_boundary'
      );
    });

    it('extracts test_target from an object payload', () => {
      const obj = {
        test_target: 'tests/test_calculator.py::test_discount_boundary',
        exit_code: 1,
        classification: 'assertion_failure',
        log_snippet: 'AssertionError: assert 90.0 == 85.0',
      };
      expect(extractTestTarget(obj)).toBe(
        'tests/test_calculator.py::test_discount_boundary'
      );
    });

    it('extracts target or test_file_path fallback from object if test_target is absent', () => {
      expect(extractTestTarget({ target: 'tests/test_app.py' })).toBe('tests/test_app.py');
      expect(extractTestTarget({ test_file_path: 'tests/test_proposed.py' })).toBe(
        'tests/test_proposed.py'
      );
    });

    it('returns null if object has [object Object] or invalid values', () => {
      expect(extractTestTarget({ test_target: '[object Object]' })).toBeNull();
      expect(extractTestTarget({ test_target: '' })).toBeNull();
      expect(extractTestTarget({ unrelated_key: 'foo' })).toBeNull();
    });

    it('returns null for numbers, booleans, and other non-target types', () => {
      expect(extractTestTarget(123)).toBeNull();
      expect(extractTestTarget(true)).toBeNull();
      expect(extractTestTarget(false)).toBeNull();
      expect(extractTestTarget(['a', 'b'])).toBeNull();
    });
  });

  describe('formatTestEvidenceDisplay', () => {
    it('returns empty string for null, undefined, or [object Object]', () => {
      expect(formatTestEvidenceDisplay(null)).toBe('');
      expect(formatTestEvidenceDisplay(undefined)).toBe('');
      expect(formatTestEvidenceDisplay('[object Object]')).toBe('');
    });

    it('returns test_target from evidence object', () => {
      expect(
        formatTestEvidenceDisplay({
          test_target: 'tests/test_calculator.py::test_boundary',
          exit_code: 1,
        })
      ).toBe('tests/test_calculator.py::test_boundary');
    });

    it('falls back to log_snippet if test_target is absent', () => {
      expect(
        formatTestEvidenceDisplay({
          log_snippet: 'AssertionError: expected 5 got 4',
        })
      ).toBe('AssertionError: expected 5 got 4');
    });

    it('returns raw string if valid string', () => {
      expect(formatTestEvidenceDisplay('tests/test_foo.py')).toBe('tests/test_foo.py');
    });
  });
});
