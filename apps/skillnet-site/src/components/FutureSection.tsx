import { motion } from "framer-motion";

export default function FutureSection() {
  return <section id="estado-actual" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">En desarrollo</motion.h2>
      <motion.p initial={false} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">SkillNet está en desarrollo. Estamos construyendo y probando esta visión en abierto, aprendiendo con cada versión.</motion.p>
    </div>
  </section>;
}
