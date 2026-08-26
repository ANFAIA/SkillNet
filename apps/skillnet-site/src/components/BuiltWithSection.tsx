import { motion } from "framer-motion";
import { useEntrance } from "./useEntrance";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { CURIO_URL, DIDACT_URL } from "../data/links";

/**
 * "Built with" — the two sibling projects SkillNet leans on. A signal, not a
 * partner wall: two cards, the same border and radius as the rest of the site.
 *
 * Curio has a real mark (its mascot), so the card uses the actual asset. Didact
 * is deliberately unbranded and has no logo, so its card is a typographic
 * lockup instead of an invented one.
 */

const EASE = [0.38, 0.49, 0, 1] as const;

const letterIn = {
  hidden: { opacity: 0.25, transition: { duration: 0 } },
  show: (delay: number) => ({ opacity: 1, transition: { duration: 0.45, delay, ease: EASE } }),
};

const ruleIn = {
  hidden: { scaleX: 0, transition: { duration: 0 } },
  show: { scaleX: 1, transition: { duration: 0.6, delay: 0.4, ease: EASE } },
};

const blobIn = {
  hidden: { opacity: 0, scale: 0.82, transition: { duration: 0 } },
  show: { opacity: 1, scale: 1, transition: { duration: 0.6, ease: EASE } },
};

/** Didact ships no logo of its own, so its mark is the name, set and animated. */
function DidactWordmark({ state }: { state: "hidden" | "show" }) {
  return (
    <span className="builtwith-wordmark" aria-hidden="true">
      {"Didact".split("").map((letter, index) => (
        <motion.span
          key={`${letter}-${index}`}
          initial={false}
          animate={state}
          variants={letterIn}
          custom={index * 0.06}
        >
          {letter}
        </motion.span>
      ))}
      <motion.i
        className="builtwith-wordmark__rule"
        initial={false}
        animate={state}
        variants={ruleIn}
      />
    </span>
  );
}

export default function BuiltWithSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).builtWith;
  const { ref, state } = useEntrance<HTMLDivElement>(0.4);

  return (
    <section id="hecho-con" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 py-16 sm:px-10 sm:py-20">
      <div className="mx-auto w-full max-w-[80%]">
        <motion.h2 initial={false} className="type-section-title">{copy.title}</motion.h2>
        <motion.p initial={false} className="type-lead mt-4 w-full text-[var(--color-text-secondary)]">
          {copy.lead}
        </motion.p>

        <div className="builtwith-list mt-8" ref={ref}>
          <a className="builtwith-card" href={DIDACT_URL} target="_blank" rel="noopener noreferrer">
            <span className="builtwith-card__mark">
              <DidactWordmark state={state} />
            </span>
            <span className="builtwith-card__body">
              <strong>{copy.didactTitle}</strong>
              <small>{copy.didactDetail}</small>
            </span>
          </a>

          <a className="builtwith-card" href={CURIO_URL} target="_blank" rel="noopener noreferrer">
            <span className="builtwith-card__mark">
              <motion.img
                src="/images/brand/curio-mark.png"
                alt="Curio"
                width={72}
                height={72}
                className="builtwith-card__blob"
                initial={false}
                animate={state}
                variants={blobIn}
              />
              <span className="builtwith-name">Curio</span>
            </span>
            <span className="builtwith-card__body">
              <strong>{copy.curioTitle}</strong>
              <small>{copy.curioDetail}</small>
            </span>
          </a>
        </div>
      </div>
    </section>
  );
}
