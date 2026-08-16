import { motion } from "framer-motion";

export default function StableAdaptSection() {
  return <section className="education-section w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">El futuro de la educación</motion.h2>
      <motion.p initial={false} className="education-copy mt-10">Cada tecnología nueva comienza imitando a la anterior: los primeros coches parecían carruajes y las primeras páginas web, papel impreso. A esa fase de imitación se la conoce como skeuomorfismo, y la educación digital todavía conserva mucho de ella: hemos trasladado libros, clases y recorridos lineales a una pantalla sin cambiar del todo la experiencia. La inteligencia artificial abre la posibilidad de buscar un lenguaje propio para aprender, con experiencias que conversan con el conocimiento, cambian con cada persona y ofrecen apoyos distintos cuando se necesitan, siempre como una herramienta al servicio de docentes y estudiantes, no como sustituto del criterio humano.</motion.p>
    </div>
  </section>;
}
