import { motion, type HTMLMotionProps } from 'framer-motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { spring } from '../../lib/motion'

type CardVariant = 'default' | 'interactive'

export interface CardProps extends HTMLMotionProps<'div'> {
  variant?: CardVariant
}

const variantClasses: Record<CardVariant, string> = {
  default:
    'border border-border bg-surface rounded-lg p-5 min-w-0 w-full',
  interactive:
    'border border-border bg-surface rounded-lg p-5 min-w-0 w-full hover:border-primary transition-colors cursor-pointer',
}

export function Card({
  variant = 'default',
  className = '',
  children,
  ...props
}: CardProps) {
  const interactive = variant === 'interactive'
  const reducedMotion = useReducedMotion()

  return (
    <motion.div
      className={`${variantClasses[variant]} ${className}`}
      whileHover={interactive && !reducedMotion ? { y: -1 } : undefined}
      whileTap={interactive && !reducedMotion ? { scale: 0.99 } : undefined}
      transition={spring.default}
      {...props}
    >
      {children}
    </motion.div>
  )
}

export function CardTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <h3 className={`text-base font-medium text-text ${className}`}>{children}</h3>
}
