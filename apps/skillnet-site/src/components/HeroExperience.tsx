import { LazyMotion, domAnimation, m, useReducedMotion } from 'framer-motion'

interface HeroExperienceProps {
  repositoryHref: string
}

const ease = [0.38, 0.49, 0, 1] as const

const paths = [
  { number: '01', title: 'Explain', note: 'A clearer starting point', tone: 'blue' },
  { number: '02', title: 'Practise', note: 'The right level of challenge', tone: 'green' },
  { number: '03', title: 'Apply', note: 'A useful next step', tone: 'mix' },
]

export function HeroExperience({ repositoryHref }: HeroExperienceProps) {
  const reducedMotion = useReducedMotion()
  const reveal = reducedMotion
    ? {}
    : {
        initial: { opacity: 0, y: 18 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.3, ease },
      }

  return (
    <LazyMotion features={domAnimation} strict>
      <section className="hero">
        <div className="shell hero-grid">
          <m.div className="hero-content" {...reveal}>
            <p className="eyebrow"><span className="eyebrow-dot" />Exploring what learning can become</p>
            <h1>The source stays the same. The learning experience doesn’t have to.</h1>
            <p className="hero-copy">
              SkillNet is an open-source learning system built around a simple idea: keep knowledge
              and objectives trustworthy, while the path, explanation and practice can adapt.
            </p>
            <div className="action-row">
              <a className="button button-primary" href="#how-it-works">See how it works <span aria-hidden="true">→</span></a>
              <a className="button button-secondary" href={repositoryHref} rel="noreferrer" target="_blank">
                Explore the source<span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
            <p className="hero-note"><span />In development. Built in public, with the limits visible.</p>
          </m.div>

          <m.div
            className="morph-stage"
            initial={reducedMotion ? false : { opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: reducedMotion ? 0 : 0.08, ease }}
            aria-hidden="true"
          >
            <div className="morph-grid" />

            <m.div
              className="source-node"
              animate={reducedMotion ? undefined : { y: [0, -5, 0] }}
              transition={{ duration: 5.6, repeat: Infinity, ease: 'easeInOut' }}
            >
              <span className="graphic-label">Shared foundation</span>
              <strong>Trusted source</strong>
              <div className="source-tags"><i>Knowledge</i><i>Objectives</i><i>Criteria</i></div>
            </m.div>

            <div className="morph-bridge bridge-in"><span /></div>

            <div className="morph-core-wrap">
              <m.div
                className="morph-core"
                animate={reducedMotion ? undefined : {
                  borderRadius: ['34% 66% 58% 42% / 45% 42% 58% 55%', '58% 42% 35% 65% / 38% 60% 40% 62%', '34% 66% 58% 42% / 45% 42% 58% 55%'],
                  rotate: [0, 8, 0],
                  scale: [1, 1.04, 1],
                }}
                transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut' }}
              >
                <span>Adapt</span>
              </m.div>
              <m.i className="orbit orbit-one" animate={reducedMotion ? undefined : { rotate: 360 }} transition={{ duration: 14, repeat: Infinity, ease: 'linear' }} />
              <m.i className="orbit orbit-two" animate={reducedMotion ? undefined : { rotate: -360 }} transition={{ duration: 18, repeat: Infinity, ease: 'linear' }} />
            </div>

            <div className="morph-bridge bridge-out"><span /></div>

            <div className="path-stack">
              {paths.map((path, index) => (
                <m.div
                  className={`path-card ${path.tone}`}
                  key={path.title}
                  initial={reducedMotion ? false : { opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0, y: reducedMotion ? 0 : [0, index % 2 ? 4 : -4, 0] }}
                  transition={{
                    opacity: { delay: 0.18 + index * 0.07, duration: 0.26, ease },
                    x: { delay: 0.18 + index * 0.07, duration: 0.26, ease },
                    y: { duration: 5 + index, repeat: Infinity, ease: 'easeInOut' },
                  }}
                >
                  <span>{path.number}</span><div><strong>{path.title}</strong><small>{path.note}</small></div>
                </m.div>
              ))}
            </div>
          </m.div>
        </div>
      </section>
    </LazyMotion>
  )
}
