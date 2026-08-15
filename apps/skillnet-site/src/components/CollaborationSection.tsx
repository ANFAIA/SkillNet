import { ArrowUpRight } from "lucide-react";
import { FaGithub } from "react-icons/fa";
import { motion } from "framer-motion";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";

export default function CollaborationSection() {
  return <section id="open-source" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Open source</motion.h2>
      <motion.div initial={false} className="open-source-row mt-10">
        <div className="open-source-copy"><p>SkillNet se construye en abierto. El código puede revisarse, ejecutarse y mejorarse públicamente, y cada organización puede mantener su propia instancia.</p><p>Compartir el proceso también significa enseñar los límites, las decisiones y lo que todavía no funciona.</p></div>
        <a className="open-source-card" href={GITHUB_URL} target="_blank" rel="noopener noreferrer"><FaGithub size={48} /><span><strong>Explorar SkillNet en GitHub</strong><small>Consulta el código, las decisiones y la evolución del proyecto.</small></span><ArrowUpRight className="open-source-card__arrow" size={22} /></a>
      </motion.div>
    </div>
  </section>;
}
