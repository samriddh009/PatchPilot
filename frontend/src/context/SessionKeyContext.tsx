import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';

interface SessionKeyContextValue {
  sessionKey: string | null;
  setSessionKey: (key: string) => void;
  clearSessionKey: () => void;
  selectedModel: string;
  setSelectedModel: (model: string) => void;
  availableModels: string[];
  setAvailableModels: (models: string[]) => void;
  isLiveDiscovered: boolean;
  setIsLiveDiscovered: (discovered: boolean) => void;
}

const SessionKeyContext = createContext<SessionKeyContextValue | undefined>(undefined);

export const SessionKeyProvider = ({ children }: { children: ReactNode }) => {
  const [sessionKey, setSessionKeyState] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>('gemini-1.5-flash');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isLiveDiscovered, setIsLiveDiscovered] = useState<boolean>(false);

  const setSessionKey = useCallback((key: string) => {
    setSessionKeyState(key);
  }, []);

  const clearSessionKey = useCallback(() => {
    setSessionKeyState(null);
    setAvailableModels([]);
    setIsLiveDiscovered(false);
  }, []);

  return (
    <SessionKeyContext.Provider value={{ 
      sessionKey, 
      setSessionKey, 
      clearSessionKey,
      selectedModel,
      setSelectedModel,
      availableModels,
      setAvailableModels,
      isLiveDiscovered,
      setIsLiveDiscovered,
    }}>
      {children}
    </SessionKeyContext.Provider>
  );
};

export const useSessionKeyContext = () => {
  const context = useContext(SessionKeyContext);
  if (!context) {
    throw new Error('useSessionKeyContext must be used within a SessionKeyProvider');
  }
  return context;
};