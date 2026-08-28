import { ArrowUpRight, Mail } from "lucide-react";
import { FaGithub, FaLinkedin } from "react-icons/fa";
import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";
import {
  ANFAIA_LOGO,
  ANFAIA_LOGO_SIZE,
  ANFAIA_URL,
  EMAIL_URL,
  GESTION_TICKETS_LOGO,
  GESTION_TICKETS_LOGO_SIZE,
  GESTION_TICKETS_URL,
  GITHUB_URL,
  LINKEDIN_URL,
} from "../data/links";

export default function ContactSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang);
  const { ref, state } = useEntrance<HTMLDivElement>(0.18);
  return <section id="contacto" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <motion.div ref={ref} initial={false} animate={state} variants={revealGroup} className="mx-auto w-full max-w-none sm:max-w-[80%]">
      <div className="contact-grid">
        <motion.div variants={revealGroup} className="contact-intro">
          <motion.h2 variants={revealItem} className="type-section-title">{copy.contact.title}</motion.h2>
          <motion.p variants={revealItem} className="type-lead mt-6 text-[var(--color-text-secondary)]">{copy.contact.lead}</motion.p>
          {/* Two distinct roles, kept distinct: Anfaia is who the project is
              developed under, Gestión Tickets sponsors the grant that funds it. */}
          <motion.p variants={revealItem} className="credit-line mt-10">
            <span>{copy.contact.developedUnder}</span>
            <a href={ANFAIA_URL} target="_blank" rel="noopener noreferrer">
              <img src={ANFAIA_LOGO} {...ANFAIA_LOGO_SIZE} alt="Anfaia" className="credit-logo credit-logo--anfaia" />
            </a>
          </motion.p>
          <motion.p variants={revealItem} className="credit-line mt-4">
            <span>{copy.contact.grantSponsor}</span>
            <a href={GESTION_TICKETS_URL} target="_blank" rel="noopener noreferrer">
              <img src={GESTION_TICKETS_LOGO} {...GESTION_TICKETS_LOGO_SIZE} alt="Gestión Tickets" className="credit-logo credit-logo--tickets" />
            </a>
          </motion.p>
        </motion.div>
        <motion.div variants={revealGroup} className="contact-actions">
          <motion.a variants={revealItem} href={EMAIL_URL} className="contact-card contact-card--mail"><Mail size={22} /><span>{copy.contact.mail}</span><ArrowUpRight className="contact-card__arrow" size={18} /></motion.a>
          <motion.a variants={revealItem} href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="contact-card contact-card--github"><FaGithub size={22} /><span>GitHub</span><ArrowUpRight className="contact-card__arrow" size={18} /></motion.a>
          <motion.a variants={revealItem} href={LINKEDIN_URL} target="_blank" rel="noopener noreferrer" className="contact-card contact-card--linkedin"><FaLinkedin size={22} /><span>LinkedIn</span><ArrowUpRight className="contact-card__arrow" size={18} /></motion.a>
        </motion.div>
      </div>
    </motion.div>
  </section>;
}
