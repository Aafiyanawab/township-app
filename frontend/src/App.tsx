import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import type { UserRole } from './api'
import { AuthProvider } from './auth/AuthContext'
import { useAuth } from './auth/useAuth'
import { ResidentShell } from './components/ResidentShell'
import { AccountsPage } from './pages/AccountsPage'
import { BillsPage } from './pages/BillsPage'
import { CommitteePage } from './pages/CommitteePage'
import { ComplaintsPage } from './pages/ComplaintsPage'
import { HelpdeskPage } from './pages/HelpdeskPage'
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

function StaffOnly({ requiredRole, children }: { requiredRole: Exclude<UserRole, 'resident'>; children: ReactNode }) {
  const { role } = useAuth()
  if (!role) return <Navigate to="/login" replace />
  if (role !== requiredRole) return <Navigate to={roleHomes[role]} replace />
  return children
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
      <Route path="/helpdesk" element={<StaffOnly requiredRole="helpdesk"><HelpdeskPage /></StaffOnly>} />
      <Route path="/accounts" element={<StaffOnly requiredRole="accounts"><AccountsPage /></StaffOnly>} />
      <Route path="/committee" element={<StaffOnly requiredRole="committee"><CommitteePage /></StaffOnly>} />
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
