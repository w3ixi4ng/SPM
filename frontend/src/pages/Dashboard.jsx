import { Link } from 'react-router-dom'
import Logo from '../components/Logo.jsx'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  line: '#E3DFD3',
  teal: '#0E7C74',
  green: '#3F8F5F',
}

export default function Dashboard() {
  return (
    <div
      className="min-h-screen flex items-center justify-center px-6 py-16"
      style={{ backgroundColor: C.paper }}
    >
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }
      `}</style>
      <div
        className="rise-in w-full max-w-sm text-center border rounded-sm px-8 py-10"
        style={{ borderColor: C.line }}
      >
        <div className="flex justify-center mb-6">
          <Logo />
        </div>
        <div
          className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-6"
          style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: C.green }}
          />
          Signed in
        </div>
        <h1 className="font-display text-3xl mb-3" style={{ color: C.ink }}>
          Welcome to ConnectSphere
        </h1>
        <p
          className="font-ui text-sm leading-relaxed mb-8"
          style={{ color: C.inkFaint }}
        >
          This is a placeholder for the main dashboard. The real event
          workspace lands here next.
        </p>
        <Link
          to="/login"
          className="inline-block px-5 py-3 rounded-sm font-medium font-ui border transition-colors duration-200"
          style={{ borderColor: C.ink, color: C.ink }}
        >
          Log out
        </Link>
      </div>
    </div>
  )
}
