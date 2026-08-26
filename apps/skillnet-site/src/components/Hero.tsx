import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { GITHUB_URL } from "../data/links";

const BACKGROUND_URL = "/images/landing/skillnet-learning-commons-background-v1.webp";

/** Section ids are shared by both locales, so the anchor needs no translation. */
const MORE_ANCHOR = "#que-es-skillnet";

export default function Hero({ lang = "es" }: { lang?: Locale }) {
  const COPY = t(lang).hero;

  return (
    <section data-nav-theme="dark" className="relative h-screen w-full overflow-hidden bg-[var(--color-primary-deep)]">
      {/* Depth 1: illustration, background plane — fully static */}
      <div
        aria-hidden="true"
        role="img"
        aria-label=""
        style={{
          backgroundImage: `url(${BACKGROUND_URL})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
        className="pointer-events-none fixed inset-0"
      />

      {/* Depth 2: colour glow, mid plane — fully static */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--color-primary-deep)]/70 via-transparent to-[var(--color-primary-deep)]/80" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
      </div>

      {/* Depth 3: foreground copy, stays essentially still */}
      <div className="relative mx-auto flex h-full w-full max-w-[80%] flex-col items-center justify-center text-center">
        <h1 className="hero-rise type-display w-full text-balance text-white">{COPY.title}</h1>

        <p className="hero-rise hero-rise--delay-1 type-lead mx-auto mt-6 max-w-2xl text-balance text-white/85">
          {COPY.subtitle}
        </p>

        <div className="hero-rise hero-rise--delay-2 mt-10 flex flex-col items-center gap-4 sm:flex-row">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="type-ui rounded-lg bg-white px-6 py-3 text-[var(--color-text)] transition-opacity duration-200 ease-out hover:opacity-90"
          >
            {COPY.github}
          </a>

          <a
            href={MORE_ANCHOR}
            className="type-ui rounded-lg border border-white/70 bg-transparent px-6 py-3 text-white transition-colors duration-200 ease-out hover:bg-white/10"
          >
            {COPY.moreCta}
          </a>
        </div>
      </div>
    </section>
  );
}
