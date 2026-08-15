import { motion } from "framer-motion";

export default function StableAdaptSection() {
  return <section className="education-section w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">El futuro de la educación</motion.h2>
      <motion.div initial={false} className="education-copy mt-10">
        <p>Durante décadas, la estructura de la educación ha cambiado mucho menos que el mundo que la rodea. Se han digitalizado materiales y aulas, pero la experiencia sigue organizándose, con frecuencia, alrededor de una misma explicación, un mismo ritmo y un mismo recorrido para todos.</p>
        <p>La inteligencia artificial abre nuevas vías: permite explorar experiencias más flexibles, mantener una conversación con el conocimiento y ofrecer apoyos distintos sin renunciar al criterio humano. La oportunidad no está en automatizar la educación, sino en imaginar mejor cómo enseñamos y cómo aprendemos.</p>
      </motion.div>
    </div>
  </section>;
}
