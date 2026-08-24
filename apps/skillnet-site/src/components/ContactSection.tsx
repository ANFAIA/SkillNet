import { ArrowUpRight, Mail } from "lucide-react";
import { FaGithub, FaLinkedin } from "react-icons/fa";
import { motion } from "framer-motion";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const LINKEDIN_URL = "https://www.linkedin.com/in/jose-est%C3%A9vez-b9b761388";
const EMAIL_URL = "mailto:jose@skillnet.es";
const ANFAIA_URL = "https://anfaia.org";

export default function ContactSection() {
  return <section id="contacto" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <div className="contact-grid">
        <div className="contact-intro">
          <motion.h2 initial={false} className="type-section-title">Contacto</motion.h2>
          <motion.p initial={false} className="type-lead mt-6 text-[var(--color-text-secondary)]">SkillNet sigue en desarrollo. Si la idea te interesa, puedes probarlo, compartir lo que no entiendas, abrir un issue o contribuir al proyecto.</motion.p>
          <p className="contact-anfaia mt-10">Desarrollado bajo <a href={ANFAIA_URL} target="_blank" rel="noopener noreferrer">Anfaia<ArrowUpRight size={19} /></a></p>
        </div>
        <div className="contact-actions">
          <a href={EMAIL_URL} className="contact-card contact-card--mail"><Mail size={22} /><span>Escríbenos</span><ArrowUpRight className="contact-card__arrow" size={18} /></a>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="contact-card contact-card--github"><FaGithub size={22} /><span>GitHub</span><ArrowUpRight className="contact-card__arrow" size={18} /></a>
          <a href={LINKEDIN_URL} target="_blank" rel="noopener noreferrer" className="contact-card contact-card--linkedin"><FaLinkedin size={22} /><span>LinkedIn</span><ArrowUpRight className="contact-card__arrow" size={18} /></a>
        </div>
      </div>
    </div>
  </section>;
}
