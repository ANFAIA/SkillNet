import { ArrowUpRight, Wrench } from "lucide-react";
import { FaGithub } from "react-icons/fa";
import { motion } from "framer-motion";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";

export default function CollaborationSection() {
  return <section id="open-source" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Open source</motion.h2>
      <motion.div initial={false} className="open-source-row mt-10">
        <div className="open-source-copy"><span className="open-source-status"><Wrench size={15} strokeWidth={1.8} aria-hidden="true" /> Versión en desarrollo</span><div><p>SkillNet se construye en abierto. El código puede revisarse, ejecutarse y mejorarse públicamente, y cada equipo o persona puede mantener su propia instancia.</p><p>Es self-hosted: se puede desplegar dentro de tus sistemas, con el proveedor de IA que prefieras o con modelos locales. Los datos permanecen en la instancia que controlas. Licencia Apache 2.0.</p><p>La API externa, el servicio A2A y el servidor MCP permiten crear cursos y consultar SkillNet desde otros agentes, chats y herramientas.</p><p>Las conversaciones, las ideas y las contribuciones al repositorio también forman parte del proyecto.</p></div></div>
        <a className="open-source-card" href={GITHUB_URL} target="_blank" rel="noopener noreferrer"><FaGithub size={48} /><span><strong>Explorar SkillNet en GitHub</strong><small>Revisa el código, pruébalo o deja una estrella para seguir su evolución.</small></span><ArrowUpRight className="open-source-card__arrow" size={22} /></a>
      </motion.div>
    </div>
  </section>;
}
