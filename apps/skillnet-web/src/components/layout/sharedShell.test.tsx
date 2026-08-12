import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('shared application shell', () => {
  it('uses the same shell for employee and admin routes', () => {
    const employee = readFileSync(resolve(__dirname, 'AppLayout.tsx'), 'utf8')
    const admin = readFileSync(resolve(__dirname, 'AdminLayout.tsx'), 'utf8')

    expect(employee).toContain('<AppShell role="employee" />')
    expect(admin).toContain('<AppShell role="admin" />')
    expect(existsSync(resolve(__dirname, 'AdminSidebar.tsx'))).toBe(false)
  })

  it('keeps role differences declarative inside the shared sidebar', () => {
    const sidebar = readFileSync(resolve(__dirname, 'Sidebar.tsx'), 'utf8')

    expect(sidebar).toContain("export type SidebarRole = 'employee' | 'admin'")
    expect(sidebar).toContain("to: '/admin/talento'")
    expect(sidebar).toContain("to: '/empleado/cursos'")
    expect(sidebar).toContain('role === \'employee\' && !collapsed')
  })

  it('shares the chat screen while keeping role-specific endpoints', () => {
    const employee = readFileSync(resolve(__dirname, '../../pages/employee/Chat.tsx'), 'utf8')
    const admin = readFileSync(resolve(__dirname, '../../pages/admin/Chat.tsx'), 'utf8')

    expect(employee).toContain('<ChatPage')
    expect(admin).toContain('<ChatPage')
    expect(employee).toContain('endpoint="/chat"')
    expect(admin).toContain('endpoint="/chat/admin"')
  })
})
