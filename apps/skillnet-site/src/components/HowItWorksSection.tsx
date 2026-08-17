import { useState } from "react";
import { AudioLines, FileText, Image as ImageIcon, Pause, Play, Video } from "lucide-react";
import { motion } from "framer-motion";

const IDEA = "Todos aprendemos de forma distinta. Cambian lo que ya sabemos, el contexto, el ritmo y el apoyo que necesitamos. La misma idea puede necesitar otra explicación, otro ejemplo o una forma diferente de practicarla.";
const MODES = [
  { key: "texto", label: "Texto", Icon: FileText },
  { key: "imagen", label: "Imagen", Icon: ImageIcon },
  { key: "video", label: "Vídeo", Icon: Video },
  { key: "audio", label: "Audio", Icon: AudioLines },
] as const;

export default function HowItWorksSection() {
  const [active, setActive] = useState<string>("texto");
  return <section id="como-funciona" className="w-full scroll-mt-24 bg-white px-6 pb-20 pt-10 sm:px-10 sm:pb-28 sm:pt-12">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title text-[var(--color-text)]">Cómo funciona</motion.h2>
      <motion.p initial={false} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">A medida que la persona avanza por el curso, SkillNet reconoce qué conceptos domina, dónde necesita más apoyo y qué formas de explicación le resultan más útiles. Así, el curso evoluciona con ella —con explicaciones, práctica y evaluación— sin perder la referencia original ni los objetivos de aprendizaje.</motion.p>
      <motion.div initial={false} className="multimodal-surface mt-12 sm:mt-16">
        {MODES.map(({ key, label, Icon }) => {
          const selected = active === key;
          return <motion.button key={key} type="button" aria-pressed={selected} onClick={() => setActive(key)} className={`media-cell media-cell--${key} ${selected ? "is-active" : ""}`} whileHover={{ y: -2 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
            <span className="media-cell__label"><Icon size={19} strokeWidth={1.7} />{label}</span>
            {key === "texto" && <div className="media-text"><strong>Todos aprendemos de forma distinta.</strong><p>{IDEA}</p></div>}
            {key === "imagen" && <div className="media-image" role="img" aria-label="Infografía visual sobre cómo se construye la comprensión" />}
            {key === "video" && <div className="media-video"><div className="media-video__still"><span className="media-play"><Play size={22} fill="currentColor" /></span><span className="media-video__subtitle">The same idea may need another explanation, example or way to practise it.</span></div><div className="media-video__controls"><Play size={14} fill="currentColor" /><span>0:18</span><i /></div></div>}
            {key === "audio" && <div className="media-audio"><div className="media-audio__track"><span className="media-audio__play">{selected ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</span><div className="waveform" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${14 + ((index * 17) % 48)}px` }} />)}</div></div><p>“Todos aprendemos de forma distinta…”</p></div>}
          </motion.button>;
        })}
      </motion.div>
      <p className="type-caption mt-4 text-[var(--color-text-secondary)]">Una representación de la dirección del producto: el formato es solo una de las dimensiones que pueden adaptarse.</p>
    </div>
  </section>;
}
