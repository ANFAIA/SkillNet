import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";

export default function StableAdaptSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).vision;
  const { ref, state } = useEntrance<HTMLDivElement>(0.14);
  return <section id="vision" data-nav-theme="light" className="education-section scroll-mt-24 w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <motion.div ref={ref} initial={false} animate={state} variants={revealGroup} className="mx-auto w-full max-w-[80%]">
      <motion.h2 variants={revealItem} className="type-section-title">{copy.title}</motion.h2>
      <motion.p variants={revealItem} className="education-copy mt-10">{copy.body1}</motion.p>
      <motion.p variants={revealItem} className="education-copy mt-10">{copy.body2}</motion.p>
      <motion.p variants={revealItem} className="education-copy mt-6">{copy.body3}</motion.p>
      <motion.p variants={revealItem} className="education-copy mt-6">{copy.body4}</motion.p>
    </motion.div>
  </section>;
}
