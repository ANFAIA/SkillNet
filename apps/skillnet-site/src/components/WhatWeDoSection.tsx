import { motion, useReducedMotion } from "framer-motion";

const TOP_FADE = "linear-gradient(to bottom,rgba(255,255,255,0) 0px,rgba(255,255,255,.08) 42px,rgba(255,255,255,.34) 88px,rgba(255,255,255,.7) 132px,#fff 190px,#fff 100%)";

export default function WhatWeDoSection() {
  const reduced = useReducedMotion();
  const reveal = { initial: false } as const;
  return <section id="que-es-skillnet" className="relative w-full scroll-mt-24 bg-white px-6 pb-20 pt-36 sm:px-10 sm:pb-28 sm:pt-48">
    <div aria-hidden="true" style={{ backgroundImage: TOP_FADE }} className="absolute inset-x-0 top-0 h-56" />
    <div className="relative mx-auto w-full max-w-[80%]">
      <motion.h2 {...reveal} transition={{ duration: 0.65, ease: [0.38, 0.49, 0, 1] }} className="type-section-title text-[var(--color-text)]">Qué es SkillNet</motion.h2>
      <motion.p {...reveal} transition={{ duration: 0.65, delay: reduced ? 0 : 0.1, ease: [0.38, 0.49, 0, 1] }} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">SkillNet está diseñado para convertir conocimiento en aprendizaje, ya parta de un documento, una web, un audio, un vídeo o una simple idea. A partir de esa fuente, adapta la experiencia al contexto de cada persona, a lo que ya sabe y a sus preferencias.</motion.p>
    </div>
  </section>;
}
