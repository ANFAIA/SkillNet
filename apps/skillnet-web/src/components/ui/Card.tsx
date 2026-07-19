import { motion, type HTMLMotionProps } from 'framer-motion'
import { spring, duration, ease } from '../../lib/motion'

type CardVariant = 'default' | 'interactive'

export interface CardProps extends HTMLMotionProps<'div'> {
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
  const interactive = variant === 'interactive'

  return (
    <motion.div
      className={`${variantClasses[variant]} ${className}`}
      whileHover={interactive ? { scale: 1.02, boxShadow: '0 8px 32px -8px rgba(0,0,0,0.12)' } : undefined}
      transition={{
        scale: spring.default,
        boxShadow: { duration: duration.normal, ease: ease.base },
      }}
      {...props}
    >
      {children}
    </motion.div>
  )
}

export function CardTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <h3 className={`text-base font-medium text-text ${className}`}>{children}</h3>
}
