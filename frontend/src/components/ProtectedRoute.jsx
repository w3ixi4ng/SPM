import { Navigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import { getRoleAccess, hasPermission } from '../lib/access.js'
import Logo from './Logo.jsx'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
}

function StatusScreen({ title, message, actionLabel, onAction }) {
  return (
    <main
      className="min-h-screen flex items-center justify-center px-6 py-16"
      style={{ backgroundColor: C.paper }}
    >
      <section
        className="w-full max-w-md border rounded-sm px-8 py-10 text-center"
        style={{ borderColor: C.line }}
      >
        <div className="flex justify-center mb-7"><Logo /></div>
        <h1 className="font-display text-3xl mb-3" style={{ color: C.ink }}>{title}</h1>
        <p className="font-ui text-sm leading-relaxed mb-7" style={{ color: C.inkFaint }}>
          {message}
        </p>
        {actionLabel && (
          <button
            type="button"
            onClick={onAction}
            className="px-5 py-3 rounded-sm font-ui font-medium text-sm text-white"
            style={{ backgroundColor: C.teal }}
          >
            {actionLabel}
          </button>
        )}
      </section>
    </main>
  )
}

function SessionBoundary({ children }) {
  const { status, refresh } = useAuth()

  if (status === 'loading') {
    return <StatusScreen title="Loading your workspace" message="Checking your secure session…" />
  }
  if (status === 'unauthenticated') return <Navigate to="/login" replace />
  if (status === 'error') {
    return (
      <StatusScreen
        title="Workspace unavailable"
        message="We couldn't verify your session. Check your connection and try again."
        actionLabel="Try again"
        onAction={() => refresh().catch(() => {})}
      />
    )
  }
  return children
}

function UnknownRole() {
  const { signOut } = useAuth()
  return (
    <StatusScreen
      title="Access not configured"
      message="Your account has no recognized role. Ask an administrator to check your account access."
      actionLabel="Sign out"
      onAction={() => signOut().catch(() => {})}
    />
  )
}

export function DashboardRedirect() {
  const { user } = useAuth()
  return (
    <SessionBoundary>
      {getRoleAccess(user?.role) ? (
        <Navigate to={getRoleAccess(user.role).dashboardPath} replace />
      ) : (
        <UnknownRole />
      )}
    </SessionBoundary>
  )
}

export default function ProtectedRoute({ children, expectedRole, permission }) {
  const { user } = useAuth()

  return (
    <SessionBoundary>
      {!getRoleAccess(user?.role) ? (
        <UnknownRole />
      ) : expectedRole && user.role !== expectedRole ? (
        <Navigate to={getRoleAccess(user.role).dashboardPath} replace />
      ) : permission && !hasPermission(user.role, permission) ? (
        <Navigate to={getRoleAccess(user.role).dashboardPath} replace />
      ) : (
        children
      )}
    </SessionBoundary>
  )
}
