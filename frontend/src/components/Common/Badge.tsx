import React from 'react';

interface BadgeProps {
  variant?: 'verified' | 'unresolved' | 'failed' | 'cancelled' | 'inspecting' | 'reproducing' | 'patching' | 'testing' | 'verifying' | 'recovering' | 'queued' | 'awaiting_approval';
  children: React.ReactNode;
  className?: string;
}

export const Badge = ({ variant = 'queued', children, className = '' }: BadgeProps) => {
  // Map variant to Tailwind classes
  const variantClasses: Record<string, string> = {
    verified: 'bg-green-600/20 text-green-400',
    awaiting_approval: 'bg-blue-600/20 text-blue-400',
    unresolved: 'bg-yellow-600/20 text-yellow-400',
    failed: 'bg-red-600/20 text-red-400',
    cancelled: 'bg-gray-600/20 text-gray-400',
    inspecting: 'bg-blue-600/20 text-blue-400 animate-pulse',
    reproducing: 'bg-blue-600/20 text-blue-400 animate-pulse',
    patching: 'bg-blue-600/20 text-blue-400 animate-pulse',
    testing: 'bg-blue-600/20 text-blue-400 animate-pulse',
    verifying: 'bg-blue-600/20 text-blue-400 animate-pulse',
    recovering: 'bg-blue-600/20 text-blue-400 animate-pulse',
    queued: 'bg-gray-600/20 text-gray-400',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
};