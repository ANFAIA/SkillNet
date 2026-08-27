import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";

export default function StableAdaptSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).vision;
  return <section id="vision" data-nav-theme="light" className="education-section scroll-mt-24 w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">{copy.title}</motion.h2>
      <motion.p initial={false} className="education-copy mt-10">{copy.body1}</motion.p>
      <motion.p initial={false} className="education-copy mt-10">{copy.body2}</motion.p>
      <motion.p initial={false} className="education-copy mt-6">{copy.body3}</motion.p>
      <motion.p initial={false} className="education-copy mt-6">{copy.body4}</motion.p>
    </div>
  </section>;
}
