import { useEffect, useState } from "react";
import { MotionConfig, motion } from "framer-motion";
import { FaGithub } from "react-icons/fa";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const LOGO_URL = "/images/brand/skillnet-head-symbol.svg";
const TRANSITION = { type: "tween", duration: 0.52, ease: [0.22, 1, 0.36, 1] } as const;

export default function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center">
    <MotionConfig transition={TRANSITION}>
      <motion.div
        layout
        initial={false}
        style={{ willChange: "transform, width, border-radius" }}
        className={`pointer-events-auto flex items-center ${scrolled ? "mt-3 gap-4 rounded-full border border-white/15 bg-[color-mix(in_srgb,var(--color-primary-deep)_94%,transparent)] px-5 py-2.5 shadow-[0_12px_34px_rgba(4,26,62,0.18)] backdrop-blur-md sm:gap-6 sm:px-6" : "mt-6 w-full max-w-[80%] justify-between"}`}
      >
        <motion.a layout="position" href="#" aria-label="Volver al inicio" className="flex shrink-0 items-center"><img src={LOGO_URL} alt="" className="h-6 w-auto sm:h-7" /></motion.a>
        <motion.nav layout="position" className="flex items-center gap-3 sm:gap-6" aria-label="Navegación principal">
          <a href="#que-es-skillnet" className="type-ui hidden whitespace-nowrap text-white/85 hover:text-white md:block">Qué es SkillNet</a>
          <a href="#como-funciona" className="type-ui hidden whitespace-nowrap text-white/85 hover:text-white min-[520px]:block">Cómo funciona</a>
          <a href="#para-quien" className="type-ui whitespace-nowrap text-white/85 hover:text-white">Para quién</a>
          <a href="#contacto" className="type-ui hidden whitespace-nowrap text-white/85 hover:text-white min-[520px]:block">Contacto</a>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="type-ui flex items-center gap-1.5 whitespace-nowrap text-white/85 hover:text-white"><FaGithub size={17} /><span className="hidden sm:inline">GitHub</span></a>
        </motion.nav>
      </motion.div>
    </MotionConfig>
  </header>;
}
