type TalentMetricIconProps = {
  kind: 'people' | 'enrollments' | 'progress' | 'completed' | 'skills'
}

const paths = {
  people: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /></>,
  enrollments: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></>,
  progress: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  completed: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
  skills: <><path d="m12 2 2.8 5.7L21 8.6l-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 8.6l6.2-.9z" /></>,
}

export function TalentMetricIcon({ kind }: TalentMetricIconProps) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[kind]}
    </svg>
  )
}
