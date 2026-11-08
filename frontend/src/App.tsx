import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import type { UserRole } from './api'
import { AuthProvider } from './auth/AuthContext'
import { useAuth } from './auth/useAuth'
import { ResidentShell } from './components/ResidentShell'
import { Button, Card } from './components/ui'
import { BillsPage } from './pages/BillsPage'
import { ComplaintsPage } from './pages/ComplaintsPage'
import { LoginPage } from './pages/LoginPage'
import { ResidentHomePage } from './pages/ResidentHomePage'

const roleHomes: Record<UserRole, string> = {
  resident: '/home',
  helpdesk: '/helpdesk',
  accounts: '/accounts',
  committee: '/committee',
}

function RoleHome() {
  const { role } = useAuth()
  return <Navigate to={role ? roleHomes[role] : '/login'} replace />
}

function ResidentOnly() {
  const { role } = useAuth()
  if (!role) return <Navigate to="/login" replace />
  if (role !== 'resident') return <Navigate to={roleHomes[role]} replace />
  return <Outlet />
}

function StaffOnly({ requiredRole }: { requiredRole: Exclude<UserRole, 'resident'> }) {
  const { role } = useAuth()
  if (!role) return <Navigate to="/login" replace />
  if (role !== requiredRole) return <Navigate to={roleHomes[role]} replace />
  return <StaffHome role={requiredRole} />
}

function StaffHome({ role }: { role: Exclude<UserRole, 'resident'> }) {
  const { signOut } = useAuth()
  const titles = { helpdesk: 'Help desk', accounts: 'Accounts', committee: 'Committee' }
  return (
    <main className="staff-page">
      <div className="brand"><span className="brand__mark">T</span><span>Township</span></div>
      <Card className="staff-card">
        <p className="eyebrow">STAFF WORKSPACE</p>
        <h1>{titles[role]}</h1>
        <p className="muted-copy">You’re signed in with {role} access. This experience currently includes resident services.</p>
        <Button variant="secondary" onClick={() => { signOut(); window.location.assign('/login') }}>Sign out</Button>
      </Card>
    </main>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RoleHome />} />
      <Route element={<ResidentOnly />}>
        <Route element={<ResidentShell />}>
          <Route path="/home" element={<ResidentHomePage />} />
          <Route path="/bills" element={<BillsPage />} />
          <Route path="/complaints" element={<ComplaintsPage />} />
        </Route>
      </Route>
      <Route path="/helpdesk" element={<StaffOnly requiredRole="helpdesk" />} />
      <Route path="/accounts" element={<StaffOnly requiredRole="accounts" />} />
      <Route path="/committee" element={<StaffOnly requiredRole="committee" />} />
      <Route path="*" element={<RoleHome />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
