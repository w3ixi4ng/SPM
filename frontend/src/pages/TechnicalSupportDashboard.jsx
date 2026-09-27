import { CheckCircle2, LogOut, Package, PackagePlus, Plus, Wrench } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import useAuth from '../auth/useAuth.js'
import Logo from '../components/Logo.jsx'
import { getRoleAccess } from '../lib/access.js'
import { equipmentErrorMessage, listEquipment } from '../lib/equipment.js'

const C = {
  ink: '#10192B',
  inkFaint: '#4C5A70',
  paper: '#F8F6F1',
  paperDim: '#F0EDE5',
  line: '#E3DFD3',
  teal: '#0E7C74',
  sky: '#3C6E96',
  green: '#3F8F5F',
}

const UPCOMING_AREAS = [
  {
    icon: Package,
    title: 'Equipment requests',
    description: 'Review and fulfil equipment requested for an event.',
  },
  {
    icon: Wrench,
    title: 'On-site technical tickets',
    description: 'Track setup issues reported during an event.',
  },
  {
    icon: CheckCircle2,
    title: 'Setup confirmations',
    description: 'Confirm AV and equipment are working before doors open.',
  },
]

export default function TechnicalSupportDashboard({ role }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, signOut } = useAuth()
  const access = getRoleAccess(role)
  const [catalogue, setCatalogue] = useState({ status: 'loading', items: [], error: null })
  const [notice, setNotice] = useState(location.state?.notice ?? null)

  const loadCatalogue = useCallback(async () => {
    try {
      const items = await listEquipment()
      setCatalogue({ status: 'ready', items, error: null })
    } catch (error) {
      setCatalogue({ status: 'error', items: [], error: equipmentErrorMessage(error) })
    }
  }, [])

  // Loading remote catalogue data is exactly the external synchronization
  // this effect owns; the state updates happen only after that request settles.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void loadCatalogue() }, [loadCatalogue])

  function retryCatalogue() {
    setCatalogue((current) => ({ ...current, status: 'loading', error: null }))
    void loadCatalogue()
  }

  useEffect(() => {
    if (location.state?.notice) navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  useEffect(() => {
    if (!notice) return undefined
    const timer = setTimeout(() => setNotice(null), 4000)
    return () => clearTimeout(timer)
  }, [notice])

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen px-6 py-10 md:py-14" style={{ backgroundColor: C.paper }}>
      <style>{`
        @keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
        .rise-in { animation: riseIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .rise-in { animation: none; }
        }

        .csp-signout-btn {
          border-color: ${C.ink};
          color: ${C.ink};
          transition: background-color 0.2s, color 0.2s;
        }
        .csp-signout-btn:hover { background-color: ${C.ink}; color: ${C.paper}; }
        .csp-signout-btn:focus-visible {
          outline: 2px solid ${C.teal};
          outline-offset: 2px;
        }
      `}</style>
      <div className="rise-in w-full max-w-5xl mx-auto">
        <header className="flex items-center justify-between gap-6 mb-14">
          <Logo />
          <button
            type="button"
            onClick={handleSignOut}
            className="csp-signout-btn inline-flex items-center gap-2 px-4 py-2 rounded-sm font-ui text-sm border"
          >
            <LogOut size={15} aria-hidden="true" />
            Sign out
          </button>
        </header>

        <div className="max-w-2xl mb-10">
          <div
            className="inline-flex items-center gap-2 text-xs font-ui px-3 py-1 rounded-sm mb-5"
            style={{ backgroundColor: 'rgba(63,143,95,0.12)', color: C.green }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: C.green }} />
            Signed in as {access.label}
          </div>
          <h1 className="font-display text-4xl sm:text-5xl mb-4" style={{ color: C.ink }}>
            Technical support workspace
          </h1>
          <p className="font-ui text-base leading-relaxed" style={{ color: C.inkFaint }}>
            {access.description}
          </p>
          <p className="font-ui text-xs mt-3" style={{ color: C.inkFaint }}>
            {user.name} · {user.email}
          </p>
        </div>

        <section className="border rounded-sm p-7 sm:p-8 max-w-3xl mb-10" style={{ borderColor: C.line }} aria-labelledby="equipment-heading">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-2">
              <PackagePlus size={18} aria-hidden="true" style={{ color: C.teal }} />
              <h2 id="equipment-heading" className="font-display text-2xl" style={{ color: C.ink }}>Equipment catalogue</h2>
            </div>
            <Link to="/equipment/new" className="inline-flex items-center gap-2 px-4 py-2 rounded-sm font-ui text-sm font-medium" style={{ backgroundColor: C.teal, color: C.paper }}>
              <Plus size={15} aria-hidden="true" />
              Add equipment
            </Link>
          </div>
          {notice && <p role="status" className="font-ui text-sm mb-4" style={{ color: C.green }}>{notice}</p>}
          {catalogue.status === 'loading' && <p className="font-ui text-sm" style={{ color: C.inkFaint }}>Loading equipment…</p>}
          {catalogue.status === 'error' && (
            <div className="font-ui text-sm" style={{ color: C.inkFaint }}>
              <p role="alert">{catalogue.error}</p>
              <button type="button" onClick={retryCatalogue} className="underline mt-1" style={{ color: C.teal }}>Try again</button>
            </div>
          )}
          {catalogue.status === 'ready' && catalogue.items.length === 0 && (
            <p className="font-ui text-sm" style={{ color: C.inkFaint }}>No equipment has been added yet.</p>
          )}
          {catalogue.status === 'ready' && catalogue.items.length > 0 && (
            <ul className="divide-y" aria-label="Equipment catalogue" style={{ borderColor: C.line }}>
              {catalogue.items.map((item) => (
                <li key={item.id} className="py-4 first:pt-0 last:pb-0 flex items-start gap-4">
                  <Package size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{item.type}</h3>
                      <span className="font-ui text-sm" style={{ color: C.inkFaint }}>{item.total_quantity} total</span>
                    </div>
                    {item.description && <p className="font-ui text-sm mt-1" style={{ color: C.inkFaint }}>{item.description}</p>}
                    <p className="font-ui text-xs mt-2" style={{ color: C.green }}>Available · Active</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border rounded-sm p-7 sm:p-8 max-w-3xl" style={{ borderColor: C.line }}>
          <div className="flex items-center gap-2 mb-3">
            <Wrench size={16} aria-hidden="true" style={{ color: C.teal }} />
            <p className="font-ui text-xs uppercase tracking-widest" style={{ color: C.teal }}>
              Coming to this workspace
            </p>
          </div>
          <h2 className="font-display text-2xl mb-6" style={{ color: C.ink }}>
            Support tools, on the way
          </h2>
          <ul className="divide-y" style={{ borderColor: C.line }}>
            {UPCOMING_AREAS.map(({ icon: Icon, title, description }) => (
              <li key={title} className="py-4 first:pt-0 last:pb-0 flex items-start gap-4">
                <Icon size={20} aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: C.sky }} />
                <div className="min-w-0 flex-1">
                  <h3 className="font-ui text-base font-medium" style={{ color: C.ink }}>{title}</h3>
                  <p className="font-ui text-sm mt-0.5" style={{ color: C.inkFaint }}>{description}</p>
                </div>
                <span
                  className="inline-flex items-center gap-1.5 font-ui text-xs shrink-0 mt-1"
                  style={{ color: C.inkFaint }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full border"
                    style={{ borderColor: C.inkFaint }}
                    aria-hidden="true"
                  />
                  Not started
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
