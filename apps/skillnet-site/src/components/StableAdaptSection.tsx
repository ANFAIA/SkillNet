import { motion } from "framer-motion";

export default function StableAdaptSection() {
  return <section id="vision" data-nav-theme="light" className="education-section scroll-mt-24 w-full bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Visión</motion.h2>
      <motion.p initial={false} className="education-copy mt-10">Muchas tecnologías nuevas empiezan imitando a las anteriores. Los primeros coches parecían carruajes y las primeras páginas web trasladaban el papel a una pantalla. ¿Y si a buena parte de la educación digital le está pasando algo parecido, con libros, clases y recorridos lineales llevados a internet sin cambiar del todo la experiencia? Si es así, la inteligencia artificial abre la posibilidad de buscar un lenguaje propio para aprender, siempre como herramienta al servicio de docentes y estudiantes.</motion.p>
      <motion.p initial={false} className="education-copy mt-10">SkillNet ya trabaja en esa dirección. Genera interfaces con OpenUI y las compone con componentes Didact creados para aprender. Las preferencias declaradas, el rol, el nivel y el progreso pueden cambiar la presentación, las actividades y los apoyos que aparecen en el curso.</motion.p>
      <motion.p initial={false} className="education-copy mt-6">La siguiente frontera es generar la propia experiencia interactiva en lugar de limitarse a elegir entre formatos existentes. Con los modelos actuales todavía resulta caro y lento hacerlo bien, pero ese límite seguirá cambiando.</motion.p>
      <motion.p initial={false} className="education-copy mt-6">Un curso de animación no debería limitarse a mostrar un vídeo sobre animación: podría generar un simulador de fotogramas para que cada persona experimente con sus propias manos. Eso todavía no es viable a escala, pero es la dirección que SkillNet quiere explorar.</motion.p>
    </div>
  </section>;
}
