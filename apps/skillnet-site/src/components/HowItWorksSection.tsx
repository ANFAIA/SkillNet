import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  Pause,
  Play,
  Video,
} from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t, type Copy } from "../i18n/ui";
import { trackEvent } from "../lib/analytics";
import { revealGroup, revealItem, useEntrance } from "./useEntrance";

const MODE_KEYS = ["texto", "imagen", "video", "audio"] as const;
const MODE_ICONS = { texto: FileText, imagen: ImageIcon, video: Video, audio: AudioLines } as const;

const VIDEO_FRAME_COUNT = 4;
const INFOGRAPHIC_IMAGES = {
  es: "/images/landing/multimodal/learning-differences-infographic-es-v4.webp",
  en: "/images/landing/multimodal/learning-differences-infographic-en-v4.webp",
} as const;

/** Bars in the audio waveform. Low enough that they stay legible on a 215px pane. */
const WAVEFORM_BARS = 28;

/**
 * Only one narration may sound at a time.
 *
 * Both cells hand their element to `playSolo`, which pauses whatever was
 * sounding before starting the new one. A single shared reference, so no cell
 * has to know the other exists and nothing sweeps the document for `<audio>`.
 */
let sounding: HTMLAudioElement | null = null;

function playSolo(audio: HTMLAudioElement) {
  if (sounding && sounding !== audio) sounding.pause();
  sounding = audio;
  return audio.play();
}

function releaseSolo(audio: HTMLAudioElement) {
  if (sounding === audio) sounding = null;
}

/** Index of the caption being spoken at `time`, given the locale's cut points. */
function frameAt(cuts: readonly number[], time: number): number {
  let index = 0;
  for (let i = 0; i < cuts.length && i < VIDEO_FRAME_COUNT; i += 1) {
    if (time >= cuts[i]) index = i;
  }
  return index;
}

function InfographicCell({ copy, lang }: { copy: Copy["howItWorks"]; lang: Locale }) {
  return <div className="media-image-wrap">
    <div className="media-image">
      <img src={INFOGRAPHIC_IMAGES[lang]} alt={copy.imageAlt} loading="lazy" decoding="async" />
    </div>
  </div>;
}

function VideoFrame({ position }: { position: number }) {
  return <div
    className={`media-video__scene media-video__scene--${position}`}
    role="img"
    aria-label=""
  />;
}

/**
 * The video cell: four photographic scenes with their caption, driven by a narration track.
 *
 * It is deliberately not a `<video>` — the piece is a short sequence of
 * images, and four webp frames plus one mp3 weigh a fraction of any encoded
 * clip. The frame and the caption both read the same `currentTime`, so what is on screen is always what is being said; a
 * second clock would drift against the voice within a line or two.
 *
 * With `prefers-reduced-motion` the narration still works — reduced motion is
 * about movement, not sound — but nothing starts on its own and the crossfade
 * is off (CSS). A step control appears as well, which simply seeks the
 * narration to the start of the next line, so stepping never puts a caption on
 * screen that disagrees with the voice.
 */
function VideoCell({ copy, lang, reduced }: { copy: Copy["howItWorks"]; lang: Locale; reduced: boolean }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const startedRef = useRef(false);
  const completedRef = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);

  // `timeupdate` only fires about four times a second, which is enough for a
  // progress bar but visibly late for a caption change. While the narration
  // sounds, read `currentTime` every frame instead -- still the audio's clock,
  // just sampled often enough that the caption turns over on the word.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const audio = audioRef.current;
      if (audio) setTime(audio.currentTime);
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [playing]);

  const cuts = copy.videoCuts;
  const index = frameAt(cuts, time);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void playSolo(audio).catch(() => setPlaying(false));
    else audio.pause();
  };

  const stepForward = () => {
    const audio = audioRef.current;
    if (!audio) return;
    const next = (index + 1) % VIDEO_FRAME_COUNT;
    audio.currentTime = cuts[next];
    setTime(cuts[next]);
  };

  return <div className="media-video">
    <div className="media-video__still">
      <div className="media-video__frames">
        {Array.from({ length: VIDEO_FRAME_COUNT }, (_, position) => <div
          key={position}
          className={`media-video__frame ${position === index ? "is-current" : ""}`}
        ><VideoFrame position={position} /></div>)}
      </div>
      <div className="media-video__overlay">
        <button
          type="button"
          className="media-play"
          onClick={toggle}
          aria-label={playing ? copy.videoPause : copy.videoPlay}
        >
          {playing ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
        </button>
        {reduced && <button type="button" className="media-video__step" onClick={stepForward} aria-label={copy.videoNext}>
          <ChevronRight size={18} />
        </button>}
        <span className="media-video__subtitle">{copy.videoCaptions[index]}</span>
      </div>
    </div>
    <audio
      ref={audioRef}
      src={`/audio/landing/how-it-works-video-${lang}.mp3`}
      preload="none"
      onPlay={() => {
        setPlaying(true);
        if (!startedRef.current) {
          startedRef.current = trackEvent("media_start", lang, {
            media_type: "video",
            media_name: "how_it_works",
          });
        }
      }}
      onPause={() => setPlaying(false)}
      onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
      onEnded={(event) => {
        if (!completedRef.current) {
          completedRef.current = trackEvent("media_complete", lang, {
            media_type: "video",
            media_name: "how_it_works",
          });
        }
        releaseSolo(event.currentTarget);
        event.currentTarget.currentTime = 0;
        setTime(0);
      }}
    />
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
  const startedRef = useRef(false);
  const completedRef = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void playSolo(audio).catch(() => setPlaying(false));
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
      onPlay={() => {
        setPlaying(true);
        if (!startedRef.current) {
          startedRef.current = trackEvent("media_start", lang, {
            media_type: "audio",
            media_name: "how_it_works",
          });
        }
      }}
      onPause={() => setPlaying(false)}
      onTimeUpdate={(event) => {
        const audio = event.currentTarget;
        setProgress(audio.duration ? audio.currentTime / audio.duration : 0);
      }}
      onEnded={(event) => {
        if (!completedRef.current) {
          completedRef.current = trackEvent("media_complete", lang, {
            media_type: "audio",
            media_name: "how_it_works",
          });
        }
        releaseSolo(event.currentTarget);
        setProgress(0);
      }}
    />
  </div>;
}

export default function HowItWorksSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).howItWorks;
  const reduced = useReducedMotion() ?? false;
  const [active, setActive] = useState<string>("texto");
  const { ref, state } = useEntrance<HTMLDivElement>(0.16);
  return <section id="como-funciona" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 pb-20 pt-10 sm:px-10 sm:pb-28 sm:pt-12">
    <motion.div ref={ref} initial={false} animate={state} variants={revealGroup} className="mx-auto w-full max-w-[80%]">
      <motion.h2 variants={revealItem} className="type-section-title text-[var(--color-text)]">{copy.title}</motion.h2>
      <motion.p variants={revealItem} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">{copy.lead}</motion.p>
      <motion.div variants={revealItem} className="multimodal-surface mt-12 sm:mt-16">
        {MODE_KEYS.map((key) => {
          const Icon = MODE_ICONS[key];
          const selected = active === key;
          // A cell is a plain container, not a button: two of them now hold real
          // controls, and a button inside a button is invalid and unreachable by
          // keyboard. Highlighting follows pointer and focus instead of a click.
          return <motion.div key={key} onMouseEnter={() => setActive(key)} onFocus={() => setActive(key)} className={`media-cell media-cell--${key} ${selected ? "is-active" : ""}`}>
            <span className="media-cell__label"><Icon size={19} strokeWidth={1.7} />{copy.modes[key]}</span>
            {key === "texto" && <div className="media-text"><strong>{copy.mediaHeading}</strong><p>{copy.idea}</p></div>}
            {key === "imagen" && <InfographicCell copy={copy} lang={lang} />}
            {key === "video" && <VideoCell copy={copy} lang={lang} reduced={reduced} />}
            {key === "audio" && <AudioCell copy={copy} lang={lang} />}
          </motion.div>;
        })}
      </motion.div>
      <motion.p variants={revealItem} className="type-caption mt-4 text-[var(--color-text-secondary)]">{copy.caption}</motion.p>
    </motion.div>
  </section>;
}
