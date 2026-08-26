import { motion } from "framer-motion";

const ANFAIA_URL = "https://anfaia.org";
const GESTION_TICKETS_URL = "https://gestiontickets.online/";

export default function SiteFooter() {
  return <motion.footer data-nav-theme="light" initial={false} className="w-full bg-white px-6 pb-10 pt-16 sm:px-10 sm:pt-24">
    <div className="mx-auto w-full max-w-[80%] pt-10">
      <div className="footer-main">
        <div>
          <strong>SkillNet</strong>
          <p>Un proyecto abierto sobre cómo puede cambiar la experiencia de aprender.</p>
        </div>
      </div>
      <div className="footer-meta"><span>© 2026 SkillNet · Un proyecto de <a href={ANFAIA_URL} target="_blank" rel="noopener noreferrer" className="footer-anfaia">Anfaia</a> · Patrocinado por <a href={GESTION_TICKETS_URL} target="_blank" rel="noopener noreferrer" className="footer-anfaia">Gestión Tickets</a></span><a href="#contacto">Contacto</a></div>
    </div>
  </motion.footer>;
}
