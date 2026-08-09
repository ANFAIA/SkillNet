import { useMemo, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useTransform,
  type PanInfo,
} from 'framer-motion'
import { useIntl } from 'react-intl'
import { useSidebar } from '../../contexts/SidebarContext'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { NavPill } from './NavPill'
import { backdrop, sidebarSlide } from '../../lib/motion'

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
  end?: boolean
}

function useNavItems(): NavItem[] {
  const intl = useIntl()
  return useMemo(() => [
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
  ], [intl])
}

function SpiderIcon() {
  return (
    <svg width="60" height="60" viewBox="0 0 576 512" fill="currentColor" className="absolute -bottom-2 -right-2 text-white/[0.04]">
      <path d="M563.3 401.6c2.608 8.443-2.149 17.4-10.62 19.1l-15.35 4.709c-8.48 2.6-17.47-2.139-20.08-10.59L493.2 338l-79.79-31.8l53.47 62.15c5.08 5.904 6.972 13.89 5.08 21.44l-28.23 110.1c-2.151 8.57-10.87 13.78-19.47 11.64l-15.58-3.873c-8.609-2.141-13.84-10.83-11.69-19.4l25.2-98.02l-38.51-44.77c.1529 2.205.6627 4.307.6627 6.549c0 53.02-43.15 96-96.37 96S191.6 405 191.6 352c0-2.242.5117-4.34.6627-6.543l-38.51 44.76l25.2 98.02c2.151 8.574-3.084 17.26-11.69 19.4l-15.58 3.873c-8.603 2.141-17.32-3.072-19.47-11.64l-28.23-110.1c-1.894-7.543 0-15.53 5.08-21.44l53.47-62.15l-79.79 31.8l-24.01 77.74c-2.608 8.447-11.6 13.19-20.08 10.59l-15.35-4.709c-8.478-2.6-13.23-11.55-10.63-19.1l27.4-88.69c2.143-6.939 7.323-12.54 14.09-15.24L158.9 256l-104.7-41.73C47.43 211.6 42.26 205.1 40.11 199.1L12.72 110.4c-2.608-8.443 2.149-17.4 10.62-19.1l15.35-4.709c8.48-2.6 17.47 2.139 20.08 10.59l24.01 77.74l79.79 31.8L109.1 143.6C104 137.7 102.1 129.7 104 122.2l28.23-110.1c2.151-8.57 10.87-13.78 19.47-11.64l15.58 3.873C175.9 6.494 181.1 15.18 178.1 23.76L153.8 121.8L207.7 184.4l.1542-24.44C206.1 123.4 228.9 91.77 261.4 80.43c5.141-1.793 10.5 2.215 10.5 7.641V112h32.12V88.09c0-5.443 5.394-9.443 10.55-7.641C345.9 91.39 368.3 121 368.3 155.9c0 1.393-.1786 2.689-.2492 4.064L368.3 184.4l53.91-62.66l-25.2-98.02c-2.151-8.574 3.084-17.26 11.69-19.4l15.58-3.873c8.603-2.141 17.32 3.072 19.47 11.64l28.23 110.1c1.894 7.543 0 15.53-5.08 21.44l-53.47 62.15l79.79-31.8l24.01-77.74c2.608-8.447 11.6-13.19 20.08-10.59l15.35 4.709c8.478 2.6 13.23 11.55 10.63 19.1l-27.4 88.69c-2.143 6.939-7.323 12.54-14.09 15.24L417.1 256l104.7 41.73c6.754 2.691 11.92 8.283 14.07 15.21L563.3 401.6z"/>
    </svg>
  )
}

function SidebarContent({ collapsed, pillId }: { collapsed: boolean; pillId: string }) {
  const { closeMobile } = useSidebar()
  const intl = useIntl()
  const navItems = useNavItems()

  return (
    <>
      {/* Logo */}
      <div className="flex flex-col items-center py-5 gap-1">
        <img
          src="/logo.png"
          alt="SkillNet"
          className="drop-shadow-lg transition-[width,height] duration-300 [transition-timing-function:var(--ease-base)]"
          style={{ width: collapsed ? 32 : 40, height: collapsed ? 32 : 40 }}
        />
        <span
          className={`text-white text-sm font-semibold tracking-wide transition-[max-width,max-height,opacity] duration-300 [transition-timing-function:var(--ease-base)] overflow-hidden whitespace-nowrap ${
            collapsed ? 'max-w-0 max-h-0 opacity-0' : 'max-w-[120px] max-h-6 opacity-100'
          }`}
        >
          SkillNet
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 mt-6 flex flex-col gap-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={closeMobile}
            className={({ isActive }) =>
              `relative flex items-center h-10 text-sm font-medium overflow-hidden transition-colors duration-200 ${
                collapsed
                  ? 'mx-2 px-0 justify-center rounded-lg'
                  : 'ml-10 pl-4 pr-4 rounded-l-xl'
              } ${
                isActive
                  ? 'text-primary'
                  : 'text-white/80 hover:text-white'
              }`
            }
            title={collapsed ? item.label : undefined}
          >
            {({ isActive }) => (
              <>
                {isActive && <NavPill layoutId={pillId} collapsed={collapsed} />}
                <span className="relative z-10 shrink-0">{item.icon}</span>
                <span
                  className={`relative z-10 transition-[max-width,opacity,margin] duration-300 [transition-timing-function:var(--ease-base)] overflow-hidden whitespace-nowrap ${
                    collapsed ? 'max-w-0 opacity-0 ml-0' : 'max-w-[160px] opacity-100 ml-3'
                  }`}
                >
                  {item.label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Help card — only when expanded */}
      {!collapsed && (
        <NavLink
          to="/empleado/chat"
          onClick={closeMobile}
          className="mx-4 mb-5 p-5 rounded-2xl block group bg-[#162844] hover:bg-[#1C3254] transition-colors relative overflow-hidden"
        >
          <SpiderIcon />
          <p className="text-white/90 text-sm font-semibold mb-1.5 relative">{intl.formatMessage({ id: 'nav.help.title' })}</p>
          <p className="text-white/45 text-xs leading-relaxed mb-4 relative">{intl.formatMessage({ id: 'nav.help.description' })}</p>
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-white/70 group-hover:text-white transition-colors relative">
            {intl.formatMessage({ id: 'nav.help.action' })}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5"><polyline points="9 18 15 12 9 6"/></svg>
          </span>
        </NavLink>
      )}
    </>
  )
}

export function Sidebar() {
  const { collapsed, mobileOpen, closeMobile } = useSidebar()
  const reducedMotion = useReducedMotion()

  // Drag position drives backdrop opacity: fully open = 1, dragged away = dimmer
  const dragX = useMotionValue(0)
  const backdropOpacity = useTransform(dragX, [-248, 0], [0, 1])

  const handleDragEnd = useCallback(
    (_: unknown, info: PanInfo) => {
      // Dismiss if swiped fast enough OR dragged far enough to the left
      if (info.velocity.x < -100 || info.offset.x < -100) {
        closeMobile()
      }
    },
    [closeMobile],
  )

  return (
    <>
      {/* Desktop / Tablet sidebar */}
      <aside
        className={`group/sidebar fixed left-0 top-0 bottom-0 frame-surface flex-col z-20 transition-[width] duration-300 [transition-timing-function:var(--ease-base)] hidden md:flex ${
          collapsed ? 'w-16' : 'w-[248px]'
        }`}
      >
        <SidebarContent collapsed={collapsed} pillId="employee-nav-pill" />
      </aside>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            {/* Backdrop — frosted glass, not heavy black */}
            <motion.div
              {...backdrop}
              style={{ opacity: backdropOpacity }}
              className="fixed inset-0 bg-black/10 backdrop-blur-sm z-30 md:hidden"
              onClick={closeMobile}
            />
            {/* Slide-in sidebar — spring physics + swipe to dismiss */}
            <motion.aside
              {...sidebarSlide}
              style={{ x: dragX }}
              drag={reducedMotion ? false : 'x'}
              dragConstraints={{ left: -248, right: 0 }}
              dragElastic={0.1}
              dragSnapToOrigin
              onDragEnd={handleDragEnd}
              className="fixed left-0 top-0 bottom-0 w-[248px] frame-surface flex flex-col z-40 md:hidden touch-none"
            >
              <SidebarContent collapsed={false} pillId="employee-nav-pill-mobile" />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
