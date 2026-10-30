import React from 'react';
import { Badge } from './Common/Badge';
import { 
  Clock, 
  Search, 
  Bug, 
  Wrench, 
  TestTube, 
  CheckCheck, 
  RotateCcw, 
  CheckCircle, 
  AlertCircle, 
  XCircle, 
  Loader2 
} from 'lucide-react';

interface RepairTimelineProps {
  repairData: any;
  events: any[];
}

const stepIcons: Record<string, React.ReactNode> = {
  queued: <Clock className="h-3 w-3" />,
  inspecting: <Search className="h-3 w-3" />,
  reproducing: <Bug className="h-3 w-3" />,
  patching: <Wrench className="h-3 w-3" />,
  testing: <TestTube className="h-3 w-3" />,
  verifying: <CheckCheck className="h-3 w-3" />,
  recovering: <RotateCcw className="h-3 w-3" />,
  verified: <CheckCircle className="h-3 w-3" />,
  unresolved: <AlertCircle className="h-3 w-3" />,
  failed: <XCircle className="h-3 w-3" />,
  cancelled: <XCircle className="h-3 w-3" />,
};

const stepDescriptions: Record<string, string> = {
  queued: 'Repair request recorded, awaiting dispatch',
  inspecting: 'Cloning repository, detecting language & tests',
  reproducing: 'Running baseline test to confirm bug',
  patching: 'Generating and applying candidate patch',
  testing: 'Running targeted and regression tests',
  verifying: 'Deterministic verification of repair',
  recovering: 'Bounded recovery attempt (max 1)',
  verified: 'All checks passed - repair verified',
  unresolved: 'Repair inconclusive - budget exhausted',
  failed: 'Unrecoverable error occurred',
  cancelled: 'User cancelled the repair',
};

interface TimelineStepProps {
  step: { id: string; label: string };
  index: number;
  currentStepIndex: number;
  repairData: any;
}

const TimelineStep = ({ step, index, currentStepIndex, repairData }: TimelineStepProps) => {
  const isActive = index === currentStepIndex;
  const isCompleted = index < currentStepIndex;
  const isUpcoming = index > currentStepIndex;
  
  type BadgeVariant = 'verified' | 'unresolved' | 'failed' | 'cancelled' | 'inspecting' | 'reproducing' | 'patching' | 'testing' | 'verifying' | 'recovering' | 'queued';
  let badgeVariant: BadgeVariant = 'queued';
  if (isCompleted) {
    badgeVariant = step.id === 'verified' ? 'verified' : 
                  step.id === 'unresolved' ? 'unresolved' : 
                  step.id === 'failed' ? 'failed' : 
                  step.id === 'cancelled' ? 'cancelled' : 'queued';
  } else if (isActive) {
    badgeVariant = step.id as BadgeVariant;
  }

  return (
    <div key={step.id} className="relative">
      <div className="absolute left-5 top-0 bottom-0 w-0.5">
        {index < 10 && (
          <div className={`absolute top-7 h-full ${isUpcoming ? 'bg-charcoal-700' : 'bg-blue-500'}`} />
        )}
      </div>
      
      <div className="pl-14">
        <div className="flex items-start gap-3">
          <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
            isActive ? 'bg-blue-600/20 border-2 border-blue-500 animate-pulse' :
            isCompleted ? 'bg-green-600/20 border-2 border-green-500' :
            'bg-charcoal-800 border-2 border-charcoal-700'
          }`}>
            {isActive && !isCompleted ? (
              <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />
            ) : isCompleted ? (
              <CheckCircle className="h-4 w-4 text-green-400" />
            ) : (
              stepIcons[step.id] || <Clock className="h-3 w-3 text-charcoal-400" />
            )}
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Badge variant={badgeVariant}>
                {step.label}
              </Badge>
              {!isUpcoming && (
                <span className="text-xs text-charcoal-400">
                  {isActive ? 'Current' : 'Completed'}
                </span>
              )}
            </div>
            <p className="text-xs text-charcoal-500 mt-1">{stepDescriptions[step.id]}</p>
            
            {isActive && repairData && (
              <div className="mt-2 text-xs text-charcoal-400 space-y-1">
                {repairData.error_message && (
                  <div className="flex items-start gap-1.5 p-2 bg-red-950/50 border border-red-500/40 rounded text-red-400">
                    <XCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                    <span className="leading-snug font-mono text-[11px]">{repairData.error_message}</span>
                  </div>
                )}
                {!repairData.error_message && repairData.baseline_failure_classification && (
                  <div className="flex items-center gap-1">
                    <Bug className="h-3 w-3" />
                    <span>Baseline: {repairData.baseline_failure_classification}</span>
                  </div>
                )}
                {repairData.restricted_mode && (
                  <div className="flex items-center gap-1 text-yellow-400">
                    <AlertCircle className="h-3 w-3" />
                    <span>Restricted demonstration mode active</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export const RepairTimeline = ({ repairData, events }: RepairTimelineProps) => {
  const timelineSteps = [
    { id: 'queued', label: 'Queued' },
    { id: 'inspecting', label: 'Inspecting' },
    { id: 'reproducing', label: 'Reproducing' },
    { id: 'patching', label: 'Patching' },
    { id: 'testing', label: 'Testing' },
    { id: 'verifying', label: 'Verifying' },
    { id: 'recovering', label: 'Recovering' },
    { id: 'verified', label: 'Verified' },
    { id: 'unresolved', label: 'Unresolved' },
    { id: 'failed', label: 'Failed' },
    { id: 'cancelled', label: 'Cancelled' },
  ];

  const currentStatus = repairData?.status || 'queued';
  const currentStepIndex = timelineSteps.findIndex(step => step.id === currentStatus);

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold text-blue-400 mb-2 flex items-center gap-2">
        <TestTube className="h-5 w-5" />
        Repair Progress
      </h3>
      
      <div className="space-y-3">
        {timelineSteps.map((step, index) => (
          <TimelineStep 
            step={step} 
            index={index} 
            currentStepIndex={currentStepIndex} 
            repairData={repairData} 
          />
        ))}
      </div>
      
      {events.length > 0 && (
        <div className="mt-6 border-t border-charcoal-700 pt-4">
          <h4 className="text-sm font-medium text-blue-400 mb-3 flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Repair Events
          </h4>
          <div className="h-48 overflow-y-auto border border-charcoal-700 rounded-lg p-2 text-xs space-y-2">
            {events.slice().reverse().map((event: any) => (
              <div key={event.sequence_id} className="flex items-start gap-2 p-2 bg-charcoal-800/50 rounded">
                <div className="h-2 w-2 bg-blue-500 rounded-full flex-shrink-0 mt-1.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-medium text-charcoal-300 whitespace-nowrap">
                      {new Date(event.created_at).toLocaleTimeString()}
                    </span>
                    <span className="text-charcoal-500">|</span>
                    <span className="text-blue-400 font-mono">{event.event_type}</span>
                  </div>
                  <div className="mt-1 text-charcoal-300 break-all whitespace-pre-wrap font-mono text-[10px]">
                    {JSON.stringify(event.payload, null, 2)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};