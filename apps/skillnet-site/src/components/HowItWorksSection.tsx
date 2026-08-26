import { useState } from "react";
import { AudioLines, FileText, Image as ImageIcon, Pause, Play, Video } from "lucide-react";
import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";

const MODE_KEYS = ["texto", "imagen", "video", "audio"] as const;
const MODE_ICONS = { texto: FileText, imagen: ImageIcon, video: Video, audio: AudioLines } as const;

export default function HowItWorksSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).howItWorks;
  const [active, setActive] = useState<string>("texto");
  return <section id="como-funciona" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 pb-20 pt-10 sm:px-10 sm:pb-28 sm:pt-12">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title text-[var(--color-text)]">{copy.title}</motion.h2>
      <motion.p initial={false} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">{copy.lead}</motion.p>
      <motion.div initial={false} className="multimodal-surface mt-12 sm:mt-16">
        {MODE_KEYS.map((key) => {
          const Icon = MODE_ICONS[key];
          const selected = active === key;
          return <motion.button key={key} type="button" aria-pressed={selected} onClick={() => setActive(key)} className={`media-cell media-cell--${key} ${selected ? "is-active" : ""}`} whileHover={{ y: -2 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
            <span className="media-cell__label"><Icon size={19} strokeWidth={1.7} />{copy.modes[key]}</span>
            {key === "texto" && <div className="media-text"><strong>{copy.mediaHeading}</strong><p>{copy.idea}</p></div>}
            {key === "imagen" && <div className="media-image" role="img" aria-label={copy.imageAlt} />}
            {key === "video" && <div className="media-video"><div className="media-video__still"><span className="media-play"><Play size={22} fill="currentColor" /></span><span className="media-video__subtitle">{copy.videoSubtitle}</span></div><div className="media-video__controls"><Play size={14} fill="currentColor" /><span>0:18</span><i /></div></div>}
            {key === "audio" && <div className="media-audio"><div className="media-audio__track"><span className="media-audio__play">{selected ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</span><div className="waveform" aria-hidden="true">{Array.from({ length: 48 }, (_, index) => <i key={index} style={{ height: `${14 + ((index * 17) % 48)}px` }} />)}</div></div><p>{copy.audioQuote}</p></div>}
          </motion.button>;
        })}
      </motion.div>
      <p className="type-caption mt-4 text-[var(--color-text-secondary)]">{copy.caption}</p>
    </div>
  </section>;
}
