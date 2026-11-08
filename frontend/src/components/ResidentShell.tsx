import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Button, Icon } from './ui'

export function ResidentShell() {
  const { signOut } = useAuth()
  const navigate = useNavigate()

  function leave() {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink className="brand" to="/home" aria-label="Community home">
          <span className="brand__mark">T</span>
          <span>Township</span>
        </NavLink>
        <Button variant="quiet" className="signout-button" onClick={leave}>Sign out</Button>
      </header>
      <main className="main-content"><Outlet /></main>
      <nav className="bottom-nav" aria-label="Main navigation">
        <NavLink to="/home" className={({ isActive }) => `bottom-nav__link${isActive ? ' is-active' : ''}`}>
          <Icon name="home" /><span>Home</span>
        </NavLink>
        <NavLink to="/bills" className={({ isActive }) => `bottom-nav__link${isActive ? ' is-active' : ''}`}>
          <Icon name="bill" /><span>Bills</span>
        </NavLink>
        <NavLink to="/complaints" className={({ isActive }) => `bottom-nav__link${isActive ? ' is-active' : ''}`}>
          <Icon name="chat" /><span>Complaints</span>
        </NavLink>
      </nav>
    </div>
  )
}
