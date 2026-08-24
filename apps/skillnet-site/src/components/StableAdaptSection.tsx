import { motion } from "framer-motion";

export default function StableAdaptSection() {
  return <section data-nav-theme="light" className="education-section w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">El futuro de la educación</motion.h2>
      <motion.p initial={false} className="education-copy mt-10">Cada tecnología nueva comienza imitando a la anterior: los primeros coches parecían carruajes y las primeras páginas web, papel impreso. A esa fase de imitación se la conoce como skeuomorfismo, y la educación digital todavía conserva mucho de ella: hemos trasladado libros, clases y recorridos lineales a una pantalla sin cambiar del todo la experiencia. La inteligencia artificial abre la posibilidad de buscar un lenguaje propio para aprender, con experiencias que conversan con el conocimiento, cambian con cada persona y ofrecen apoyos distintos cuando se necesitan, siempre como una herramienta al servicio de docentes y estudiantes, no como sustituto del criterio humano.</motion.p>
      <motion.p initial={false} className="education-copy mt-10">Un horizonte: experiencias, no catálogo. Hoy SkillNet ya genera interfaces con OpenUI y las compone con componentes Didact creados para aprender. Las preferencias declaradas, el rol, el nivel y el progreso pueden cambiar la presentación, las actividades y los apoyos que aparecen en el curso.</motion.p>
      <motion.p initial={false} className="education-copy mt-6">Ir más allá y generar la propia experiencia interactiva, en vez de elegirla entre formatos que ya existen, tiene hoy un cuello de botella: con los modelos actuales sigue siendo caro y lento hacerlo bien. Ese cuello de botella no es fijo, es el borde de lo que los modelos pueden hacer hoy, y a medida que evolucionen será cada vez más viable incorporarlo y explorarlo.</motion.p>
      <motion.p initial={false} className="education-copy mt-6">La filosofía de SkillNet es construir ya en ese borde. Un curso de animación no debería explicarse con un vídeo sobre animación: debería generar su propio simulador de fotogramas para que cada persona anime con sus manos. Eso todavía no es viable a escala, pero es la dirección.</motion.p>
    </div>
  </section>;
}
