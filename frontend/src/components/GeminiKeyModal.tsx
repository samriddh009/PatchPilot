import React, { useState } from 'react';
import { Button } from './Common/Button';
import { Key, CheckCircle, AlertCircle, Info, Loader2, Sparkles, AlertTriangle } from 'lucide-react';
import { DEFAULT_CANDIDATE_MODELS, pickSensibleModel, isModelLiveConfirmed } from '../utils/modelUtils';

interface GeminiKeyModalProps {
  sessionKey: string | null;
  setSessionKey: (key: string) => void;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  availableModels?: string[];
  isLiveDiscovered?: boolean;
  onDiscoverModels?: (key: string) => Promise<string[]>;
  connectionValid: boolean;
  onTestConnection: (model?: string, key?: string) => Promise<void>;
  onCancel: () => void;
  onSuccess: () => void;
  error: string | null;
  isLoading: boolean;
}

export const GeminiKeyModal = ({ 
  sessionKey, 
  setSessionKey, 
  selectedModel = 'gemini-1.5-flash',
  onModelChange,
  availableModels = [],
  isLiveDiscovered = false,
  onDiscoverModels,
  connectionValid, 
  onTestConnection, 
  onCancel, 
  onSuccess,
  error,
  isLoading
}: GeminiKeyModalProps) => {
  const [apiKey, setApiKey] = useState<string>(sessionKey || '');
  const [showKey, setShowKey] = useState<boolean>(false);
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [probeNotice, setProbeNotice] = useState<string | null>(null);

  const handleProbeModels = async () => {
    const cleanKey = apiKey.trim();
    if (!cleanKey || !onDiscoverModels) return;
    try {
      setIsDiscovering(true);
      setProbeNotice(null);
      const discovered = await onDiscoverModels(cleanKey);
      if (discovered && discovered.length > 0) {
        setProbeNotice(`Discovered ${discovered.length} live models from Google AI Studio.`);
        const sensible = pickSensibleModel(discovered, selectedModel);
        if (sensible) {
          onModelChange?.(sensible);
        }
      } else {
        setProbeNotice('No models discovered. Check key or network connectivity.');
      }
    } catch {
      setProbeNotice('Model discovery probe failed.');
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement>) => {
    if (e && 'preventDefault' in e) {
      e.preventDefault();
    }
    const cleanKey = apiKey.trim();
    if (!cleanKey) return;
    
    try {
      setSessionKey(cleanKey);
      await onTestConnection(selectedModel, cleanKey);
      onSuccess();
    } catch (err) {
      // Error is set in parent state; available_models is parsed into context
    }
  };

  const hasLiveModels = isLiveDiscovered && availableModels.length > 0;
  const isSelectedConfirmed = isModelLiveConfirmed(selectedModel, isLiveDiscovered, availableModels);
  const unconfirmedCandidates = DEFAULT_CANDIDATE_MODELS.filter(
    (c) => !availableModels.some((m) => m.toLowerCase() === c.toLowerCase())
  );

  return (
    <div className="fixed inset-0 bg-charcoal-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-6 w-full max-w-md">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 bg-blue-600/20 rounded-lg flex items-center justify-center">
            <Key className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-charcoal-50">Gemini API Configuration</h2>
            <p className="text-sm text-charcoal-400">Enter your API key to enable AI-powered repairs</p>
          </div>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-charcoal-50">
                API Key
              </label>
              {onDiscoverModels && (
                <button
                  type="button"
                  onClick={handleProbeModels}
                  disabled={isLoading || isDiscovering || !apiKey.trim()}
                  className="px-2 py-0.5 text-xs font-medium rounded bg-blue-600/20 text-blue-300 hover:bg-blue-600/30 border border-blue-500/30 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
                  title="Query Google AI Studio to discover models enabled for this key"
                >
                  {isDiscovering ? (
                    <>
                      <Loader2 className="h-3 w-3 animate-spin" />
                      <span>Probing...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3 w-3 text-blue-400" />
                      <span>Probe Models</span>
                    </>
                  )}
                </button>
              )}
            </div>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setProbeNotice(null);
                }}
                placeholder="AIzaSy... or sk-..."
                className="w-full input pr-12 font-mono text-sm"
                disabled={isLoading}
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-charcoal-400 hover:text-charcoal-200"
                disabled={isLoading}
              >
                {showKey ? <AlertCircle className="h-5 w-5" /> : <CheckCircle className="h-5 w-5" />}
              </button>
            </div>
            {probeNotice && (
              <p className="text-xs text-blue-300 mt-1 flex items-center gap-1">
                <Info className="h-3.5 w-3.5 text-blue-400" />
                <span>{probeNotice}</span>
              </p>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-charcoal-50">
                Gemini Model
              </label>
              {hasLiveModels ? (
                <span className="text-xs text-green-400 font-medium flex items-center gap-1">
                  <CheckCircle className="h-3 w-3" /> Live Discovered ({availableModels.length})
                </span>
              ) : (
                <span className="text-xs text-charcoal-400">Unverified candidates</span>
              )}
            </div>
            <select
              value={selectedModel}
              onChange={(e) => onModelChange?.(e.target.value)}
              disabled={isLoading}
              className="w-full input bg-charcoal-900 text-charcoal-100 border-charcoal-700 text-sm font-mono"
            >
              {hasLiveModels ? (
                <>
                  <optgroup label={`✓ Live Confirmed Models (${availableModels.length} available for key)`}>
                    {availableModels.map((m) => (
                      <option key={m} value={m}>
                        {m} (Verified available)
                      </option>
                    ))}
                  </optgroup>
                  {unconfirmedCandidates.length > 0 && (
                    <optgroup label="⚠ Unconfirmed Candidates (Not found for this key)">
                      {unconfirmedCandidates.map((m) => (
                        <option key={m} value={m} className="text-charcoal-400">
                          {m} (Unconfirmed)
                        </option>
                      ))}
                    </optgroup>
                  )}
                </>
              ) : (
                <optgroup label="Candidate Models (Probe key to verify)">
                  {DEFAULT_CANDIDATE_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m} (Unverified candidate)
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            
            {hasLiveModels && !isSelectedConfirmed && (
              <p className="text-xs text-yellow-400 mt-1.5 flex items-center gap-1">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                <span>Warning: Selected model '{selectedModel}' was not in Google's model list for this key.</span>
              </p>
            )}

            <p className="text-xs text-charcoal-400 mt-1">
              {hasLiveModels 
                ? `Models listed above were retrieved directly from Google AI Studio for this key.`
                : `Enter your API key and click "Probe Models" or "Test & Continue" to retrieve verified models.`}
            </p>
          </div>
          
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-600/10 border border-red-600/20 rounded-lg text-sm text-red-400">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}
          
          <div className="space-y-2 text-xs text-charcoal-400 border-t border-charcoal-700 pt-4">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 flex-shrink-0 mt-0.5 text-blue-400" />
              <div>
                <p className="font-medium text-charcoal-300">Privacy Notice</p>
                <p>Code snippets and bug descriptions are transmitted over TLS to Google Gemini API. Repository contents are subject to provider data policies.</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 flex-shrink-0 mt-0.5 text-yellow-400" />
              <div>
                <p className="font-medium text-charcoal-300">Free-tier Quota</p>
                <p>User-supplied keys are subject to provider rate limits (e.g. 15 RPM). Free tiers are not assumed to be unlimited.</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 flex-shrink-0 mt-0.5 text-green-400" />
              <div>
                <p className="font-medium text-charcoal-300">Key Storage</p>
                <p>Your API key is held only in browser memory for this session. It is never saved to disk, localStorage, or sent anywhere except the local backend.</p>
              </div>
            </div>
          </div>
          
          <div className="flex justify-between items-center gap-2 mt-4 flex-wrap">
            <Button variant="secondary" size="sm" onClick={onSuccess} disabled={isLoading} title="Continue in demo/inspection mode without live API key">
              Continue in Demo Mode
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={onCancel} disabled={isLoading}>
                Cancel
              </Button>
              <Button 
                variant="primary" 
                size="sm"
                onClick={handleSubmit} 
                disabled={isLoading || !apiKey.trim()}
                loading={isLoading}
              >
                {connectionValid ? 'Continue to Repositories' : 'Test & Continue'}
              </Button>
            </div>
          </div>
        </form>
        
        {!sessionKey && !connectionValid && (
          <div className="mt-4 pt-4 border-t border-charcoal-700">
            <p className="text-xs text-charcoal-400 text-center">
              Alternatively, you can set the <code className="bg-charcoal-900 px-1 rounded">GEMINI_API_KEY</code> environment variable before starting the backend.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};