import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import type { UserRole } from '../api'
import { useAuth } from '../auth/useAuth'
import { Button } from './ui'

type StaffRole = Exclude<UserRole, 'resident'>

const labels: Record<StaffRole, string> = {
  helpdesk: 'Help desk',
  accounts: 'Accounts',
  committee: 'Committee',
}

const paths: Record<StaffRole, string> = {
  helpdesk: '/helpdesk',
  accounts: '/accounts',
  committee: '/committee',
}

export function StaffShell({ role, children }: { role: StaffRole; children: ReactNode }) {
  const { signOut } = useAuth()
  const navigate = useNavigate()

  function leave() {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="staff-app">
      <header className="topbar">
        <NavLink className="brand" to={paths[role]} aria-label={`${labels[role]} home`}>
          <span className="brand__mark">T</span><span>Township</span>
        </NavLink>
        <span className="staff-role-label">{labels[role]} workspace</span>
        <Button variant="quiet" className="signout-button" onClick={leave}>Sign out</Button>
      </header>
      <main className="staff-main">{children}</main>
    </div>
  )
}
