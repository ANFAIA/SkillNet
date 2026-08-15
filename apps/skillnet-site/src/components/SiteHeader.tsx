import { useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { FaGithub } from "react-icons/fa";

const GITHUB_URL = "https://github.com/ANFAIA/SkillNet";
const LOGO_URL = "/images/brand/skillnet-head-symbol.svg";
const TRANSITION = { type: "tween", duration: 0.6, ease: [0.38, 0.49, 0, 1] } as const;

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
      <motion.div layout className={`pointer-events-auto ${scrolled ? "mt-3 flex items-center gap-4 rounded-full border border-white/15 bg-[var(--color-primary-deep)] px-5 py-2.5 sm:gap-6 sm:px-6" : "mt-6 flex w-full max-w-[80%] items-center justify-between"}`}>
        <motion.a layout href="#" aria-label="Volver al inicio" className="flex items-center gap-2"><img src={LOGO_URL} alt="" className="h-6 w-auto sm:h-7" /><AnimatePresence initial={false}>{!scrolled && <motion.span key="wordmark" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="type-ui whitespace-nowrap font-semibold text-white">SkillNet</motion.span>}</AnimatePresence></motion.a>
        <motion.nav layout="position" className="flex items-center gap-3 sm:gap-6" aria-label="Navegación principal">
          <a href="#que-es-skillnet" className="type-ui hidden whitespace-nowrap text-white/85 hover:text-white md:block">Qué es SkillNet</a>
          <a href="#como-funciona" className="type-ui hidden whitespace-nowrap text-white/85 hover:text-white min-[520px]:block">Cómo funciona</a>
          <a href="#para-quien" className="type-ui whitespace-nowrap text-white/85 hover:text-white">Para quién</a>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="type-ui flex items-center gap-1.5 whitespace-nowrap text-white/85 hover:text-white"><FaGithub size={17} /><span className="hidden sm:inline">GitHub</span></a>
        </motion.nav>
      </motion.div>
    </MotionConfig>
  </header>;
}
