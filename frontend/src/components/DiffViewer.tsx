import React from 'react';
import { FileCode, Minus, Plus, FileText } from 'lucide-react';

interface DiffViewerProps {
  diff: string;
  hasDiff: boolean;
}

interface ParsedFile {
  path: string;
  hunks: ParsedHunk[];
}

interface ParsedHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
}

interface DiffLine {
  type: 'context' | 'add' | 'remove' | 'header';
  content: string;
  oldLineNum?: number;
  newLineNum?: number;
}

const parseDiff = (diff: string): ParsedFile[] => {
  const files: ParsedFile[] = [];
  const lines = diff.split('\n');
  
  let currentFile: ParsedFile | null = null;
  let currentHunk: ParsedHunk | null = null;
  let oldLineNum = 0;
  let newLineNum = 0;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // File header
    if (line.startsWith('--- a/') || line.startsWith('+++ b/')) {
      if (line.startsWith('--- a/')) {
        const path = line.substring(6);
        if (currentFile) {
          files.push(currentFile);
        }
        currentFile = { path, hunks: [] };
        currentHunk = null;
      }
      continue;
    }
    
    // Hunk header
    const hunkMatch = line.match(/^@@ -(\d+),(\d+) \+(\d+),(\d+) @@/);
    if (hunkMatch && currentFile) {
      if (currentHunk) {
        currentFile.hunks.push(currentHunk);
      }
      oldLineNum = parseInt(hunkMatch[1], 10) - 1;
      newLineNum = parseInt(hunkMatch[3], 10) - 1;
      currentHunk = {
        oldStart: parseInt(hunkMatch[1], 10),
        oldLines: parseInt(hunkMatch[2], 10),
        newStart: parseInt(hunkMatch[3], 10),
        newLines: parseInt(hunkMatch[4], 10),
        lines: [],
      };
      currentHunk.lines.push({ type: 'header', content: line });
      continue;
    }
    
    // Diff lines
    if (currentHunk && currentFile) {
      if (line.startsWith('+')) {
        newLineNum++;
        currentHunk.lines.push({ 
          type: 'add', 
          content: line.substring(1), 
          newLineNum 
        });
      } else if (line.startsWith('-')) {
        oldLineNum++;
        currentHunk.lines.push({ 
          type: 'remove', 
          content: line.substring(1), 
          oldLineNum 
        });
      } else if (line.startsWith(' ')) {
        oldLineNum++;
        newLineNum++;
        currentHunk.lines.push({ 
          type: 'context', 
          content: line.substring(1), 
          oldLineNum, 
          newLineNum 
        });
      } else {
        // Empty line or other
        currentHunk.lines.push({ type: 'context', content: line });
      }
    }
  }
  
  if (currentHunk && currentFile) {
    currentFile.hunks.push(currentHunk);
  }
  if (currentFile) {
    files.push(currentFile);
  }
  
  return files;
};

export const DiffViewer = ({ diff, hasDiff }: DiffViewerProps) => {
  if (!hasDiff || !diff.trim()) {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
          <FileCode className="h-5 w-5" />
          Code Changes
        </h3>
        <div className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-8 text-center">
          <FileText className="h-12 w-12 text-charcoal-600 mx-auto mb-3" />
          <p className="text-charcoal-400">No diff available yet.</p>
          <p className="text-xs text-charcoal-500 mt-1">Diff will appear here when a patch is generated.</p>
        </div>
      </div>
    );
  }

  const files = parseDiff(diff);
  
  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
        <FileCode className="h-5 w-5" />
        Code Changes
      </h3>
      
      <div className="bg-charcoal-900 border border-charcoal-800 rounded-lg overflow-hidden">
        {files.map((file, fileIndex) => (
          <div key={fileIndex} className="border-b border-charcoal-800 last:border-b-0">
            {/* File header */}
            <div className="bg-charcoal-800 border-b border-charcoal-700 px-4 py-2 flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-400" />
              <span className="font-medium text-charcoal-100">{file.path}</span>
              <span className="text-xs text-charcoal-500 ml-auto">
                {file.hunks.reduce((acc, hunk) => acc + hunk.lines.filter(l => l.type === 'add').length, 0)} additions, 
                {file.hunks.reduce((acc, hunk) => acc + hunk.lines.filter(l => l.type === 'remove').length, 0)} deletions
              </span>
            </div>
            
            {/* Hunks */}
            <div className="p-4 font-mono text-sm overflow-auto max-h-[500px]">
              {file.hunks.map((hunk, hunkIndex) => (
                <div key={hunkIndex} className="space-y-1">
                  <div className="text-xs text-charcoal-500 px-2 py-1 bg-charcoal-800 rounded mb-2 font-normal">
                    @@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
                  </div>
                  {hunk.lines.map((line, lineIndex) => (
                    <div 
                      key={lineIndex}
                      className={`flex gap-3 px-2 py-0.5 ${
                        line.type === 'add' ? 'bg-green-600/10' : 
                        line.type === 'remove' ? 'bg-red-600/10' : 
                        'bg-transparent'
                      }`}
                    >
                      <span className={`w-8 text-right text-charcoal-500 select-none pr-2 ${line.type === 'remove' ? 'text-red-400' : ''}`}>
                        {line.oldLineNum !== undefined ? line.oldLineNum : ''}
                      </span>
                      <span className={`w-8 text-right text-charcoal-500 select-none pr-2 ${line.type === 'add' ? 'text-green-400' : ''}`}>
                        {line.newLineNum !== undefined ? line.newLineNum : ''}
                      </span>
                      <span 
                        className={`flex-1 whitespace-pre ${
                          line.type === 'add' ? 'text-green-400' : 
                          line.type === 'remove' ? 'text-red-400' : 
                          'text-charcoal-300'
                        }`}
                      >
                        {line.type === 'add' && <Plus className="h-3 w-3 inline-block mr-1 text-green-500" />}
                        {line.type === 'remove' && <Minus className="h-3 w-3 inline-block mr-1 text-red-500" />}
                        {line.type === 'context' && <span className="w-5 inline-block" />}
                        {line.content}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};