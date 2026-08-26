import { useEffect, useRef, useState } from "react";
import { AudioLines, ChevronRight, FileText, Image as ImageIcon, Pause, Play, Video } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t, type Copy } from "../i18n/ui";

const MODE_KEYS = ["texto", "imagen", "video", "audio"] as const;
const MODE_ICONS = { texto: FileText, imagen: ImageIcon, video: Video, audio: AudioLines } as const;

/** The four frames of the video sequence, in order. They are real files, not a mock-up. */
const VIDEO_FRAMES = [
  "/images/landing/multimodal/learning-differences-video-frame-v1.webp",
  "/images/landing/multimodal/learning-differences-video-frame-2-v1.webp",
  "/images/landing/multimodal/learning-differences-video-frame-3-v1.webp",
  "/images/landing/multimodal/learning-differences-video-frame-4-v1.webp",
] as const;

/** Seconds each frame holds. Four frames make a 14 s sequence. */
const FRAME_SECONDS = 3.5;
const VIDEO_SECONDS = VIDEO_FRAMES.length * FRAME_SECONDS;

/** Bars in the audio waveform. Low enough that they stay legible on a 215px pane. */
const WAVEFORM_BARS = 28;

function formatTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * The video cell: four stills with their caption, advancing on a real clock.
 *
 * It is deliberately not a `<video>` — the piece really is a short sequence of
 * images, and four webp frames weigh a fraction of any encoded clip. With
 * `prefers-reduced-motion` there is no timer at all: the play control becomes a
 * step control and the viewer advances the sequence themselves.
 */
function VideoCell({ copy, reduced }: { copy: Copy["howItWorks"]; reduced: boolean }) {
  const [playing, setPlaying] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [step, setStep] = useState(0);
  const elapsedRef = useRef(0);
  elapsedRef.current = elapsed;

  useEffect(() => {
    if (!playing || reduced) return;
    const start = performance.now() - elapsedRef.current * 1000;
    const id = window.setInterval(() => {
      const next = (performance.now() - start) / 1000;
      if (next >= VIDEO_SECONDS) {
        setElapsed(0);
        setPlaying(false);
        return;
      }
      setElapsed(next);
    }, 100);
    return () => window.clearInterval(id);
  }, [playing, reduced]);

  const index = reduced
    ? step
    : Math.min(VIDEO_FRAMES.length - 1, Math.floor(elapsed / FRAME_SECONDS));
  const progress = reduced
    ? ((step + 1) / VIDEO_FRAMES.length) * 100
    : (elapsed / VIDEO_SECONDS) * 100;
  const label = reduced ? copy.videoNext : playing ? copy.videoPause : copy.videoPlay;

  const advance = () => {
    if (reduced) {
      setStep((prev) => (prev + 1) % VIDEO_FRAMES.length);
      return;
    }
    setPlaying((prev) => !prev);
  };

  return <div className="media-video">
    <div className="media-video__still">
      <div className="media-video__frames">
        {VIDEO_FRAMES.map((src, position) => <img
          key={src}
          className={`media-video__frame ${position === index ? "is-current" : ""}`}
          src={src}
          alt=""
          width={1672}
          height={941}
          decoding="async"
        />)}
      </div>
      <div className="media-video__overlay">
        <button type="button" className="media-play" onClick={advance} aria-label={label}>
          {reduced ? <ChevronRight size={22} /> : playing ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
        </button>
        <span className="media-video__subtitle">{copy.videoCaptions[index]}</span>
      </div>
    </div>
    <div className="media-video__controls">
      {reduced ? <ChevronRight size={14} /> : playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" />}
      <span>{reduced ? `${step + 1}/${VIDEO_FRAMES.length}` : `${formatTime(elapsed)} / ${formatTime(VIDEO_SECONDS)}`}</span>
      <i style={{ "--progress": `${progress}%` } as React.CSSProperties} />
    </div>
  </div>;
}

/**
 * The audio cell: the real audio overview for the page's language.
 *
 * `preload="none"` so the mp3 costs nothing until someone asks for it, and the
 * waveform is drawn from `currentTime` rather than being decorative.
 */
function AudioCell({ copy, lang }: { copy: Copy["howItWorks"]; lang: Locale }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play().catch(() => setPlaying(false));
    else audio.pause();
  };

  return <div className="media-audio">
    <div className="media-audio__track">
      <button
        type="button"
        className="media-audio__play"
        onClick={toggle}
        aria-label={playing ? copy.audioPause : copy.audioPlay}
      >
        {playing ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}
      </button>
      <div className="waveform" aria-hidden="true">
        {Array.from({ length: WAVEFORM_BARS }, (_, index) => <i
          key={index}
          className={index / WAVEFORM_BARS < progress ? "is-played" : ""}
          style={{ height: `${16 + ((index * 23) % 44)}px` }}
        />)}
      </div>
    </div>
    <p>{copy.audioQuote}</p>
    <audio
      ref={audioRef}
      src={`/audio/landing/how-it-works-audio-${lang}.mp3`}
      preload="none"
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onTimeUpdate={(event) => {
        const audio = event.currentTarget;
        setProgress(audio.duration ? audio.currentTime / audio.duration : 0);
      }}
      onEnded={() => setProgress(0)}
    />
  </div>;
}

export default function HowItWorksSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).howItWorks;
  const reduced = useReducedMotion() ?? false;
  const [active, setActive] = useState<string>("texto");
  return <section id="como-funciona" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 pb-20 pt-10 sm:px-10 sm:pb-28 sm:pt-12">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title text-[var(--color-text)]">{copy.title}</motion.h2>
      <motion.p initial={false} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">{copy.lead}</motion.p>
      <motion.div initial={false} className="multimodal-surface mt-12 sm:mt-16">
        {MODE_KEYS.map((key) => {
          const Icon = MODE_ICONS[key];
          const selected = active === key;
          // A cell is a plain container, not a button: two of them now hold real
          // controls, and a button inside a button is invalid and unreachable by
          // keyboard. Highlighting follows pointer and focus instead of a click.
          return <motion.div key={key} onMouseEnter={() => setActive(key)} onFocus={() => setActive(key)} className={`media-cell media-cell--${key} ${selected ? "is-active" : ""}`} whileHover={{ y: -2 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
            <span className="media-cell__label"><Icon size={19} strokeWidth={1.7} />{copy.modes[key]}</span>
            {key === "texto" && <div className="media-text"><strong>{copy.mediaHeading}</strong><p>{copy.idea}</p></div>}
            {key === "imagen" && <div className="media-image" role="img" aria-label={copy.imageAlt} />}
            {key === "video" && <VideoCell copy={copy} reduced={reduced} />}
            {key === "audio" && <AudioCell copy={copy} lang={lang} />}
          </motion.div>;
        })}
      </motion.div>
      <p className="type-caption mt-4 text-[var(--color-text-secondary)]">{copy.caption}</p>
    </div>
  </section>;
}
