import { Mail } from "lucide-react";
import { FaGithub, FaLinkedin } from "react-icons/fa";
import { motion } from "framer-motion";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const EMAIL_URL = "mailto:jose@skillnet.es";

export default function SiteFooter() {
  return <motion.footer initial={false} className="w-full bg-white px-6 pb-10 pt-16 sm:px-10 sm:pt-24">
    <div className="mx-auto w-full max-w-[80%] border-t border-[var(--color-border-strong)] pt-10">
      <div className="footer-main"><div><strong>SkillNet</strong><p>Un proyecto abierto sobre cómo puede cambiar la experiencia de aprender.</p></div><nav aria-label="Enlaces de contacto">
        <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="social-link social-link--github"><FaGithub size={20} />GitHub</a>
        <span className="social-link social-link--linkedin is-disabled" title="Enlace pendiente de confirmar"><FaLinkedin size={20} />LinkedIn</span>
        <a href={EMAIL_URL} className="social-link social-link--mail"><Mail size={20} />Contacto</a>
      </nav></div>
      <div className="footer-meta"><span>© 2026 SkillNet</span><a href={EMAIL_URL}>jose@skillnet.es</a></div>
    </div>
  </motion.footer>;
}
