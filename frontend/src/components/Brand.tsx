import { useEffect, useState } from 'react'

type GlyphProps = { className?: string; dot?: boolean; width?: number; height?: number }

// The Pointifly mark: an airliner seen from above forms the "i" of POINT·I·FLY, with its dot above.
export function PlaneGlyph({ className, dot = true, width, height }: GlyphProps) {
  return (
    <svg className={className} width={width} height={height} viewBox={dot ? '0 0 32 56' : '0 10 32 43'} aria-hidden="true" fill="currentColor">
      {dot && <circle cx="16" cy="4.6" r="4" />}
      {/* fuselage */}
      <path d="M16 11c1.8 0 2.7 2 2.7 4.6V45c0 2.8-1.3 5.4-2.7 7-1.4-1.6-2.7-4.2-2.7-7V15.6c0-2.6.9-4.6 2.7-4.6z" />
      {/* wings */}
      <path d="M18.4 24 32 33.5v3.4l-13.6-4.3zM13.6 24 0 33.5v3.4l13.6-4.3z" />
      {/* tailplane */}
      <path d="M18.4 43.5l6.5 4.6v2.2l-6.5-1.6zM13.6 43.5l-6.5 4.6v2.2l6.5-1.6z" />
    </svg>
  )
}

export function Logo({ size = 'header' }: { size?: 'header' | 'hero' }) {
  return (
    <div className={`logo logo-${size}`}>
      <div className="wordmark" role="img" aria-label="Pointifly">
        <span>POINT</span>
        <PlaneGlyph className="logo-plane" />
        <span>FLY</span>
      </div>
      <div className="tagline">Turn points to places</div>
    </div>
  )
}

const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

// Opening splash: the logo on the world map, then a fade into the app. Click to skip.
export function Splash({ onDone }: { onDone: () => void }) {
  const [leaving, setLeaving] = useState(false)
  useEffect(() => {
    const hold = reduceMotion() ? 600 : 2100
    const t1 = setTimeout(() => setLeaving(true), hold)
    const t2 = setTimeout(onDone, hold + 650)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [onDone])
  return (
    <div className={`splash ${leaving ? 'leaving' : ''}`} onClick={() => {
        setLeaving(true)
        setTimeout(onDone, 650)
      }}>
      <Logo size="hero" />
    </div>
  )
}

// Optimizer loading state: a plane flying an arc between two points.
export function PlaneLoader({ label }: { label: string }) {
  return (
    <section className="card center loader">
      <svg viewBox="0 0 320 110" className="flight-arc" aria-hidden="true">
        <path id="arc" d="M20 92 Q160 -18 300 92" className="arc-path" />
        <circle cx="20" cy="92" r="4" className="arc-end" />
        <circle cx="300" cy="92" r="4" className="arc-end" />
        <g>
          {/* The glyph points up; rotate so it points along the path. */}
          <g transform="rotate(90) translate(-10 -13.5)">
            <PlaneGlyph dot={false} className="arc-plane" width={20} height={27} />
          </g>
          <animateMotion dur="2.2s" repeatCount="indefinite" rotate="auto" keyPoints="0;1" keyTimes="0;1" calcMode="spline" keySplines="0.45 0 0.55 1">
            <mpath href="#arc" />
          </animateMotion>
        </g>
      </svg>
      <p className="muted">{label}</p>
    </section>
  )
}
