import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import {
  ANFAIA_LOGO,
  ANFAIA_LOGO_SIZE,
  ANFAIA_URL,
  GESTION_TICKETS_LOGO,
  GESTION_TICKETS_LOGO_SIZE,
  GESTION_TICKETS_URL,
} from "../data/links";

export default function SiteFooter({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang);
  const contactHref = lang === "en" ? "/en/#contacto" : "/#contacto";
  const cookieSettingsLabel = lang === "en" ? "Cookie settings" : "Configurar cookies";
  const openCookieSettings = () => {
    window.dispatchEvent(new CustomEvent("skillnet:open-cookie-settings"));
  };

  return <motion.footer data-nav-theme="light" initial={false} className="w-full bg-white px-6 pb-10 pt-16 sm:px-10 sm:pt-24">
    <div className="mx-auto w-full max-w-[80%] pt-10">
      <div className="footer-main">
        <div>
          <strong>SkillNet</strong>
          <p>{copy.footer.tagline}</p>
        </div>
      </div>
      <div className="footer-credits">
        <span className="credit-line credit-line--small">
          <span>{copy.footer.projectBy}</span>
          <a href={ANFAIA_URL} target="_blank" rel="noopener noreferrer">
            <img src={ANFAIA_LOGO} {...ANFAIA_LOGO_SIZE} alt="Anfaia" className="credit-logo credit-logo--anfaia" />
          </a>
        </span>
        <span className="credit-line credit-line--small">
          <span>{copy.footer.grantBy}</span>
          <a href={GESTION_TICKETS_URL} target="_blank" rel="noopener noreferrer">
            <img src={GESTION_TICKETS_LOGO} {...GESTION_TICKETS_LOGO_SIZE} alt="Gestión Tickets" className="credit-logo credit-logo--tickets" />
          </a>
        </span>
      </div>
      <div className="footer-meta">
        <span>© 2026 SkillNet</span>
        <div className="footer-meta__links">
          <button type="button" onClick={openCookieSettings}>{cookieSettingsLabel}</button>
          <a href={contactHref}>{copy.footer.contact}</a>
        </div>
      </div>
    </div>
  </motion.footer>;
}
