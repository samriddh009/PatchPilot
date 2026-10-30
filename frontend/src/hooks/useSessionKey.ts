import { useState, useEffect, useCallback } from 'react';
import { validateSessionKey, discoverModels, setModel } from '../api/endpoints';
import { setSessionKeyGetter } from '../api/client';
import { useSessionKeyContext } from '../context/SessionKeyContext';
import { pickSensibleModel } from '../utils/modelUtils';

export const useSessionKey = () => {
  const { 
    sessionKey, 
    setSessionKey: setSessionKeyContext, 
    clearSessionKey: clearSessionKeyContext,
    selectedModel,
    setSelectedModel: setSelectedModelContext,
    availableModels,
    setAvailableModels,
    isLiveDiscovered,
    setIsLiveDiscovered,
  } = useSessionKeyContext();

  const [connectionValid, setConnectionValid] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Set the session key getter for the API client
  useEffect(() => {
    setSessionKeyGetter(() => sessionKey);
  }, [sessionKey]);

  // Synchronize active model choice with backend
  const handleSetSelectedModel = useCallback((model: string) => {
    setSelectedModelContext(model);
    setModel(model).catch(() => {});
  }, [setSelectedModelContext]);

  // Discover models live from Google API for a given key
  const handleDiscoverModels = useCallback(async (keyToProbe?: string) => {
    const key = keyToProbe || sessionKey;
    if (!key) {
      setError('No API key provided to probe models.');
      return [];
    }
    try {
      setError(null);
      const res = await discoverModels(key);
      const discovered = res.data?.available_models;
      if (res.data?.is_live_discovered && Array.isArray(discovered) && discovered.length > 0) {
        setAvailableModels(discovered);
        setIsLiveDiscovered(true);
        // Automatically switch to sensible discovered model if current is not in the live list
        const sensible = pickSensibleModel(discovered, selectedModel);
        if (sensible !== selectedModel) {
          handleSetSelectedModel(sensible);
        }
        return discovered;
      }
      if (res.data?.error_detail) {
        setError(res.data.error_detail);
      }
      return [];
    } catch (err: any) {
      const errorObj = err.response?.data?.error || err.response?.data?.detail || err.response?.data || {};
      const msg =
        errorObj.message ||
        err.response?.data?.detail?.message ||
        err.message ||
        'Model discovery probe failed.';
      setError(msg);
      return [];
    }
  }, [sessionKey, selectedModel, handleSetSelectedModel, setAvailableModels, setIsLiveDiscovered]);

  // Test connection and discover available models
  const handleTestConnection = useCallback(async (customModel?: string, customKey?: string) => {
    const key = customKey || sessionKey;
    if (!key) {
      setError('No API key provided');
      return;
    }
    
    try {
      setIsTesting(true);
      setError(null);
      const modelToTest = customModel || selectedModel;
      const response = await validateSessionKey(key, modelToTest);
      setConnectionValid(response.data.valid);
      const discovered = response.data.available_models;
      if (Array.isArray(discovered) && discovered.length > 0) {
        setAvailableModels(discovered);
        setIsLiveDiscovered(true);
      }
      await setModel(modelToTest).catch(() => {});
    } catch (err: any) {
      setConnectionValid(false);
      const errorObj = err.response?.data?.error || err.response?.data?.detail || err.response?.data || {};
      const modelsFromError =
        errorObj.details?.available_models ||
        errorObj.available_models ||
        err.response?.data?.detail?.available_models;
      
      if (Array.isArray(modelsFromError) && modelsFromError.length > 0) {
        setAvailableModels(modelsFromError);
        setIsLiveDiscovered(true);
        // Switch to sensible discovered model so the next test or selection is valid
        if (!modelsFromError.includes(selectedModel)) {
          const sensible = pickSensibleModel(modelsFromError);
          handleSetSelectedModel(sensible);
        }
      }
      const msg =
        errorObj.message ||
        errorObj.details?.message ||
        err.response?.data?.detail?.message ||
        (typeof err.response?.data?.detail === 'string' ? err.response?.data?.detail : null) ||
        err.message ||
        'Connection test failed';
      setError(msg);
      throw err;
    } finally {
      setIsTesting(false);
    }
  }, [sessionKey, selectedModel, handleSetSelectedModel, setAvailableModels, setIsLiveDiscovered]);

  const handleSetSessionKey = useCallback((key: string) => {
    setSessionKeyContext(key);
    setError(null);
  }, [setSessionKeyContext]);

  const handleClearSessionKey = useCallback(() => {
    clearSessionKeyContext();
    setConnectionValid(false);
    setError(null);
  }, [clearSessionKeyContext]);

  return {
    sessionKey,
    setSessionKey: handleSetSessionKey,
    selectedModel,
    setSelectedModel: handleSetSelectedModel,
    availableModels,
    isLiveDiscovered,
    discoverModels: handleDiscoverModels,
    connectionValid,
    isTesting,
    error,
    testConnection: handleTestConnection,
    clearSessionKey: handleClearSessionKey,
  };
};