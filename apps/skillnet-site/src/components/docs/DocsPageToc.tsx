import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

export interface DocsPageHeading {
  slug: string;
  text: string;
}

interface Props {
  headings: DocsPageHeading[];
  locale: "es" | "en";
}

const COPY = {
  es: { title: "En esta página", current: "Sección actual" },
  en: { title: "On this page", current: "Current section" },
} as const;

export default function DocsPageToc({ headings, locale }: Props) {
  const [activeSlug, setActiveSlug] = useState(headings[0]?.slug ?? "");
  const copy = COPY[locale];

  useEffect(() => {
    if (headings.length === 0) return;

    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const readingLine = window.scrollY + 128;
        let current = headings[0].slug;

        for (const heading of headings) {
          const element = document.getElementById(heading.slug);
          if (element && element.offsetTop <= readingLine) current = heading.slug;
        }

        setActiveSlug(current);
      });
    };

    sync();
    window.addEventListener("scroll", sync, { passive: true });
    document.addEventListener("astro:page-load", sync);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", sync);
      document.removeEventListener("astro:page-load", sync);
    };
  }, [headings]);

  const links = (className: string) => (
    <nav aria-label={copy.title} className={className}>
      {headings.map((heading) => (
        <a
          key={heading.slug}
          href={`#${heading.slug}`}
          className="docs-page-toc__link"
          aria-current={activeSlug === heading.slug ? "location" : undefined}
        >
          {heading.text}
        </a>
      ))}
    </nav>
  );

  const activeHeading = headings.find((heading) => heading.slug === activeSlug)?.text;

  return (
    <>
      <aside className="docs-page-toc docs-page-toc--desktop">
        <p className="docs-page-toc__title">{copy.title}</p>
        {links("docs-page-toc__list")}
      </aside>

      <details className="docs-page-toc docs-page-toc--mobile">
        <summary className="docs-page-toc__summary">
          <span>{copy.title}</span>
          {activeHeading && <small aria-label={copy.current}>{activeHeading}</small>}
          <ChevronDown className="docs-page-toc__chevron" size={16} strokeWidth={1.75} aria-hidden="true" />
        </summary>
        {links("docs-page-toc__list docs-page-toc__list--mobile")}
      </details>
    </>
  );
}
