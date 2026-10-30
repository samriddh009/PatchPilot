import React from 'react';
import { Badge } from './Badge';

type RepairStatus = 
  | 'queued'
  | 'inspecting'
  | 'reproducing'
  | 'patching'
  | 'testing'
  | 'verifying'
  | 'recovering'
  | 'verified'
  | 'unresolved'
  | 'failed'
  | 'cancelled';

interface StatusIndicatorProps {
  status: RepairStatus;
}

const statusMap: Record<RepairStatus, { label: string; variant: RepairStatus }> = {
  queued: { label: 'Queued', variant: 'queued' },
  inspecting: { label: 'Inspecting', variant: 'inspecting' },
  reproducing: { label: 'Reproducing', variant: 'reproducing' },
  patching: { label: 'Patching', variant: 'patching' },
  testing: { label: 'Testing', variant: 'testing' },
  verifying: { label: 'Verifying', variant: 'verifying' },
  recovering: { label: 'Recovering', variant: 'recovering' },
  verified: { label: 'Verified', variant: 'verified' },
  unresolved: { label: 'Unresolved', variant: 'unresolved' },
  failed: { label: 'Failed', variant: 'failed' },
  cancelled: { label: 'Cancelled', variant: 'cancelled' },
};

export const StatusIndicator = ({ status }: StatusIndicatorProps) => {
  const { label, variant } = statusMap[status] || { label: 'Unknown', variant: 'queued' };

  return (
    <div className="flex items-center gap-2">
      <Badge variant={variant}>
        {label}
      </Badge>
    </div>
  );
};