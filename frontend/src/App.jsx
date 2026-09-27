import { Navigate, Route, Routes } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider.jsx'
import ProtectedRoute, { DashboardRedirect } from './components/ProtectedRoute.jsx'
import { PERMISSIONS, ROLE_ACCESS } from './lib/access.js'
import Dashboard from './pages/Dashboard.jsx'
import EventCoordinatorDashboard from './pages/EventCoordinatorDashboard.jsx'
import EventCoordinatorEventDetail from './pages/EventCoordinatorEventDetail.jsx'
import EventRequestForm from './pages/EventRequestForm.jsx'
import EquipmentForm from './pages/EquipmentForm.jsx'
import ForgotPassword from './pages/ForgotPassword.jsx'
import Login from './pages/Login.jsx'
import SignUp from './pages/SignUp.jsx'
import TechnicalSupportDashboard from './pages/TechnicalSupportDashboard.jsx'
import VenueForm from './pages/VenueForm.jsx'
import VenueRequestForm from './pages/VenueRequestForm.jsx'
import VenueStaffDashboard from './pages/VenueStaffDashboard.jsx'

// Each role's landing page. event_organiser and attendee still share the
// generic Dashboard component (no distinct page has been asked for yet);
// the other three roles get their own page now that their placeholder
// dashboards needed to stop looking identical to each other.
const ROLE_DASHBOARDS = {
  event_organiser: Dashboard,
  event_coordinator: EventCoordinatorDashboard,
  venue_staff: VenueStaffDashboard,
  technical_support: TechnicalSupportDashboard,
  attendee: Dashboard,
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/dashboard" element={<DashboardRedirect />} />
        {Object.entries(ROLE_ACCESS).map(([role, access]) => {
          const RoleDashboard = ROLE_DASHBOARDS[role]
          return (
            <Route
              key={role}
              path={access.dashboardPath}
              element={(
                <ProtectedRoute expectedRole={role}>
                  <RoleDashboard role={role} />
                </ProtectedRoute>
              )}
            />
          )
        })}
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
        <Route
          path="/venues/new"
          element={(
            <ProtectedRoute permission={PERMISSIONS.CREATE_VENUE}>
              <VenueForm />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/equipment/new"
          element={(
            <ProtectedRoute permission={PERMISSIONS.CREATE_EQUIPMENT}>
              <EquipmentForm />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/coordinator/events/:id"
          element={(
            <ProtectedRoute permission={PERMISSIONS.VIEW_ASSIGNED_EVENTS}>
              <EventCoordinatorEventDetail />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/coordinator/events/:id/request-venue"
          element={(
            <ProtectedRoute permission={PERMISSIONS.REQUEST_VENUE_BOOKING}>
              <VenueRequestForm />
            </ProtectedRoute>
          )}
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}

export default App
