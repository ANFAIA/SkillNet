import { Building2, GraduationCap, UserRound } from "lucide-react";
import { motion } from "framer-motion";

const PROFILES = [
  { label: "Empresas", Icon: Building2, detail: "Onboarding y formación interna sobre los procesos y la documentación que la organización ya tiene." },
  { label: "Educación", Icon: GraduationCap, detail: "Clases y materiales que conservan objetivos comunes mientras cambia la experiencia de cada estudiante." },
  { label: "Personas", Icon: UserRound, detail: "Aprendizaje por cuenta propia, al ritmo y con el nivel de detalle que cada uno necesita." },
];

export default function ProfilesSection() {
  return <section id="para-quien" data-nav-theme="light" className="w-full scroll-mt-24 bg-white px-6 py-12 sm:px-10 sm:py-16">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Para quién</motion.h2>
      <motion.p initial={false} className="type-lead mt-4 w-full text-[var(--color-text-secondary)]">El sistema es el mismo en los tres casos. Lo que cambia es quién decide qué hay que aprender y cuánto margen tiene cada persona para recorrerlo a su manera.</motion.p>
      <div className="profile-list mt-7">
        {PROFILES.map(({ label, Icon, detail }) => <motion.article key={label} initial={false} whileHover={{ y: -4 }} transition={{ duration: 0.28, ease: [0.38, 0.49, 0, 1] }} className="profile-card">
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
