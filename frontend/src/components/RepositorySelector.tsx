import React, { useState, useEffect } from 'react';
import { getRepositories } from '../api/endpoints';
import { Button } from './Common/Button';
import { OpenLocalFolderModal } from './OpenLocalFolderModal';
import { SourceExplorer } from './SourceExplorer';
import { Repository } from '../types/domain';
import { 
  FolderGit, 
  ChevronLeft, 
  Check, 
  Code, 
  Loader2, 
  AlertCircle, 
  FolderPlus, 
  ShieldAlert, 
  Sparkles,
  Laptop,
  FileCode,
  Eye,
  ShieldCheck
} from 'lucide-react';

interface RepositorySelectorProps {
  selectedRepositoryId?: string | null;
  onRepositorySelect: (id: string) => void;
  onContinue?: (id: string) => void;
  onFindBugs?: (id: string) => void;
  onBack: () => void;
  error: string | null;
}

export const RepositorySelector: React.FC<RepositorySelectorProps> = ({ 
  selectedRepositoryId,
  onRepositorySelect, 
  onContinue, 
  onFindBugs,
  onBack, 
  error 
}) => {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRepository, setSelectedRepository] = useState<string | null>(selectedRepositoryId || null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [explorerRepo, setExplorerRepo] = useState<Repository | null>(null);

  useEffect(() => {
    if (selectedRepositoryId) {
      setSelectedRepository(selectedRepositoryId);
    }
  }, [selectedRepositoryId]);

  const loadRepositories = async () => {
    try {
      setLoading(true);
      const response = await getRepositories();
      setRepositories(response.data.items);
    } catch (err) {
      console.error('Failed to load repositories:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRepositories();
  }, []);

  const handleOpenLocalSuccess = (newRepo: Repository) => {
    setRepositories((prev) => {
      const exists = prev.some((r) => r.id === newRepo.id);
      return exists ? prev.map((r) => (r.id === newRepo.id ? newRepo : r)) : [newRepo, ...prev];
    });
    setSelectedRepository(newRepo.id);
    onRepositorySelect(newRepo.id);
  };

  const getLanguageIcon = (language: string) => {
    switch (language) {
      case 'python':
        return <Code className="h-4 w-4 text-yellow-400" />;
      case 'javascript':
        return <Code className="h-4 w-4 text-yellow-500" />;
      case 'typescript':
        return <Code className="h-4 w-4 text-blue-400" />;
      case 'java':
        return <Code className="h-4 w-4 text-red-400" />;
      default:
        return <Code className="h-4 w-4 text-charcoal-400" />;
    }
  };

  if (loading) {
    return (
      <div className="text-center py-8">
        <Loader2 className="h-8 w-8 text-blue-500 animate-spin mx-auto" />
        <p className="mt-2 text-charcoal-400">Loading repositories...</p>
      </div>
    );
  }

  const localRepos = repositories.filter((r) => !r.is_fixture && !r.id.startsWith('repo_py_'));
  const demoRepos = repositories.filter((r) => r.is_fixture || r.id.startsWith('repo_py_'));

  const selectedRepoObj = repositories.find((r) => r.id === selectedRepository);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-blue-400 flex items-center gap-2">
            <FolderGit className="h-6 w-6" />
            Select Repository
          </h2>
          <p className="text-xs text-charcoal-400 mt-0.5">
            Choose a bundled demo fixture or open a local project folder
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="primary" 
            size="sm" 
            onClick={() => setIsModalOpen(true)}
            className="flex-shrink-0"
          >
            <FolderPlus className="h-4 w-4 mr-1.5" />
            Open Local Folder
          </Button>
          <Button variant="secondary" onClick={onBack} size="sm">
            <ChevronLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
        </div>
      </div>
      
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-600/10 border border-red-600/20 rounded-lg text-sm text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {selectedRepoObj && selectedRepoObj.execution_allowed === false && (
        <div className="p-3 bg-yellow-600/15 border border-yellow-600/30 rounded-lg flex items-start gap-2.5 text-xs text-yellow-300">
          <ShieldAlert className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-yellow-200">Execution Restricted on Host: </span>
            Docker is unavailable on this machine. You can inspect project files and layouts, but arbitrary test execution is blocked for your security.
          </div>
        </div>
      )}

      {selectedRepoObj && selectedRepoObj.execution_allowed && !selectedRepoObj.is_fixture && (
        <div className="p-3 bg-emerald-600/15 border border-emerald-600/30 rounded-lg flex items-start gap-2.5 text-xs text-emerald-300">
          <ShieldCheck className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-emerald-200">Isolated Container Execution Active: </span>
            Docker sandbox is operational. Automated test execution and repair runs will occur inside an isolated ephemeral container with no host access.
          </div>
        </div>
      )}

      {/* Group 1: User-Selected Local Repositories */}
      {localRepos.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-charcoal-400 flex items-center gap-1.5">
              <Laptop className="h-3.5 w-3.5 text-blue-400" />
              Your Local Repositories
            </h3>
            <span className="text-[11px] text-charcoal-500">{localRepos.length} loaded</span>
          </div>
          <div className="space-y-2">
            {localRepos.map((repo) => (
              <div 
                key={repo.id}
                className={`cursor-pointer p-4 border rounded-lg transition-all ${
                  selectedRepository === repo.id 
                    ? 'border-blue-500 bg-charcoal-700/60 shadow-md ring-1 ring-blue-500/30' 
                    : 'border-charcoal-700 hover:border-charcoal-600 hover:bg-charcoal-800/40'
                }`}
                onClick={() => {
                  setSelectedRepository(repo.id);
                  onRepositorySelect(repo.id);
                }}
              >
                <div className="flex items-center gap-4">
                  <div className="h-10 w-10 bg-charcoal-900 rounded-lg flex items-center justify-center flex-shrink-0 border border-charcoal-800">
                    {getLanguageIcon(repo.language)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-charcoal-100 truncate">{repo.name}</p>
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
                        Local
                      </span>
                      {repo.layout_status === 'no_tests' ? (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                          No Tests
                        </span>
                      ) : (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                          Supported
                        </span>
                      )}
                      {repo.execution_allowed === false ? (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                          Inspection Only
                        </span>
                      ) : (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/30">
                          Docker Sandboxed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="text-xs text-charcoal-400 flex items-center gap-1">
                        {getLanguageIcon(repo.language)}
                        {repo.language}
                      </span>
                      <span className="text-xs text-charcoal-400 bg-charcoal-900 px-2 py-0.5 rounded border border-charcoal-800">
                        {repo.test_framework === 'unknown' ? 'No test runner' : repo.test_framework}
                      </span>
                      {repo.file_count !== undefined && (
                        <span className="text-xs text-charcoal-500">
                          {repo.file_count} files
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExplorerRepo(repo);
                      }}
                      className="px-2.5 py-1 text-xs rounded bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-300 hover:text-white border border-charcoal-700 flex items-center gap-1 transition-colors"
                      title="Browse repository files in code viewer"
                    >
                      <FileCode className="h-3.5 w-3.5 text-blue-400" />
                      <span>Browse Source</span>
                    </button>
                    {selectedRepository === repo.id && (
                      <Check className="h-5 w-5 text-blue-400 flex-shrink-0" />
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Group 2: Demo Repositories (Bundled Fixtures) */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-charcoal-400 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-yellow-400" />
              Demo Repositories
            </h3>
            <p className="text-[11px] text-charcoal-500">
              Bundled fixtures authorized for restricted host execution without Docker
            </p>
          </div>
          <span className="text-[11px] text-charcoal-500">{demoRepos.length} available</span>
        </div>
        <div className="space-y-2">
          {demoRepos.map((repo) => (
            <div 
              key={repo.id}
              className={`cursor-pointer p-4 border rounded-lg transition-all ${
                selectedRepository === repo.id 
                  ? 'border-blue-500 bg-charcoal-700/60 shadow-md ring-1 ring-blue-500/30' 
                  : 'border-charcoal-700 hover:border-charcoal-600 hover:bg-charcoal-800/40'
              }`}
              onClick={() => {
                setSelectedRepository(repo.id);
                onRepositorySelect(repo.id);
              }}
            >
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 bg-charcoal-900 rounded-lg flex items-center justify-center flex-shrink-0 border border-charcoal-800">
                  {getLanguageIcon(repo.language)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-charcoal-100 truncate">{repo.name}</p>
                    <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      Demo Fixture
                    </span>
                    <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400 border border-blue-500/30">
                      Ready for Repair
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    <span className="text-xs text-charcoal-400 flex items-center gap-1">
                      {getLanguageIcon(repo.language)}
                      {repo.language}
                    </span>
                    <span className="text-xs text-charcoal-400 bg-charcoal-900 px-2 py-0.5 rounded border border-charcoal-800">
                      {repo.test_framework}
                    </span>
                    {repo.file_count !== undefined && (
                      <span className="text-xs text-charcoal-500">
                        {repo.file_count} files
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setExplorerRepo(repo);
                    }}
                    className="px-2.5 py-1 text-xs rounded bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-300 hover:text-white border border-charcoal-700 flex items-center gap-1 transition-colors"
                    title="Browse fixture source files in code viewer"
                  >
                    <FileCode className="h-3.5 w-3.5 text-blue-400" />
                    <span>Browse Source</span>
                  </button>
                  {selectedRepository === repo.id && (
                    <Check className="h-5 w-5 text-blue-400 flex-shrink-0" />
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
      
      <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-charcoal-700">
        <div className="text-xs text-charcoal-400">
          {selectedRepoObj ? (
            <span>Selected: <strong className="text-charcoal-200">{selectedRepoObj.name}</strong> ({selectedRepoObj.language})</span>
          ) : (
            <span>Please select a repository to proceed</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {onFindBugs && (
            <Button 
              variant="secondary" 
              onClick={() => {
                if (selectedRepository) {
                  onRepositorySelect(selectedRepository);
                  onFindBugs(selectedRepository);
                }
              }}
              disabled={!selectedRepository}
              size="md"
            >
              <Sparkles className="h-4 w-4 mr-1.5 text-blue-400" />
              Find Bugs
            </Button>
          )}
          <Button 
            variant="primary" 
            onClick={() => {
              if (selectedRepository) {
                onRepositorySelect(selectedRepository);
                if (onContinue) {
                  onContinue(selectedRepository);
                }
              }
            }}
            disabled={!selectedRepository}
            size="md"
          >
            Directed Repair
            <ChevronLeft className="h-4 w-4 ml-1 rotate-180" />
          </Button>
        </div>
      </div>

      <OpenLocalFolderModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={handleOpenLocalSuccess}
      />

      <SourceExplorer
        repository={explorerRepo}
        isOpen={!!explorerRepo}
        onClose={() => setExplorerRepo(null)}
      />
    </div>
  );
};