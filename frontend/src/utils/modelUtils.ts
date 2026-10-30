/**
 * Utilities for Gemini model discovery, normalization, selection, and verification.
 */

export const DEFAULT_CANDIDATE_MODELS: string[] = [
  'gemini-2.5-flash',
  'gemini-2.5-pro',
  'gemini-2.0-flash',
  'gemini-1.5-flash',
  'gemini-1.5-pro',
  'gemini-2.0-flash-exp',
];

/**
 * Chooses a sensible, high-performance model for automated code repair
 * from an active list of live-discovered models.
 * 
 * Rules:
 * 1. If currentModel is non-empty and present in availableModels, keep it.
 * 2. Otherwise, match against known preferred models in priority order.
 * 3. Fallback to any model containing 'flash' or 'gemini'.
 * 4. Never return an unavailable model if availableModels is non-empty.
 */
export function pickSensibleModel(availableModels: string[], currentModel?: string): string {
  if (!availableModels || availableModels.length === 0) {
    return currentModel || DEFAULT_CANDIDATE_MODELS[0];
  }

  // Rule 1: Keep currentModel if it exists in available models
  if (currentModel && availableModels.includes(currentModel)) {
    return currentModel;
  }

  // Rule 2: Prefer modern fast models suitable for agentic code editing
  const priorityPreference = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-2.5-pro',
    'gemini-1.5-pro',
    'gemini-2.0-flash-exp',
  ];

  for (const preferred of priorityPreference) {
    const match = availableModels.find(
      (m) => m.toLowerCase() === preferred.toLowerCase()
    );
    if (match) {
      return match;
    }
  }

  // Rule 3: Any model with 'flash' (fastest tier)
  const flashModel = availableModels.find((m) =>
    m.toLowerCase().includes('flash')
  );
  if (flashModel) {
    return flashModel;
  }

  // Rule 4: Any model with 'gemini'
  const geminiModel = availableModels.find((m) =>
    m.toLowerCase().includes('gemini')
  );
  if (geminiModel) {
    return geminiModel;
  }

  // Fallback to the very first discovered model
  return availableModels[0];
}

/**
 * Checks whether a candidate model is confirmed available via live discovery.
 */
export function isModelLiveConfirmed(
  model: string,
  isLiveDiscovered: boolean,
  availableModels: string[]
): boolean {
  if (!isLiveDiscovered || !availableModels || availableModels.length === 0) {
    return false;
  }
  return availableModels.includes(model);
}
