import { useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { FaGithub } from "react-icons/fa";
import Logo from "./Logo";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const TRANSITION = { type: "tween", duration: 0.52, ease: [0.22, 1, 0.36, 1] } as const;
/** Tailwind's `2xl` breakpoint: above it the desktop nav replaces the mobile menu. */
const DESKTOP_QUERY = "(min-width: 96rem)";

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
  // `open` is the intent; `expanded` is the surface. On opening they move together,
  // but on closing the surface has to hold its shape until the links have faded
  // out: otherwise it narrows to a pill while the panel is still in the flow, and
  // the morph lands on a tall sliver instead of the bar.
  const [expanded, setExpanded] = useState(false);
  const LINKS = variant === "docs" ? (locale === "en" ? DOCS_LINKS_EN : DOCS_LINKS_ES) : LANDING_LINKS;
  const logoHref = variant === "docs" ? "/" : "#";
  const otherLocaleLabel = locale === "en" ? "ES" : "EN";
  const langToggleAriaLabel = locale === "en" ? "Switch to Spanish" : "Cambiar a inglés";
  useEffect(() => {
    if (open) setExpanded(true);
  }, [open]);

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

  // The open menu reshapes the header surface, so it must not survive a jump to
  // the desktop layout (where the panel is hidden but the surface would stay wide).
  useEffect(() => {
    const desktop = window.matchMedia(DESKTOP_QUERY);
    const closeOnDesktop = () => {
      if (desktop.matches) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    closeOnDesktop();
    desktop.addEventListener("change", closeOnDesktop);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      desktop.removeEventListener("change", closeOnDesktop);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const lightTheme = variant === "landing" && navTheme === "light";
  const surfaceClass = lightTheme
    ? "border-[color-mix(in_srgb,var(--color-primary-deep)_12%,transparent)] bg-white/72 text-[var(--color-primary-deep)]"
    : "border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_58%,transparent)] text-white";
  const linkClass = lightTheme
    ? "text-[color-mix(in_srgb,var(--color-primary-deep)_78%,transparent)] hover:text-[var(--color-primary-deep)]"
    : "text-white/85 hover:text-white";
  const menuLinkClass = lightTheme
    ? "text-[color-mix(in_srgb,var(--color-primary-deep)_82%,transparent)] hover:bg-black/5 hover:text-[var(--color-primary-deep)]"
    : "text-white/90 hover:bg-white/10 hover:text-white";

  // One surface, three shapes. The menu lives *inside* it, so the panel can never
  // drift away from the button that opens it: the container morphs, the panel fades in.
  const surfaceShape = expanded
    ? `mt-3 w-full max-w-[88%] rounded-3xl border p-2 backdrop-blur-xl backdrop-saturate-150 sm:max-w-md ${surfaceClass}`
    : scrolled
      ? `mt-3 rounded-full border px-4 py-2 backdrop-blur-xl backdrop-saturate-150 sm:px-5 ${surfaceClass}`
      : "mt-6 w-full max-w-[80%] text-white";

  return <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex flex-col items-center">
    <MotionConfig transition={TRANSITION}>
      <motion.div
        layout
        initial={false}
        className={`pointer-events-auto flex flex-col transition-colors duration-300 ${surfaceShape}`}
      >
        <motion.div layout className={`flex items-center ${expanded ? "justify-between px-2" : scrolled ? "gap-4 sm:gap-5" : "justify-between"}`}>
          <motion.a layout href={logoHref} aria-label="Volver al inicio" className={`flex shrink-0 items-center transition-colors duration-300 ${scrolled && lightTheme ? "text-[var(--color-primary)]" : "text-current"}`}><Logo size={26} /></motion.a>

          {/* Desktop navigation */}
          <nav className="hidden items-center gap-6 2xl:flex" aria-label="Navegación principal">
            {LINKS.map(({ href, label }) => <a key={href} href={href} className={`type-ui whitespace-nowrap transition-colors duration-300 ${scrolled ? linkClass : "text-white/85 hover:text-white"}`}>{label}</a>)}
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className={`type-ui flex items-center gap-1.5 whitespace-nowrap transition-colors duration-300 ${scrolled ? linkClass : "text-white/85 hover:text-white"}`}><FaGithub size={17} /><span>GitHub</span></a>
            {variant === "docs" && altHref && (
              <a href={altHref} aria-label={langToggleAriaLabel} className="type-ui whitespace-nowrap rounded-full border border-white/25 px-2.5 py-1 text-white/85 hover:border-white/50 hover:text-white">
                {otherLocaleLabel}
              </a>
            )}
          </nav>

          {/* Mobile hamburger */}
          <motion.button layout type="button" onClick={() => setOpen((v) => !v)} aria-label={open ? "Cerrar menú" : "Abrir menú"} aria-expanded={open} className="flex h-9 w-9 shrink-0 items-center justify-center text-current 2xl:hidden">
            {open ? <X size={22} /> : <Menu size={22} />}
          </motion.button>
        </motion.div>

        {/* Mobile menu: part of the surface, never a detached slab */}
        <AnimatePresence initial={false} onExitComplete={() => setExpanded(false)}>
          {open && <motion.nav
            key="mobile-menu"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.22, delay: 0.3, ease: "linear" } }}
            exit={{ opacity: 0, transition: { duration: 0.16, delay: 0, ease: "linear" } }}
            aria-label="Menú"
            className="mt-2 flex w-full flex-col overflow-hidden 2xl:hidden"
          >
            {LINKS.map(({ href, label }) => <a key={href} href={href} onClick={() => setOpen(false)} className={`type-ui rounded-xl px-3 py-3 transition-colors duration-200 ${menuLinkClass}`}>{label}</a>)}
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)} className={`type-ui flex items-center gap-2 rounded-xl px-3 py-3 transition-colors duration-200 ${menuLinkClass}`}><FaGithub size={17} />GitHub</a>
            {variant === "docs" && altHref && (
              <a href={altHref} onClick={() => setOpen(false)} aria-label={langToggleAriaLabel} className={`type-ui rounded-xl px-3 py-3 transition-colors duration-200 ${menuLinkClass}`}>
                {otherLocaleLabel}
              </a>
            )}
          </motion.nav>}
        </AnimatePresence>
      </motion.div>
    </MotionConfig>
  </header>;
}
