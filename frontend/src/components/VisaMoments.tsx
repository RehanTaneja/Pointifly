import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { VISA_MOMENT, type VisaMoment } from '../visaMoments'
import { VisaMark } from './VisaImpact'

const DONE_TTL = 5200
const WORKING_MAX = 20000 // a "working" label never outlives a stuck call

type Shown = VisaMoment & { key: number; leaving?: boolean }

// The stack of Visa moments at the top of the screen, in Visa blue and gold.
export function VisaMoments() {
  const [moments, setMoments] = useState<Shown[]>([])

  useEffect(() => {
    let key = 0
    const timers = new Map<string, number>()
    const remove = (id: string) => {
      setMoments((all) => all.map((m) => (m.id === id ? { ...m, leaving: true } : m)))
      window.setTimeout(() => setMoments((all) => all.filter((m) => m.id !== id || !m.leaving)), 450)
    }
    const onMoment = (e: Event) => {
      const m = (e as CustomEvent<VisaMoment>).detail
      clearTimeout(timers.get(m.id))
      setMoments((all) => {
        const next = { ...m, key: ++key }
        const i = all.findIndex((x) => x.id === m.id)
        return i >= 0 ? all.map((x, j) => (j === i ? { ...next, key: x.key } : x)) : [...all.slice(-3), next]
      })
      timers.set(m.id, window.setTimeout(() => remove(m.id), m.kind === 'working' ? WORKING_MAX : (m.ttl ?? DONE_TTL)))
    }
    window.addEventListener(VISA_MOMENT, onMoment)
    return () => {
      window.removeEventListener(VISA_MOMENT, onMoment)
      timers.forEach((t) => clearTimeout(t))
    }
  }, [])

  if (!moments.length) return null
  return createPortal(
    <div className="visa-moments" aria-live="polite">
      {moments.map((m) => (
        <div key={m.key} className={`visa-moment ${m.kind} ${m.leaving ? 'leaving' : ''}`} role="status">
          <MomentIcon kind={m.kind} />
          <div className="visa-moment-text">
            <div className="visa-moment-title">
              <VisaMark /> {m.title}
            </div>
            {m.detail && <div className="visa-moment-detail">{m.detail}</div>}
          </div>
        </div>
      ))}
    </div>,
    document.body,
  )
}

function MomentIcon({ kind }: { kind: VisaMoment['kind'] }) {
  if (kind === 'working') return <span className="visa-spinner" aria-hidden="true" />
  return (
    <svg className={`visa-check ${kind}`} viewBox="0 0 52 52" aria-hidden="true">
      <circle className="visa-check-circle" cx="26" cy="26" r="24" />
      {kind === 'done' ? <path className="visa-check-mark" d="M15 27 l7 7 l15 -15" /> : <path className="visa-check-mark" d="M26 14 v15 M26 37 v1" />}
    </svg>
  )
}
