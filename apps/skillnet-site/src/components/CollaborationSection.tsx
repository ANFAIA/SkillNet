import { ArrowUpRight, Wrench } from "lucide-react";
import { FaGithub } from "react-icons/fa";
import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";
import { GITHUB_URL } from "../data/links";

export default function CollaborationSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).collaboration;
  return <section id="open-source" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">{copy.title}</motion.h2>
      <motion.div initial={false} className="open-source-row mt-10">
        <div className="open-source-copy"><span className="open-source-status"><Wrench size={15} strokeWidth={1.8} aria-hidden="true" /> {copy.status}</span><div><p>{copy.body1}</p><p>{copy.body2}</p></div></div>
        <a className="open-source-card" href={GITHUB_URL} target="_blank" rel="noopener noreferrer"><FaGithub size={48} /><span><strong>{copy.cardTitle}</strong><small>{copy.cardDetail}</small></span><ArrowUpRight className="open-source-card__arrow" size={22} /></a>
      </motion.div>
    </div>
  </section>;
}
