import { Building2, GraduationCap, UserRound } from "lucide-react";
import { motion } from "framer-motion";

const PROFILES = [
  { label: "Empresas", Icon: Building2, detail: "Onboarding y formación interna a partir de la documentación propia de la organización." },
  { label: "Educación", Icon: GraduationCap, detail: "Clases y materiales que conservan objetivos comunes mientras cambia la experiencia de cada estudiante." },
  { label: "Personas", Icon: UserRound, detail: "Aprendizaje individual a partir de apuntes, documentos, webs y otras fuentes propias." },
];

export default function ProfilesSection() {
  return <section id="para-quien" className="w-full scroll-mt-24 bg-white px-6 py-12 sm:px-10 sm:py-16">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Para quién</motion.h2>
      <motion.p initial={false} className="type-lead mt-4 w-full text-[var(--color-text-secondary)]">Esta misma idea puede aplicarse al onboarding y la formación interna de una empresa, a una clase o al aprendizaje individual con materiales propios.</motion.p>
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
