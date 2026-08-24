import { motion, useReducedMotion } from "framer-motion";

const BACKGROUND_URL = "/images/landing/skillnet-learning-commons-background-v1.webp";

const COPY = {
  title: "Aprender no tiene por qué ser igual para todos.",
  subtitle:
    "SkillNet convierte una idea o fuente en un curso que puede adaptar sus explicaciones, actividades e interfaz a cada persona.",
  github: "Explorar en GitHub",
  moreCta: "Saber más",
};

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const MORE_ANCHOR = "#que-es-skillnet";

export default function Hero() {
  const prefersReducedMotion = useReducedMotion();

  const entrance = prefersReducedMotion
    ? {}
    : {
        initial: { opacity: 0, y: 16 },
        animate: { opacity: 1, y: 0 },
      };

  return (
    <section className="relative h-screen w-full overflow-hidden bg-[var(--color-primary-deep)]">
      {/* Depth 1: illustration, background plane — fully static */}
      <div
        aria-hidden="true"
        role="img"
        aria-label=""
        style={{
          backgroundImage: `url(${BACKGROUND_URL})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
        className="pointer-events-none fixed inset-0"
      />

      {/* Depth 2: colour glow, mid plane — fully static */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--color-primary-deep)]/70 via-transparent to-[var(--color-primary-deep)]/80" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
      </div>

      {/* Depth 3: foreground copy, stays essentially still */}
      <div className="relative mx-auto flex h-full w-full max-w-[80%] flex-col items-center justify-center text-center">
        <motion.h1
          {...entrance}
          transition={{ duration: 0.7, ease: [0.38, 0.49, 0, 1] }}
          className="type-display w-full text-balance text-white"
        >
          {COPY.title}
        </motion.h1>

        <motion.p
          {...entrance}
          transition={{
            duration: 0.7,
            ease: [0.38, 0.49, 0, 1],
            delay: prefersReducedMotion ? 0 : 0.12,
          }}
          className="type-lead mx-auto mt-6 max-w-2xl text-balance text-white/85"
        >
          {COPY.subtitle}
        </motion.p>

        <motion.div
          {...entrance}
          transition={{
            duration: 0.7,
            ease: [0.38, 0.49, 0, 1],
            delay: prefersReducedMotion ? 0 : 0.24,
          }}
          className="mt-10 flex flex-col items-center gap-4 sm:flex-row"
        >
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="type-ui rounded-lg bg-white px-6 py-3 text-[var(--color-text)] transition-opacity duration-200 ease-out hover:opacity-90"
          >
            {COPY.github}
          </a>

          <a
            href={MORE_ANCHOR}
            className="type-ui rounded-lg border border-white/70 bg-transparent px-6 py-3 text-white transition-colors duration-200 ease-out hover:bg-white/10"
          >
            {COPY.moreCta}
          </a>
        </motion.div>
      </div>
    </section>
  );
}
