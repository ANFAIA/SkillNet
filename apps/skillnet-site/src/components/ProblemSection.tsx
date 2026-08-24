import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";

const BACKGROUND_URL = "/images/landing/skillnet-adaptive-assessment-plaza-v1.webp";
const QUOTE = "No puedes juzgar a un pez por cómo trepa un árbol.";
const EXPLANATION = "Todos aprendemos de maneras distintas. Cambian lo que ya sabemos, nuestro contexto, el ritmo, los intereses y el apoyo que necesitamos. Una misma explicación no funciona igual para todas las personas; la experiencia educativa debería poder responder a esas diferencias.";

export default function ProblemSection() {
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement | null>(null);
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start end", "end start"] });
  const bgY = useTransform(scrollYProgress, [0, 1], ["-12%", "12%"]);
  const reveal = { initial: false } as const;
  return <section id="el-problema" data-nav-theme="dark" ref={sectionRef} className="relative w-full overflow-hidden bg-[var(--color-primary-deep)]">
    <motion.div aria-hidden="true" style={{ backgroundImage: `url(${BACKGROUND_URL})`, backgroundSize: "cover", backgroundPosition: "center", backgroundRepeat: "no-repeat", ...(reduced ? {} : { y: bgY }) }} className="pointer-events-none absolute inset-0 scale-[1.2] will-change-transform" />
    <div className="absolute inset-0 bg-[var(--color-primary-deep)]/70" />
    <div className="relative mx-auto grid w-full max-w-[80%] gap-10 py-24 sm:min-h-[70vh] sm:grid-cols-2 sm:items-center sm:gap-16 sm:py-32">
      <motion.blockquote {...reveal} transition={{ duration: 0.6, ease: [0.38, 0.49, 0, 1] }} className="type-section-title text-balance text-white">&ldquo;{QUOTE}&rdquo;</motion.blockquote>
      <motion.p {...reveal} transition={{ duration: 0.6, delay: reduced ? 0 : 0.12, ease: [0.38, 0.49, 0, 1] }} className="type-body text-white/85">{EXPLANATION}</motion.p>
    </div>
  </section>;
}
