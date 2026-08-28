import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";

const BACKGROUND_URL = "/images/landing/skillnet-adaptive-assessment-plaza-v1.webp";

export default function ProblemSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).problem;
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement | null>(null);
  const { ref: contentRef, state } = useEntrance<HTMLDivElement>(0.25);
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start end", "end start"] });
  const bgY = useTransform(scrollYProgress, [0, 1], ["-12%", "12%"]);
  return <section id="el-problema" data-nav-theme="dark" ref={sectionRef} className="relative w-full overflow-hidden bg-[var(--color-primary-deep)]">
    <motion.div aria-hidden="true" style={{ backgroundImage: `url(${BACKGROUND_URL})`, backgroundSize: "cover", backgroundPosition: "center", backgroundRepeat: "no-repeat", ...(reduced ? {} : { y: bgY }) }} className="pointer-events-none absolute inset-0 scale-[1.2] will-change-transform" />
    <div className="absolute inset-0 bg-[var(--color-primary-deep)]/70" />
    <motion.div ref={contentRef} initial={false} animate={state} variants={revealGroup} className="relative mx-auto grid w-full max-w-[80%] gap-10 py-24 sm:min-h-[70vh] sm:grid-cols-2 sm:items-center sm:gap-16 sm:py-32">
      <motion.blockquote variants={revealItem} className="type-section-title text-balance text-white">&ldquo;{copy.quote}&rdquo;</motion.blockquote>
      <motion.p variants={revealItem} className="type-body text-white/85">{copy.explanation}</motion.p>
    </motion.div>
  </section>;
}
