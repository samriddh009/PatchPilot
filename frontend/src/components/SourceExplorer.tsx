import React, { useState, useEffect, useMemo } from 'react';
import { 
  Folder, 
  FolderOpen, 
  FileCode, 
  FileText, 
  Search, 
  X, 
  Copy, 
  Check, 
  AlertCircle, 
  Lock, 
  RefreshCw, 
  FileQuestion,
  ChevronRight,
  ChevronDown,
  Layers,
  ShieldCheck
} from 'lucide-react';
import { api } from '../api/client';
import { Repository, RepositoryFileContent } from '../types/domain';

interface SourceExplorerProps {
  repository: Repository | null;
  isOpen: boolean;
  onClose: () => void;
}

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children?: TreeNode[];
}

export const SourceExplorer: React.FC<SourceExplorerProps> = ({
  repository,
  isOpen,
  onClose,
}) => {
  const [files, setFiles] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<RepositoryFileContent | null>(null);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});

  // Fetch safe file list whenever repository changes or modal opens
  useEffect(() => {
    if (isOpen && repository) {
      loadFiles();
    } else {
      setSelectedFile(null);
      setFileContent(null);
      setContentError(null);
    }
  }, [isOpen, repository?.id]);

  const loadFiles = async () => {
    if (!repository) return;
    try {
      setIsLoadingFiles(true);
      const res = await api.getRepositoryFiles(repository.id, true);
      const fileList: string[] = res.data?.files || [];
      setFiles(fileList);

      // Auto-expand root directories
      const initialExpanded: Record<string, boolean> = {};
      fileList.forEach((f) => {
        const parts = f.split('/');
        if (parts.length > 1) {
          initialExpanded[parts[0]] = true;
        }
      });
      setExpandedDirs(initialExpanded);

      // Auto-select first source file if none selected
      if (!selectedFile && fileList.length > 0) {
        const firstSource = fileList.find((f) => !f.startsWith('test') && !f.includes('/test')) || fileList[0];
        handleSelectFile(firstSource);
      }
    } catch (err: any) {
      console.error('Failed to load files:', err);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const handleSelectFile = async (path: string) => {
    if (!repository) return;
    setSelectedFile(path);
    setIsLoadingContent(true);
    setContentError(null);
    try {
      const res = await api.getRepositoryFile(repository.id, path);
      setFileContent(res.data);
    } catch (err: any) {
      const msg =
        err?.response?.data?.error?.message ||
        err?.response?.data?.detail?.message ||
        'Unable to display file content.';
      setContentError(msg);
      setFileContent(null);
    } finally {
      setIsLoadingContent(false);
    }
  };

  const handleCopy = () => {
    if (!fileContent?.content) return;
    navigator.clipboard.writeText(fileContent.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleDir = (dirPath: string) => {
    setExpandedDirs((prev) => ({
      ...prev,
      [dirPath]: !prev[dirPath],
    }));
  };

  // Build directory tree
  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return files;
    const q = searchQuery.toLowerCase();
    return files.filter((f) => f.toLowerCase().includes(q));
  }, [files, searchQuery]);

  const tree = useMemo(() => {
    const root: TreeNode = { name: '', path: '', isDir: true, children: [] };

    filteredFiles.forEach((file) => {
      const parts = file.split('/');
      let current = root;

      parts.forEach((part, index) => {
        const isLast = index === parts.length - 1;
        const currentPath = parts.slice(0, index + 1).join('/');

        if (isLast) {
          current.children = current.children || [];
          current.children.push({
            name: part,
            path: currentPath,
            isDir: false,
          });
        } else {
          current.children = current.children || [];
          let dirNode = current.children.find((c) => c.isDir && c.name === part);
          if (!dirNode) {
            dirNode = {
              name: part,
              path: currentPath,
              isDir: true,
              children: [],
            };
            current.children.push(dirNode);
          }
          current = dirNode;
        }
      });
    });

    const sortNodes = (nodes: TreeNode[]) => {
      nodes.sort((a, b) => {
        if (a.isDir && !b.isDir) return -1;
        if (!a.isDir && b.isDir) return 1;
        return a.name.localeCompare(b.name);
      });
      nodes.forEach((n) => {
        if (n.children) sortNodes(n.children);
      });
    };

    if (root.children) sortNodes(root.children);
    return root.children || [];
  }, [filteredFiles]);

  if (!isOpen || !repository) return null;

  const renderTree = (nodes: TreeNode[], depth: number = 0) => {
    return nodes.map((node) => {
      if (node.isDir) {
        const isExpanded = expandedDirs[node.path] ?? false;
        return (
          <div key={node.path} className="select-none">
            <button
              onClick={() => toggleDir(node.path)}
              className="flex items-center gap-1.5 w-full py-1 px-2 text-xs text-charcoal-300 hover:text-white hover:bg-charcoal-800 rounded transition-colors text-left"
              style={{ paddingLeft: `${depth * 12 + 8}px` }}
            >
              {isExpanded ? (
                <ChevronDown className="h-3.5 w-3.5 text-charcoal-400 shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-charcoal-400 shrink-0" />
              )}
              {isExpanded ? (
                <FolderOpen className="h-3.5 w-3.5 text-amber-400 shrink-0" />
              ) : (
                <Folder className="h-3.5 w-3.5 text-amber-500 shrink-0" />
              )}
              <span className="font-mono truncate">{node.name}</span>
            </button>
            {isExpanded && node.children && (
              <div>{renderTree(node.children, depth + 1)}</div>
            )}
          </div>
        );
      }

      const isSelected = selectedFile === node.path;
      const isTest = node.path.includes('test') || node.name.includes('_test') || node.name.includes('.test.');
      const isConfig =
        node.name.endsWith('.toml') ||
        node.name.endsWith('.json') ||
        node.name.endsWith('.yaml') ||
        node.name.endsWith('.xml') ||
        node.name.endsWith('.ini');

      return (
        <button
          key={node.path}
          onClick={() => handleSelectFile(node.path)}
          className={`flex items-center justify-between w-full py-1 px-2 text-xs rounded transition-colors text-left ${
            isSelected
              ? 'bg-blue-600/20 text-blue-300 font-medium border border-blue-500/30'
              : 'text-charcoal-300 hover:text-white hover:bg-charcoal-800'
          }`}
          style={{ paddingLeft: `${depth * 12 + 20}px` }}
        >
          <div className="flex items-center gap-1.5 truncate">
            {isTest ? (
              <FileCode className="h-3.5 w-3.5 text-green-400 shrink-0" />
            ) : isConfig ? (
              <FileText className="h-3.5 w-3.5 text-purple-400 shrink-0" />
            ) : (
              <FileCode className="h-3.5 w-3.5 text-blue-400 shrink-0" />
            )}
            <span className="font-mono truncate">{node.name}</span>
          </div>
          {isTest && (
            <span className="ml-1 text-[9px] uppercase px-1 py-0.2 rounded bg-green-950/80 text-green-400 border border-green-800 shrink-0">
              test
            </span>
          )}
        </button>
      );
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-charcoal-950/80 backdrop-blur-sm animate-fade-in">
      <div 
        className="w-full max-w-6xl h-[88vh] bg-charcoal-900 border border-charcoal-700 rounded-xl shadow-2xl flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="explorer-title"
      >
        {/* Top Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-charcoal-800 bg-charcoal-950/50">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 rounded-md text-blue-400">
              <Layers className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="explorer-title" className="text-sm font-semibold text-white">
                  Source Explorer — {repository.name}
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded uppercase font-semibold bg-charcoal-800 text-charcoal-300 border border-charcoal-700">
                  {repository.language}
                </span>
                {repository.is_fixture ? (
                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                    Demo Fixture
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded font-semibold bg-blue-950/80 text-blue-400 border border-blue-800">
                    Local Repository
                  </span>
                )}
              </div>
              <p className="text-[11px] text-charcoal-400">
                Safe static in-app code inspection. Sensitive files and build artifacts are strictly excluded.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadFiles}
              className="p-1.5 text-charcoal-400 hover:text-white hover:bg-charcoal-800 rounded transition-colors"
              title="Refresh files"
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingFiles ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-charcoal-400 hover:text-white hover:bg-charcoal-800 rounded transition-colors"
              title="Close Explorer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content Body: Left File Tree + Right Code View */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel: Files and Search */}
          <div className="w-72 sm:w-80 border-r border-charcoal-800 flex flex-col bg-charcoal-900/60">
            {/* Search Box */}
            <div className="p-3 border-b border-charcoal-800">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-charcoal-400" />
                <input
                  type="text"
                  placeholder="Filter files..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-charcoal-950 border border-charcoal-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-charcoal-200 placeholder-charcoal-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            {/* Tree Container */}
            <div className="flex-1 overflow-y-auto p-2">
              {isLoadingFiles ? (
                <div className="p-6 text-center text-xs text-charcoal-400">
                  <RefreshCw className="h-4 w-4 animate-spin mx-auto mb-2 text-blue-400" />
                  Scanning safe project files...
                </div>
              ) : tree.length === 0 ? (
                <div className="p-6 text-center text-xs text-charcoal-400">
                  <FileQuestion className="h-5 w-5 mx-auto mb-2 text-charcoal-500" />
                  No matching files found.
                </div>
              ) : (
                <div className="space-y-0.5">{renderTree(tree)}</div>
              )}
            </div>

            {/* Tree Footer */}
            <div className="p-2.5 border-t border-charcoal-800 bg-charcoal-950/40 text-[11px] text-charcoal-400 flex items-center justify-between">
              <span className="flex items-center gap-1">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                {files.length} safe files scanned
              </span>
              <span className="text-[10px] text-charcoal-400">.env & credentials hidden</span>
            </div>
          </div>

          {/* Right Panel: Code Viewer */}
          <div className="flex-1 flex flex-col bg-charcoal-950 overflow-hidden">
            {selectedFile ? (
              <>
                {/* File Sub-header */}
                <div className="flex items-center justify-between px-4 py-2 border-b border-charcoal-800 bg-charcoal-900/40 text-xs">
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-mono text-charcoal-200 truncate">{selectedFile}</span>
                    {fileContent && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-charcoal-800 text-charcoal-400 font-mono">
                        {fileContent.total_lines} lines
                      </span>
                    )}
                    {fileContent?.language && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-400 font-mono">
                        {fileContent.language}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopy}
                      disabled={!fileContent?.content}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-300 hover:text-white transition-colors border border-charcoal-700"
                    >
                      {copied ? (
                        <>
                          <Check className="h-3 w-3 text-emerald-400" />
                          <span className="text-emerald-400 text-[11px]">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 text-charcoal-400" />
                          <span className="text-[11px]">Copy Code</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Code Body */}
                <div className="flex-1 overflow-auto p-4 font-mono text-xs text-charcoal-200">
                  {isLoadingContent ? (
                    <div className="h-full flex items-center justify-center text-charcoal-400 text-xs">
                      <RefreshCw className="h-5 w-5 animate-spin mr-2 text-blue-400" />
                      Loading file content...
                    </div>
                  ) : contentError ? (
                    <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                      <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-full text-red-400 mb-3">
                        <Lock className="h-6 w-6" />
                      </div>
                      <h4 className="text-sm font-semibold text-white mb-1">Access Restricted</h4>
                      <p className="text-xs text-charcoal-400 max-w-md">{contentError}</p>
                    </div>
                  ) : fileContent?.content ? (
                    <div className="flex">
                      {/* Line Numbers */}
                      <div className="select-none pr-4 text-right text-charcoal-600 border-r border-charcoal-800 font-mono text-xs">
                        {fileContent.content.split('\n').map((_, i) => (
                          <div key={i} className="leading-5">
                            {fileContent.offset_line + i}
                          </div>
                        ))}
                      </div>
                      {/* Code Lines */}
                      <div className="pl-4 flex-1 overflow-x-auto">
                        <pre className="font-mono text-xs leading-5 text-charcoal-100 whitespace-pre">
                          {fileContent.content}
                        </pre>
                      </div>
                    </div>
                  ) : (
                    <div className="text-charcoal-400 italic">Empty file.</div>
                  )}
                </div>
              </>
            ) : (
              <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                <FileCode className="h-8 w-8 text-charcoal-600 mb-2" />
                <h4 className="text-sm font-medium text-charcoal-300 mb-1">Select a File to View</h4>
                <p className="text-xs text-charcoal-400 max-w-sm">
                  Choose any source file, configuration, or test from the tree to inspect its contents.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
