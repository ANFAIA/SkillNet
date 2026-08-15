import { Building2, GraduationCap, Presentation, UserRound } from "lucide-react";
import { motion } from "framer-motion";

const PROFILES = [
  { label: "Empresas", detail: "Onboarding y formación interna a partir de la documentación propia de la organización.", Icon: Building2 },
  { label: "Educación", detail: "Clases y materiales que conservan objetivos comunes mientras cambia la experiencia de cada estudiante.", Icon: GraduationCap },
  { label: "Formación", detail: "Programas que pueden adaptarse al contexto de cada cliente sin rehacerse desde cero.", Icon: Presentation },
  { label: "Personas", detail: "Aprendizaje individual a partir de apuntes, documentos, webs y otras fuentes propias.", Icon: UserRound },
];

export default function ProfilesSection() {
  return <section id="para-quien" className="w-full scroll-mt-24 bg-white px-6 py-20 sm:px-10 sm:py-28">
    <div className="mx-auto w-full max-w-[80%]">
      <motion.h2 initial={false} className="type-section-title">Para quién</motion.h2>
      <motion.p initial={false} className="type-lead mt-7 w-full text-[var(--color-text-secondary)]">Esta misma idea puede aplicarse al onboarding y la formación interna de una empresa, a una clase, a un programa formativo o al aprendizaje individual con materiales propios.</motion.p>
      <div className="profile-list mt-14">
        {PROFILES.map(({ label, detail, Icon }) => <motion.article key={label} initial={false} whileHover={{ y: -4 }} transition={{ duration: 0.28, ease: [0.38, 0.49, 0, 1] }} className="profile-card">
          <span className="profile-card__icon"><Icon size={24} strokeWidth={1.6} /></span>
          <div><h3>{label}</h3><p>{detail}</p></div>
        </motion.article>)}
      </div>
    </div>
  </section>;
}
