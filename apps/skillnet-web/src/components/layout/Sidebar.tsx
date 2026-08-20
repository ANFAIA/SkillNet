import { useCallback, useMemo } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useTransform,
  type PanInfo,
} from 'framer-motion'
import { useIntl } from 'react-intl'
import { useEnrollments } from '../../api/enrollments'
import { useWorkspaceMode } from '../../hooks/useAuth'
import type { WorkspaceMode } from '../../types'
import { useSidebar } from '../../contexts/SidebarContext'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { backdrop, sidebarSlide } from '../../lib/motion'
import { Logo } from '../ui'
import { ContinueCoursePanel } from './ContinueCoursePanel'
import { NavPill } from './NavPill'

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
  end?: boolean
  /** Stable anchor for the product tour spotlight (docs/design/onboarding.md). */
  tourId?: string
}

export type SidebarRole = 'employee' | 'admin'

function useNavItems(role: SidebarRole, mode: WorkspaceMode): NavItem[] {
  const intl = useIntl()
  return useMemo(
    () => {
      const individual = mode === 'individual'
      return role === 'employee' ? [
      {
        label: intl.formatMessage({ id: 'nav.home' }),
        to: '/empleado',
        end: true,
        icon: (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
        ),
      },
      {
        label: intl.formatMessage({ id: 'nav.courses' }),
        to: '/empleado/cursos',
        icon: (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
        ),
      },
      {
        label: intl.formatMessage({ id: 'nav.skillmap' }),
        to: '/empleado/skillmap',
        icon: (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        ),
      },
      {
        label: intl.formatMessage({ id: 'nav.chat' }),
        to: '/empleado/chat',
        icon: (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        ),
      },
    ] : [
      {
        label: intl.formatMessage({ id: 'admin.nav.home' }),
        to: '/admin',
        end: true,
        tourId: 'admin-home',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>,
      },
      {
        label: intl.formatMessage({ id: 'admin.nav.employees' }),
        to: '/admin/empleados',
        tourId: 'admin-employees',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>,
      },
      {
        label: intl.formatMessage({ id: 'admin.nav.talent' }),
        to: '/admin/talento',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3 4 7l8 4 8-4-8-4Z" /><path d="m4 12 8 4 8-4" /><path d="m4 17 8 4 8-4" /></svg>,
      },
      {
        label: intl.formatMessage({ id: 'admin.nav.content' }),
        to: '/admin/contenido',
        tourId: 'admin-content',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>,
      },
      {
        label: intl.formatMessage({ id: 'admin.nav.createCourse' }),
        to: '/admin/crear-curso',
        tourId: 'admin-create-course',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" /></svg>,
      },
      {
        label: intl.formatMessage({ id: 'admin.nav.chat' }),
        to: '/admin/chat',
        icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
      },
    ]
      // In an individual deployment the owner administers and learns alone: the
      // collective pages do not exist, and "Content" reads as "My courses".
      .filter((item) => !individual || (item.to !== '/admin/empleados' && item.to !== '/admin/talento'))
      .map((item) =>
        individual && item.to === '/admin/contenido'
          ? { ...item, label: intl.formatMessage({ id: 'admin.nav.myCourses' }) }
          : item,
      )
    },
    [intl, role, mode],
  )
}

function SidebarToggleIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d={collapsed ? 'm9 18 6-6-6-6' : 'm15 18-6-6 6-6'} />
    </svg>
  )
}

function EmployeeContinueCourse({ onNavigate }: { onNavigate: () => void }) {
  const { data: enrollmentData } = useEnrollments()
  const activeEnrollment = enrollmentData?.items
    .filter(
      (enrollment) =>
        (enrollment.status === 'in_progress' || enrollment.status === 'overdue') &&
        (enrollment.progress ?? 0) < 1,
    )
    .sort((a, b) => (b.progress ?? 0) - (a.progress ?? 0))[0]

  if (!activeEnrollment) return null
  return <ContinueCoursePanel enrollment={activeEnrollment} onNavigate={onNavigate} />
}

const TYPE_CHAR = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

/**
 * The sidebar label as a typewriter: on expand the letters are written in
 * left-to-right, cascaded per nav item; on collapse they are erased from the end
 * (staggerDirection -1). The outer span still owns the layout collapse (max-width)
 * so the icon can center when narrow; the per-letter reveal rides on top.
 */
function TypewriterLabel({
  text,
  expanded,
  index = 0,
}: {
  text: string
  expanded: boolean
  index?: number
}) {
  const reduced = useReducedMotion()
  return (
    <span
      className={`relative z-10 overflow-hidden whitespace-nowrap transition-[max-width,margin] duration-[300ms] [transition-timing-function:var(--ease-base)] ${
        expanded ? 'ml-3 max-w-40 delay-0' : 'ml-0 max-w-0 delay-[180ms]'
      }`}
    >
      <span className="sr-only">{text}</span>
      {reduced ? (
        <span aria-hidden="true" className={expanded ? 'opacity-100' : 'opacity-0'}>
          {text}
        </span>
      ) : (
        <motion.span
          aria-hidden="true"
          className="inline-block"
          initial={false}
          animate={expanded ? 'visible' : 'hidden'}
          variants={{
            visible: { transition: { staggerChildren: 0.015, delayChildren: 0.06 + index * 0.015 } },
            hidden: { transition: { staggerChildren: 0.016, staggerDirection: -1 } },
          }}
        >
          {Array.from(text).map((ch, i) => (
            <motion.span key={i} variants={TYPE_CHAR} transition={{ duration: 0.02 }} className="whitespace-pre">
              {ch}
            </motion.span>
          ))}
        </motion.span>
      )}
    </span>
  )
}

function SidebarContent({
  collapsed,
  pillId,
  showCollapse = false,
  role,
}: {
  collapsed: boolean
  pillId: string
  showCollapse?: boolean
  role: SidebarRole
}) {
  const { closeMobile, toggleCollapsed } = useSidebar()
  const intl = useIntl()
  const mode = useWorkspaceMode()
  const navItems = useNavItems(role, mode)

  return (
    <>
      <div className={`flex min-h-12 items-center gap-3 px-4 ${collapsed ? 'justify-center' : ''}`}>
        {(!collapsed || !showCollapse) && (
          <>
            <Logo size={32} className="shrink-0" />
            <span className="min-w-0 max-w-32 overflow-hidden whitespace-nowrap">
              <strong className="text-sm font-semibold text-text">SkillNet</strong>
            </span>
          </>
        )}

        {showCollapse && (
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={intl.formatMessage({
              id: collapsed ? 'nav.expandSidebar' : 'nav.collapseSidebar',
            })}
            aria-expanded={!collapsed}
            title={intl.formatMessage({
              id: collapsed ? 'nav.expandSidebar' : 'nav.collapseSidebar',
            })}
            className={`${collapsed ? '' : 'ml-auto'} grid size-8 shrink-0 place-items-center rounded-full text-text-muted transition-colors hover:text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 cursor-pointer`}
          >
            <SidebarToggleIcon collapsed={collapsed} />
          </button>
        )}
      </div>

      <nav className="mt-5 flex flex-col gap-1.5">
        {navItems.map((item, itemIndex) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={closeMobile}
            data-tour={item.tourId}
            className={({ isActive }) =>
              `relative flex h-[42px] items-center ml-3 rounded-l-xl pl-3 pr-4 text-sm font-medium transition-colors duration-200 ${
                isActive ? 'text-text' : 'text-text-secondary hover:text-text'
              }`
            }
            title={collapsed ? item.label : undefined}
          >
            {({ isActive }) => (
              <>
                {isActive && <NavPill layoutId={pillId} collapsed={collapsed} connected />}
                <span className="relative z-10 shrink-0">{item.icon}</span>
                <TypewriterLabel text={item.label} expanded={!collapsed} index={itemIndex} />
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="flex-1" />

      {role === 'employee' && !collapsed && <EmployeeContinueCourse onNavigate={closeMobile} />}

      <nav className="pb-3">
        <NavLink
          to={role === 'employee' ? '/empleado/ajustes' : '/admin/ajustes'}
          onClick={closeMobile}
          className={({ isActive }) =>
            `relative flex h-[42px] items-center ml-3 rounded-l-xl pl-3 pr-4 text-sm font-medium transition-colors duration-200 ${
              isActive ? 'text-text' : 'text-text-secondary hover:text-text'
            }`
          }
          title={collapsed ? intl.formatMessage({ id: 'nav.settings' }) : undefined}
        >
          {({ isActive }) => (
            <>
              {isActive && <NavPill layoutId={pillId} collapsed={collapsed} connected />}
              <span className="relative z-10 shrink-0">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.09 14H3v-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.09V3h4v.09A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.36 9 1.7 1.7 0 0 0 20.91 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15z" />
                </svg>
              </span>
              <TypewriterLabel
                text={intl.formatMessage({ id: role === 'employee' ? 'nav.settings' : 'admin.nav.settings' })}
                expanded={!collapsed}
                index={navItems.length}
              />
            </>
          )}
        </NavLink>
      </nav>

    </>
  )
}

export function Sidebar({ role = 'employee' }: { role?: SidebarRole }) {
  const { collapsed, mobileOpen, closeMobile } = useSidebar()
  const reducedMotion = useReducedMotion()
  const dragX = useMotionValue(0)
  const backdropOpacity = useTransform(dragX, [-248, 0], [0, 1])

  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      if (info.velocity.x < -100 || info.offset.x < -100) closeMobile()
    },
    [closeMobile],
  )

  return (
    <>
      <aside
        className={`connected-sidebar group/sidebar fixed inset-y-0 left-0 z-20 hidden flex-col transition-[width] duration-[320ms] [transition-timing-function:var(--ease-base)] motion-reduce:transition-none md:flex ${
          collapsed ? 'w-16 delay-[180ms]' : 'w-[248px] delay-0'
        }`}
      >
        <SidebarContent collapsed={collapsed} pillId={`${role}-nav-pill`} showCollapse role={role} />
      </aside>

      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              {...backdrop}
              style={{ opacity: backdropOpacity }}
              className="fixed inset-0 z-30 bg-black/10 backdrop-blur-sm md:hidden"
              onClick={closeMobile}
            />
            <motion.aside
              {...sidebarSlide}
              style={{ x: dragX }}
              drag={reducedMotion ? false : 'x'}
              dragConstraints={{ left: -248, right: 0 }}
              dragElastic={0.1}
              dragSnapToOrigin
              onDragEnd={handleDragEnd}
              className="connected-sidebar fixed inset-y-0 left-0 z-40 flex w-[248px] touch-none flex-col md:hidden"
            >
              <SidebarContent collapsed={false} pillId={`${role}-nav-pill-mobile`} role={role} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
