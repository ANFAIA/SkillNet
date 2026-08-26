import { Building2, GraduationCap, UserRound } from "lucide-react";
import { motion } from "framer-motion";
import type { Locale } from "../i18n/config";
import { t } from "../i18n/ui";

export default function ProfilesSection({ lang = "es" }: { lang?: Locale }) {
  const copy = t(lang).profiles;
  const profiles = [
    { ...copy.companies, Icon: Building2 },
    { ...copy.education, Icon: GraduationCap },
    { ...copy.individuals, Icon: UserRound },
  ];
  return <section id="para-quien" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 py-12 sm:px-10 sm:py-16">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">{copy.title}</motion.h2>
      <motion.p initial={false} className="type-lead mt-4 w-full text-[var(--color-text-secondary)]">{copy.lead}</motion.p>
      <div className="profile-list mt-7">
        {profiles.map(({ label, Icon, detail }) => <motion.article key={label} initial={false} whileHover={{ y: -4 }} transition={{ duration: 0.28, ease: [0.38, 0.49, 0, 1] }} className="profile-card">
          <div className="profile-card__head">
            <h3>{label}</h3>
            <span className="profile-card__icon" aria-hidden="true"><Icon size={26} strokeWidth={1.6} /></span>
          </div>
          <p>{detail}</p>
        </motion.article>)}
      </div>
    </div>
  </section>;
}
