const INK = '#10192B'
const PAPER = '#F8F6F1'
const TEAL = '#0E7C74'
const TEAL_BRIGHT = '#149E92'

export default function Logo({ onDark = false, className = '' }) {
  const wordmarkColor = onDark ? PAPER : INK
  const markAccent = onDark ? TEAL_BRIGHT : TEAL

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <circle cx="12" cy="14" r="9" fill={markAccent} opacity="0.9" />
        <circle
          cx="18"
          cy="11"
          r="6.5"
          fill="none"
          stroke={markAccent}
          strokeWidth="1.75"
        />
      </svg>
      <span
        className="font-display text-lg leading-none"
        style={{ color: wordmarkColor }}
      >
        ConnectSphere
      </span>
    </div>
  )
}
