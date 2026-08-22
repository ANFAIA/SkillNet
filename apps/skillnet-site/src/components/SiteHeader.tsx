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

const DOCS_LINKS = [{ href: "/", label: "Volver al inicio" }];

interface Props {
  variant?: "landing" | "docs";
}

export default function SiteHeader({ variant = "landing" }: Props) {
  const [scrolled, setScrolled] = useState(variant === "docs");
  const [open, setOpen] = useState(false);
  const LINKS = variant === "docs" ? DOCS_LINKS : LANDING_LINKS;
  const logoHref = variant === "docs" ? "/" : "#";
  useEffect(() => {
    if (variant === "docs") return;
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [variant]);

  return <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex flex-col items-center">
    <MotionConfig transition={TRANSITION}>
      <motion.div
        layout
        initial={false}
        style={{ willChange: "transform, width, border-radius" }}
        className={`pointer-events-auto flex items-center ${scrolled ? "mt-3 gap-4 rounded-full border border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_94%,transparent)] px-5 py-2.5 shadow-[0_12px_34px_rgba(4,26,62,0.18)] backdrop-blur-md sm:gap-6 sm:px-6" : "mt-6 w-full max-w-[80%] justify-between"}`}
      >
        <motion.a layout="position" href={logoHref} aria-label="Volver al inicio" className="flex shrink-0 items-center text-white"><Logo size={26} /></motion.a>

        {/* Desktop navigation */}
        <motion.nav layout="position" className="hidden items-center gap-6 md:flex" aria-label="Navegación principal">
          {LINKS.map(({ href, label }) => <a key={href} href={href} className="type-ui whitespace-nowrap text-white/85 hover:text-white">{label}</a>)}
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="type-ui flex items-center gap-1.5 whitespace-nowrap text-white/85 hover:text-white"><FaGithub size={17} /><span>GitHub</span></a>
        </motion.nav>

        {/* Mobile hamburger */}
        <button type="button" onClick={() => setOpen((v) => !v)} aria-label={open ? "Cerrar menú" : "Abrir menú"} aria-expanded={open} className="flex h-9 w-9 items-center justify-center text-white md:hidden">
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
          className="pointer-events-auto mt-2 flex w-full max-w-[88%] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_96%,transparent)] p-2 shadow-[0_18px_44px_rgba(4,26,62,0.28)] md:hidden"
        >
          {LINKS.map(({ href, label }) => <a key={href} href={href} onClick={() => setOpen(false)} className="type-ui rounded-xl px-4 py-3 text-white/90 hover:bg-white/10 hover:text-white">{label}</a>)}
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)} className="type-ui flex items-center gap-2 rounded-xl px-4 py-3 text-white/90 hover:bg-white/10 hover:text-white"><FaGithub size={17} />GitHub</a>
        </motion.nav>}
      </AnimatePresence>
    </MotionConfig>
  </header>;
}
