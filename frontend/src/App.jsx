import { Navigate, Route, Routes } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import ProtectedRoute, { DashboardRedirect } from './components/ProtectedRoute.jsx'
import { PERMISSIONS, ROLE_ACCESS } from './lib/access.js'
import Dashboard from './pages/Dashboard.jsx'
import EventRequestForm from './pages/EventRequestForm.jsx'
import ForgotPassword from './pages/ForgotPassword.jsx'
import Login from './pages/Login.jsx'
import SignUp from './pages/SignUp.jsx'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/dashboard" element={<DashboardRedirect />} />
        {Object.entries(ROLE_ACCESS).map(([role, access]) => (
          <Route
            key={role}
            path={access.dashboardPath}
            element={(
              <ProtectedRoute expectedRole={role}>
                <Dashboard role={role} />
              </ProtectedRoute>
            )}
          />
        ))}
        <Route
          path="/events/new"
          element={(
            <ProtectedRoute permission={PERMISSIONS.CREATE_EVENT}>
              <EventRequestForm />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/events/:id"
          element={(
            <ProtectedRoute permission={PERMISSIONS.VIEW_OWN_EVENTS}>
              <EventRequestForm />
            </ProtectedRoute>
          )}
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
