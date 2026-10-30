import React from 'react';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
}

export const Button = ({ 
  variant = 'primary', 
  size = 'md', 
  disabled = false, 
  loading = false,
  onClick, 
  children,
  className = '',
  type = 'button',
  ...rest
}: ButtonProps) => {
  // Base classes
  const baseClasses = 'font-medium py-2 px-4 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2';
  
  // Variant classes
  const variantClasses: Record<string, string> = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white',
    secondary: 'bg-charcoal-800 hover:bg-charcoal-700 text-charcoal-50',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
  };
  
  // Size classes
  const sizeClasses: Record<string, string> = {
    sm: 'px-3 py-1 text-sm',
    md: 'px-4 py-2',
    lg: 'px-5 py-3 text-lg',
  };

  return (
    <button
      type={type}
      className={`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      onClick={onClick}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
};