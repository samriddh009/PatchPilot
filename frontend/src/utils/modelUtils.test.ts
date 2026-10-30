import { describe, it, expect } from 'vitest';
import {
  DEFAULT_CANDIDATE_MODELS,
  pickSensibleModel,
  isModelLiveConfirmed,
} from './modelUtils';

describe('Gemini Model Discovery & Selection Logic (modelUtils)', () => {
  it('retains current model if it is confirmed in the live-discovered models', () => {
    const liveModels = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash'];
    const chosen = pickSensibleModel(liveModels, 'gemini-1.5-flash');
    expect(chosen).toBe('gemini-1.5-flash');
  });

  it('selects a sensible modern flash model when current model is NOT in live models', () => {
    // Current model is gemini-1.5-flash, but key only has 2.5 series
    const liveModels = ['gemini-2.5-flash', 'gemini-2.5-pro', 'text-embedding-004'];
    const chosen = pickSensibleModel(liveModels, 'gemini-1.5-flash');
    // Must NOT silently keep gemini-1.5-flash
    expect(chosen).toBe('gemini-2.5-flash');
  });

  it('selects gemini-2.0-flash or gemini-2.5-pro in priority order if preferred is unavailable', () => {
    const liveModels = ['gemini-2.5-pro', 'gemini-1.0-pro'];
    const chosen = pickSensibleModel(liveModels, 'gemini-1.5-flash');
    expect(chosen).toBe('gemini-2.5-pro');
  });

  it('falls back to any flash or first available model if custom names returned', () => {
    const liveModels = ['custom-tuned-flash-v1', 'custom-tuned-chat'];
    const chosen = pickSensibleModel(liveModels, 'gemini-1.5-flash');
    expect(chosen).toBe('custom-tuned-flash-v1');
  });

  it('returns default candidate when no live models have been discovered yet', () => {
    const chosen = pickSensibleModel([], 'gemini-1.5-flash');
    expect(chosen).toBe('gemini-1.5-flash');

    const chosenWithoutCurrent = pickSensibleModel([]);
    expect(chosenWithoutCurrent).toBe(DEFAULT_CANDIDATE_MODELS[0]);
  });

  it('verifies that only models returned by live discovery are marked as confirmed', () => {
    const liveModels = ['gemini-2.5-flash', 'gemini-2.5-pro'];

    // Discovered models are confirmed
    expect(isModelLiveConfirmed('gemini-2.5-flash', true, liveModels)).toBe(true);
    expect(isModelLiveConfirmed('gemini-2.5-pro', true, liveModels)).toBe(true);

    // Stale candidate models NOT returned by Google must NOT be marked confirmed
    expect(isModelLiveConfirmed('gemini-1.5-flash', true, liveModels)).toBe(false);
    expect(isModelLiveConfirmed('gemini-1.5-pro', true, liveModels)).toBe(false);
    expect(isModelLiveConfirmed('gemini-2.0-flash-exp', true, liveModels)).toBe(false);

    // Before discovery (isLiveDiscovered = false), no models are confirmed
    expect(isModelLiveConfirmed('gemini-2.5-flash', false, liveModels)).toBe(false);
    expect(isModelLiveConfirmed('gemini-1.5-flash', false, [])).toBe(false);
  });

  it('correctly partitions confirmed models from unconfirmed candidates for dropdown optgroups', () => {
    const liveModels = ['gemini-2.5-flash', 'gemini-2.5-pro'];
    const unconfirmedCandidates = DEFAULT_CANDIDATE_MODELS.filter(
      (c) => !liveModels.some((m) => m.toLowerCase() === c.toLowerCase())
    );

    expect(unconfirmedCandidates).toContain('gemini-1.5-flash');
    expect(unconfirmedCandidates).toContain('gemini-1.5-pro');
    expect(unconfirmedCandidates).not.toContain('gemini-2.5-flash');
    expect(unconfirmedCandidates).not.toContain('gemini-2.5-pro');
  });
});
