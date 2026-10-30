import React from 'react';
import { Badge } from './Common/Badge';
import { Button } from './Common/Button';
import { Shield, XCircle, FileText } from 'lucide-react';

interface NavbarProps {
  repositoryId: string | null;
  bugReport: string;
  testTarget: string;
  onCancel: () => void;
  status?: string;
  onViewReport?: () => void;
  isLoadingReport?: boolean;
}

export const Navbar = ({ repositoryId, bugReport, testTarget, onCancel, status, onViewReport, isLoadingReport }: NavbarProps) => {
  const isTerminal = ['verified', 'unresolved', 'failed', 'cancelled'].includes(status || '');

  return (
    <div className="border-b border-charcoal-700 pb-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex flex-col gap-2">
          {repositoryId && (
            <div className="flex items-center gap-3">
              <Shield className="h-4 w-4 text-blue-500 flex-shrink-0" />
              <span className="text-sm text-charcoal-400">Repository: {repositoryId}</span>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <p className="text-xs text-charcoal-400">Bug Report:</p>
            <p className="break-all text-xs text-charcoal-300">{bugReport}</p>
          </div>
          {testTarget && testTarget !== '[object Object]' && testTarget !== 'undefined' && testTarget !== 'null' && (
            <div className="flex flex-col gap-1">
              <p className="text-xs text-charcoal-400">Test Target:</p>
              <p className="break-all text-xs text-charcoal-300">{testTarget}</p>
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-3">
          {status && (
            <Badge variant={status as any}>
              {status}
            </Badge>
          )}
          {isTerminal && onViewReport ? (
            <Button variant="primary" size="sm" onClick={onViewReport} disabled={isLoadingReport}>
              <FileText className="h-4 w-4 mr-1" />
              {isLoadingReport ? 'Loading...' : 'View Final Report'}
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={onCancel} disabled={isTerminal}>
              <XCircle className="h-4 w-4 mr-1" />
              Cancel Repair
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};