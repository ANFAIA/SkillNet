import { motion, useReducedMotion } from "framer-motion";

const TOP_FADE = "linear-gradient(to bottom,rgba(255,255,255,0) 0px,rgba(255,255,255,.16) 28px,rgba(255,255,255,.58) 72px,#fff 128px,#fff 100%)";

export default function WhatWeDoSection() {
  const reduced = useReducedMotion();
  const reveal = { initial: false } as const;
  return <section id="que-es-skillnet" className="relative w-full scroll-mt-24 bg-white px-6 pb-10 pt-24 sm:px-10 sm:pb-12 sm:pt-28">
    <div aria-hidden="true" style={{ backgroundImage: TOP_FADE }} className="absolute inset-x-0 top-0 h-40" />
    <div className="relative mx-auto w-full max-w-[80%]">
      <motion.h2 {...reveal} transition={{ duration: 0.65, ease: [0.38, 0.49, 0, 1] }} className="type-section-title text-[var(--color-text)]">Qué es SkillNet</motion.h2>
      <motion.p {...reveal} transition={{ duration: 0.65, delay: reduced ? 0 : 0.1, ease: [0.38, 0.49, 0, 1] }} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">SkillNet es un sistema de aprendizaje adaptativo y open source. Puedes partir de una idea o subir material en PDF, DOCX, Markdown o TXT. A partir de ahí genera la estructura, las lecciones y los ejercicios de un curso. Si utilizas material propio, conserva su procedencia y lo usa como fuente. Si partes de una idea, registra que la fuente ha sido generada.</motion.p>
    </div>
  </section>;
}
