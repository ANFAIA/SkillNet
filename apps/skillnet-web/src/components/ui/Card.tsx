import type { HTMLAttributes } from 'react'

type CardVariant = 'default' | 'interactive'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant
}

const variantClasses: Record<CardVariant, string> = {
  default:
    'border border-border bg-bg rounded-xl p-5 min-w-0 w-full',
  interactive:
    'border border-border bg-bg rounded-xl p-5 min-w-0 w-full hover:border-primary transition-colors cursor-pointer',
}

export function Card({
  variant = 'default',
  className = '',
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={`${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <h3 className={`text-base font-medium text-text ${className}`}>{children}</h3>
}
