import { motion } from 'framer-motion'

export interface InfographicPosterProps {
  src: string
  title: string
}

/** The generated infographic remains one image; this wrapper only presents it consistently. */
export function InfographicPoster({ src, title }: InfographicPosterProps) {
  return (
    <figure className="overflow-hidden border border-border bg-bg">
      <motion.img
        key={src}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
        src={src}
        alt={title}
        className="block h-auto w-full"
      />
    </figure>
  )
}
