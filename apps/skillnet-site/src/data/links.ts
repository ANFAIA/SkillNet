/** External destinations used across the landing, in one place. */
export const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
/** La demo pública: se entra por `/entrar`, que es quien crea el espacio de la visita. */
export const DEMO_URL = "https://demo.skillnet.es/entrar";

/**
 * The demo door, told which language to open in.
 *
 * The demo picks its own language from `Accept-Language`, which is the right answer for
 * anyone arriving cold. It is the wrong one for anyone arriving from here: this page
 * already knows better, because the reader either let the browser choose (same answer) or
 * explicitly picked a language on the site — a choice `Accept-Language` does not carry.
 * Passing it makes the two ends agree in the one case where they otherwise would not: a
 * Spanish browser reading the English site.
 */
export function demoUrl(locale: "es" | "en"): string {
  return `${DEMO_URL}?lang=${locale}`;
}
export const LINKEDIN_URL = "https://www.linkedin.com/in/jose-est%C3%A9vez-b9b761388";
export const EMAIL_URL = "mailto:jose@skillnet.es";
export const ANFAIA_URL = "https://anfaia.org";
export const GESTION_TICKETS_URL = "https://gestiontickets.online/";
/**
 * Curio's own page, not its repository. Someone reading "built with" on a landing page is
 * asking what the thing IS, and a repository answers a different question: it opens on a
 * file tree and a README, which is the right destination for whoever has already decided
 * to use it and the wrong one for everybody else. Didact still points at its repository
 * because it has no page yet.
 */
export const CURIO_URL = "https://curio-landing-phi.vercel.app";
export const DIDACT_URL = "https://github.com/JoseEstevez520/Didact";

/**
 * Both credit marks are single-ink artwork that arrived on an opaque white
 * background. They were matted to transparency and resized to 96px tall (about
 * 3x the largest size they are painted at), so they can sit straight on the
 * page instead of inside a white plate that would read as a box.
 */
export const ANFAIA_LOGO = "/images/brand/anfaia-logo-mark.png";
export const ANFAIA_LOGO_SIZE = { width: 269, height: 96 };
export const GESTION_TICKETS_LOGO = "/images/brand/gestion-tickets-logo-mark.png";
export const GESTION_TICKETS_LOGO_SIZE = { width: 415, height: 96 };
