import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";

const TOP_FADE = "linear-gradient(to bottom,rgba(255,255,255,0) 0px,rgba(255,255,255,.16) 28px,rgba(255,255,255,.58) 72px,#fff 128px,#fff 100%)";

export default function WhatWeDoSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).whatWeDo;
  const { ref, state } = useEntrance<HTMLDivElement>(0.25);
  return <section id="que-es-skillnet" data-nav-theme="light" className="relative w-full scroll-mt-24 bg-white px-6 pb-10 pt-24 sm:px-10 sm:pb-12 sm:pt-28">
    <div aria-hidden="true" style={{ backgroundImage: TOP_FADE }} className="absolute inset-x-0 top-0 h-40" />
    <motion.div ref={ref} initial={false} animate={state} variants={revealGroup} className="relative mx-auto w-full max-w-[80%]">
      <motion.h2 variants={revealItem} className="type-section-title text-[var(--color-text)]">{copy.title}</motion.h2>
      <motion.p variants={revealItem} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">{copy.body}</motion.p>
    </motion.div>
  </section>;
}
