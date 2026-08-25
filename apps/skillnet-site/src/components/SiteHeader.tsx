import { useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { FaGithub } from "react-icons/fa";
import Logo from "./Logo";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const TRANSITION = { type: "tween", duration: 0.52, ease: [0.22, 1, 0.36, 1] } as const;

const LANDING_LINKS = [
  { href: "#que-es-skillnet", label: "Qué es SkillNet" },
  { href: "#como-funciona", label: "Cómo funciona" },
  { href: "#para-quien", label: "Para quién" },
  { href: "#contacto", label: "Contacto" },
  { href: "/docs", label: "Documentación" },
];

const DOCS_LINKS_ES = [{ href: "/", label: "Volver al inicio" }];
const DOCS_LINKS_EN = [{ href: "/", label: "Back to home" }];

interface Props {
  variant?: "landing" | "docs";
  locale?: "es" | "en";
  /** For variant="docs": href of the equivalent page in the other locale. */
  altHref?: string;
}

export default function SiteHeader({ variant = "landing", locale = "es", altHref }: Props) {
  const [scrolled, setScrolled] = useState(variant === "docs");
  const [navTheme, setNavTheme] = useState<"dark" | "light">("dark");
  const [open, setOpen] = useState(false);
  const LINKS = variant === "docs" ? (locale === "en" ? DOCS_LINKS_EN : DOCS_LINKS_ES) : LANDING_LINKS;
  const logoHref = variant === "docs" ? "/" : "#";
  const otherLocaleLabel = locale === "en" ? "ES" : "EN";
  const langToggleAriaLabel = locale === "en" ? "Switch to Spanish" : "Cambiar a inglés";
  useEffect(() => {
    if (variant === "docs") return;
    const updateHeader = () => {
      setScrolled(window.scrollY > 40);
      const section = Array.from(document.querySelectorAll<HTMLElement>("[data-nav-theme]"))
        .find((candidate) => {
          const bounds = candidate.getBoundingClientRect();
          return bounds.top <= 72 && bounds.bottom > 72;
        });
      if (section?.dataset.navTheme === "light" || section?.dataset.navTheme === "dark") {
        setNavTheme(section.dataset.navTheme);
      }
    };
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
    window.addEventListener("resize", updateHeader, { passive: true });
    return () => {
      window.removeEventListener("scroll", updateHeader);
      window.removeEventListener("resize", updateHeader);
    };
  }, [variant]);

  const lightTheme = variant === "landing" && navTheme === "light";
  const surfaceClass = lightTheme
    ? "border-[color-mix(in_srgb,var(--color-primary-deep)_12%,transparent)] bg-white/72 text-[var(--color-primary-deep)]"
    : "border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_58%,transparent)] text-white";
  const linkClass = lightTheme
    ? "text-[color-mix(in_srgb,var(--color-primary-deep)_78%,transparent)] hover:text-[var(--color-primary-deep)]"
    : "text-white/85 hover:text-white";
  const menuSurfaceClass = lightTheme
    ? "border-[color-mix(in_srgb,var(--color-primary-deep)_12%,transparent)] bg-white/78 text-[var(--color-primary-deep)]"
    : "border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_78%,transparent)] text-white";
  const menuLinkClass = lightTheme
    ? "text-[color-mix(in_srgb,var(--color-primary-deep)_82%,transparent)] hover:bg-black/5 hover:text-[var(--color-primary-deep)]"
    : "text-white/90 hover:bg-white/10 hover:text-white";

  return <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex flex-col items-center">
    <MotionConfig transition={TRANSITION}>
      <motion.div
        layout
        initial={false}
        style={{ willChange: "transform, width, border-radius" }}
        className={`pointer-events-auto flex items-center transition-colors duration-300 ${scrolled ? `mt-3 gap-4 rounded-full border px-4 py-2 backdrop-blur-xl backdrop-saturate-150 sm:gap-5 sm:px-5 ${surfaceClass}` : "mt-6 w-full max-w-[80%] justify-between text-white"}`}
      >
        <motion.a layout="position" href={logoHref} aria-label="Volver al inicio" className={`flex shrink-0 items-center transition-colors duration-300 ${scrolled && lightTheme ? "text-[var(--color-primary)]" : "text-current"}`}><Logo size={26} /></motion.a>

        {/* Desktop navigation */}
        <motion.nav layout="position" className="hidden items-center gap-6 2xl:flex" aria-label="Navegación principal">
          {LINKS.map(({ href, label }) => <a key={href} href={href} className={`type-ui whitespace-nowrap transition-colors duration-300 ${scrolled ? linkClass : "text-white/85 hover:text-white"}`}>{label}</a>)}
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className={`type-ui flex items-center gap-1.5 whitespace-nowrap transition-colors duration-300 ${scrolled ? linkClass : "text-white/85 hover:text-white"}`}><FaGithub size={17} /><span>GitHub</span></a>
          {variant === "docs" && altHref && (
            <a href={altHref} aria-label={langToggleAriaLabel} className="type-ui whitespace-nowrap rounded-full border border-white/25 px-2.5 py-1 text-white/85 hover:border-white/50 hover:text-white">
              {otherLocaleLabel}
            </a>
          )}
        </motion.nav>

        {/* Mobile hamburger */}
        <button type="button" onClick={() => setOpen((v) => !v)} aria-label={open ? "Cerrar menú" : "Abrir menú"} aria-expanded={open} className="flex h-9 w-9 items-center justify-center text-current 2xl:hidden">
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </motion.div>

      {/* Mobile dropdown panel */}
      <AnimatePresence>
        {open && <motion.nav
          key="mobile-menu"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          aria-label="Navegación principal"
          className={`pointer-events-auto mt-2 flex w-full max-w-[88%] flex-col overflow-hidden rounded-2xl border p-2 backdrop-blur-xl transition-colors duration-300 sm:max-w-md 2xl:hidden ${menuSurfaceClass}`}
        >
          {LINKS.map(({ href, label }) => <a key={href} href={href} onClick={() => setOpen(false)} className={`type-ui rounded-xl px-4 py-3 transition-colors duration-200 ${menuLinkClass}`}>{label}</a>)}
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)} className={`type-ui flex items-center gap-2 rounded-xl px-4 py-3 transition-colors duration-200 ${menuLinkClass}`}><FaGithub size={17} />GitHub</a>
          {variant === "docs" && altHref && (
            <a href={altHref} onClick={() => setOpen(false)} aria-label={langToggleAriaLabel} className="type-ui rounded-xl px-4 py-3 text-white/90 hover:bg-white/10 hover:text-white">
              {otherLocaleLabel}
            </a>
          )}
        </motion.nav>}
      </AnimatePresence>
    </MotionConfig>
  </header>;
}
