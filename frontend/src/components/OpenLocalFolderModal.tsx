import React, { useState } from 'react';
import { Button } from './Common/Button';
import { Repository } from '../types/domain';
import {
  FolderPlus,
  FolderSearch,
  X,
  AlertCircle,
  Loader2,
  CheckCircle2,
  Info,
  Shield,
  FileCode2,
  UploadCloud,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  projectAccessService,
  ProjectSelectionMetadata,
  DesktopProjectAdapter,
  WebProjectAdapter,
} from '../services/projectAccess';

interface OpenLocalFolderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (repo: Repository) => void;
}

export const OpenLocalFolderModal: React.FC<OpenLocalFolderModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [folderPath, setFolderPath] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stagedWebProject, setStagedWebProject] = useState<ProjectSelectionMetadata | null>(null);
  const [showManualEntry, setShowManualEntry] = useState(false);

  if (!isOpen) return null;

  const isDesktop = projectAccessService.isDesktop();
  const desktopAdapter = new DesktopProjectAdapter();
  const webAdapter = new WebProjectAdapter();

  // Desktop Native Browse
  const handleDesktopBrowse = async () => {
    try {
      setIsBrowsing(true);
      setError(null);
      const res = await desktopAdapter.selectDirectory();
      if (res && !res.canceled && res.path) {
        setFolderPath(res.path);
        if (!displayName) {
          const parts = res.path.split(/[/\\]/);
          const last = parts[parts.length - 1];
          if (last) setDisplayName(last);
        }
      }
    } catch (err: any) {
      console.warn('Native folder browse error:', err);
      setError(err?.message || 'Failed to open native Windows folder dialog.');
    } finally {
      setIsBrowsing(false);
    }
  };

  // Web Browser Folder Selection (window.showDirectoryPicker with webkitdirectory fallback)
  const handleWebBrowse = async () => {
    try {
      setIsBrowsing(true);
      setError(null);

      let metadata: ProjectSelectionMetadata | null = null;
      if (webAdapter.hasDirectoryPicker()) {
        try {
          metadata = await webAdapter.selectWithDirectoryPicker();
        } catch (pickerErr: any) {
          // If permission denied or user dismissed without AbortError, fallback to file input
          if (pickerErr.name !== 'AbortError') {
            metadata = await webAdapter.selectWithFileInput();
          }
        }
      } else {
        metadata = await webAdapter.selectWithFileInput();
      }

      if (metadata) {
        if (metadata.fileCount === 0) {
          setError('Selected folder contains no supported source files or all files were excluded.');
          setStagedWebProject(null);
        } else {
          setStagedWebProject(metadata);
          if (!displayName) {
            setDisplayName(metadata.folderName);
          }
        }
      }
    } catch (err: any) {
      console.warn('Web folder browse error:', err);
      setError(err?.message || 'Failed to select folder in browser.');
    } finally {
      setIsBrowsing(false);
    }
  };

  // Submit Staged Web Project Ingestion
  const handleIngestWebProject = async () => {
    if (!stagedWebProject) return;

    try {
      setIsLoading(true);
      setError(null);
      const repo = await projectAccessService.ingestWebProject({
        ...stagedWebProject,
        name: displayName.trim() || stagedWebProject.name,
      });
      onSuccess(repo);
      onClose();
    } catch (err: any) {
      const errorObj = err?.response?.data?.error || err?.response?.data?.detail || err?.response?.data;
      const errorMsg =
        errorObj?.message ||
        (typeof errorObj === 'string' ? errorObj : null) ||
        err?.message ||
        'Failed to ingest project files.';
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  // Submit Local / Manual Path Registration
  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanPath = folderPath.trim().replace(/^["']|["']$/g, '');
    if (!cleanPath) {
      setError('Please provide a project folder path.');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      const repo = await projectAccessService.registerLocalPath(cleanPath, displayName.trim() || undefined);
      onSuccess(repo);
      onClose();
    } catch (err: any) {
      const errorObj = err?.response?.data?.error || err?.response?.data?.detail || err?.response?.data;
      const errorMsg =
        errorObj?.message ||
        (typeof errorObj === 'string' ? errorObj : null) ||
        err?.message ||
        'Failed to open local repository.';
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-charcoal-950/80 backdrop-blur-sm animate-fade-in">
      <div 
        className="w-full max-w-lg bg-charcoal-900 border border-charcoal-700 rounded-xl shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-charcoal-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 border border-blue-500/20 rounded-lg text-blue-400">
              <FolderPlus className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="modal-title" className="text-lg font-semibold text-charcoal-50">
                  Open Project Folder
                </h3>
                <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${
                  isDesktop 
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                }`}>
                  {isDesktop ? 'Desktop App' : 'Browser Mode'}
                </span>
              </div>
              <p className="text-xs text-charcoal-400">
                {isDesktop 
                  ? 'Select your project directory via native Windows dialog'
                  : 'Select your local project folder to inspect and repair in browser'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-charcoal-400 hover:text-charcoal-200 p-1.5 rounded-lg hover:bg-charcoal-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-2.5 text-xs text-red-300">
              <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="leading-relaxed">{error}</div>
            </div>
          )}

          {/* DESKTOP MODE: Native Windows Explorer Dialog */}
          {isDesktop ? (
            <form onSubmit={handleManualSubmit} className="space-y-4">
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/25 rounded-lg flex items-start gap-2.5 text-xs text-emerald-300">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <div className="leading-relaxed">
                  <span className="font-semibold text-emerald-200">Native Windows Folder Dialog Active: </span>
                  Click <strong>Browse…</strong> to open your project with Windows Explorer.
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="repository-path-input" className="text-xs font-medium text-charcoal-200">
                  Project Folder Path <span className="text-red-400">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    id="repository-path-input"
                    type="text"
                    aria-label="Project Folder Path"
                    value={folderPath}
                    onChange={(e) => setFolderPath(e.target.value)}
                    placeholder="e.g. C:\projects\my-app"
                    className="flex-1 input font-mono text-xs text-charcoal-100 placeholder:text-charcoal-500"
                    disabled={isLoading}
                    autoFocus
                  />
                  <Button
                    type="button"
                    id="browse-folder-button"
                    variant="secondary"
                    size="md"
                    onClick={handleDesktopBrowse}
                    disabled={isLoading || isBrowsing}
                    title="Open native Windows folder dialog"
                    className="flex-shrink-0"
                  >
                    {isBrowsing ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                        <span>Browsing…</span>
                      </>
                    ) : (
                      <>
                        <FolderSearch className="h-4 w-4 mr-1.5 text-emerald-400" />
                        <span>Browse…</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-charcoal-200">
                  Display Name <span className="text-charcoal-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Defaults to folder name"
                  className="w-full input text-xs text-charcoal-100 placeholder:text-charcoal-500"
                  disabled={isLoading}
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-charcoal-800">
                <Button type="button" variant="secondary" size="md" onClick={onClose} disabled={isLoading}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="md" disabled={isLoading || !folderPath.trim()}>
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Opening…
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4 mr-1.5" />
                      Open Repository
                    </>
                  )}
                </Button>
              </div>
            </form>
          ) : (
            /* BROWSER MODE: Progressive Enhancement (Directory Picker + Ingestion) */
            <div className="space-y-4">
              {!stagedWebProject ? (
                <div className="space-y-4">
                  <div className="p-4 border-2 border-dashed border-charcoal-700 hover:border-blue-500/50 rounded-xl bg-charcoal-800/50 transition-colors flex flex-col items-center justify-center p-6 text-center space-y-3">
                    <div className="p-3 bg-blue-500/10 text-blue-400 rounded-full">
                      <UploadCloud className="h-8 w-8" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-charcoal-100">Select Project Folder</h4>
                      <p className="text-xs text-charcoal-400 mt-1 max-w-sm">
                        Use your browser's folder chooser to select any local project folder. No path typing required.
                      </p>
                    </div>
                    <Button
                      type="button"
                      id="browse-folder-button"
                      variant="primary"
                      size="md"
                      onClick={handleWebBrowse}
                      disabled={isBrowsing || isLoading}
                      className="px-6"
                    >
                      {isBrowsing ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Scanning Folder…
                        </>
                      ) : (
                        <>
                          <FolderSearch className="h-4 w-4 mr-2" />
                          Browse Project Folder…
                        </>
                      )}
                    </Button>
                    <p className="text-[11px] text-charcoal-500">
                      Supports Python (.py), TypeScript (.ts/.tsx), JavaScript (.js/.jsx), Java (.java).
                    </p>
                  </div>

                  {/* Collapsible Manual Path Option for local developers */}
                  <div className="pt-2 border-t border-charcoal-800">
                    <button
                      type="button"
                      onClick={() => setShowManualEntry(!showManualEntry)}
                      className="text-xs text-charcoal-400 hover:text-charcoal-200 flex items-center justify-between w-full py-1"
                    >
                      <span>Or enter filesystem path manually (local host backend)</span>
                      {showManualEntry ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>

                    {showManualEntry && (
                      <form onSubmit={handleManualSubmit} className="mt-3 space-y-3">
                        <input
                          id="repository-path-input"
                          type="text"
                          value={folderPath}
                          onChange={(e) => setFolderPath(e.target.value)}
                          placeholder="e.g. fixtures/python_calc_bug or C:\projects\my-app"
                          className="w-full input font-mono text-xs text-charcoal-100"
                          disabled={isLoading}
                        />
                        <div className="flex justify-end gap-2">
                          <Button type="submit" variant="secondary" size="sm" disabled={isLoading || !folderPath.trim()}>
                            {isLoading ? 'Registering…' : 'Open Path'}
                          </Button>
                        </div>
                      </form>
                    )}
                  </div>
                </div>
              ) : (
                /* STAGED PROJECT CONFIRMATION & DISCLOSURE */
                <div className="space-y-4">
                  <div className="p-4 bg-charcoal-800 border border-charcoal-700 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <FileCode2 className="h-5 w-5 text-blue-400" />
                        <div>
                          <h4 className="text-sm font-semibold text-charcoal-100">{stagedWebProject.folderName}</h4>
                          <p className="text-xs text-charcoal-400">
                            {stagedWebProject.fileCount} source files staged
                            {stagedWebProject.excludedCount > 0 && ` (${stagedWebProject.excludedCount} files excluded)`}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setStagedWebProject(null)}
                        className="text-xs text-blue-400 hover:text-blue-300 underline"
                      >
                        Change Folder
                      </button>
                    </div>

                    {/* Detected Languages */}
                    {stagedWebProject.detectedLanguages.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {stagedWebProject.detectedLanguages.map((lang) => (
                          <span
                            key={lang}
                            className="px-2 py-0.5 text-[10px] font-semibold bg-blue-500/15 border border-blue-500/30 text-blue-300 rounded"
                          >
                            {lang}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Optional Display Name */}
                    <div className="pt-2 border-t border-charcoal-700/60 space-y-1">
                      <label className="text-[11px] font-medium text-charcoal-300">
                        Display Name (Optional)
                      </label>
                      <input
                        type="text"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        placeholder={stagedWebProject.folderName}
                        className="w-full input text-xs text-charcoal-100"
                        disabled={isLoading}
                      />
                    </div>
                  </div>

                  {/* Privacy & Ingestion Disclosure */}
                  <div className="p-3 bg-blue-500/10 border border-blue-500/25 rounded-lg flex items-start gap-2.5 text-xs text-blue-200">
                    <Shield className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
                    <div className="leading-relaxed">
                      <span className="font-semibold text-blue-100">Privacy & Data Flow Disclosure: </span>
                      Selected source files will be ingested into an isolated workspace on the PatchPilot backend service. 
                      If Gemini AI is enabled with your API key, relevant diagnostic code snippets may be sent to Google's 
                      Gemini API for analysis and repairs. Local secrets (<code className="text-blue-300">.env</code>, private keys) 
                      and dependencies (<code className="text-blue-300">.git</code>, <code className="text-blue-300">node_modules</code>, <code className="text-blue-300">.venv</code>) 
                      are strictly excluded.
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-charcoal-800">
                    <Button
                      type="button"
                      variant="secondary"
                      size="md"
                      onClick={() => setStagedWebProject(null)}
                      disabled={isLoading}
                    >
                      Back
                    </Button>
                    <Button
                      type="button"
                      variant="primary"
                      size="md"
                      onClick={handleIngestWebProject}
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Ingesting & Opening…
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="h-4 w-4 mr-1.5" />
                          Ingest & Open Project
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
