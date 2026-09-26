import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { fmtUsd, getAgentStatus, PAYMENTS_CHANGED, setMandate, type AgentStatus, type PayResult } from '../api'

// The user's mandate for the agent: autopay on/off and spending limits, enforced by the server,
// plus the audit log of every payment attempt (paid or blocked, and why).
export function AgentPayments({ planId, onPaidChange }: { planId: string; onPaidChange: (ids: string[]) => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [limits, setLimits] = useState({ per: 1000, total: 2500 })
  const [toast, setToast] = useState<PayResult | null>(null)

  const refresh = useCallback(() => {
    getAgentStatus(planId)
      .then((s) => {
        setStatus(s)
        setLimits({ per: s.max_per_payment, total: s.max_total })
        onPaidChange(s.paid)
      })
      .catch(() => undefined)
  }, [planId, onPaidChange])

  useEffect(() => {
    refresh()
    const onChange = (e: Event) => {
      refresh()
      const r = (e as CustomEvent<PayResult>).detail
      if (r?.decision === 'paid') {
        setToast(r)
        setTimeout(() => setToast(null), 4500)
      }
    }
    window.addEventListener(PAYMENTS_CHANGED, onChange)
    return () => window.removeEventListener(PAYMENTS_CHANGED, onChange)
  }, [refresh])

  const save = (autopay: boolean, per = limits.per, total = limits.total) =>
    setMandate(planId, autopay, per, total).then(setStatus).catch(() => undefined)

  if (!status) return null
  const legs = Object.keys(status.cash_legs).length
  return (
    <section className="card">
      <div className="row between">
        <h2>Agent payments</h2>
        <label className="switch small">
          <input type="checkbox" checked={status.autopay} onChange={(e) => save(e.target.checked)} />
          <span>Let Pointifly pay cash trips for me</span>
        </label>
      </div>
      <p className="muted small">
        {status.autopay
          ? `Ask Pointifly to book and it pays the plan's ${legs} cash trip${legs === 1 ? '' : 's'} with Visa, within your limits.`
          : 'Autopay is off: Pointifly can plan and explain, but only you can pay.'}{' '}
        The amount and card always come from the plan; limits are enforced by the server.
      </p>
      <div className="row limits">
        <label className="small">
          Max per payment
          <input type="number" min={1} max={20000} value={limits.per} onChange={(e) => setLimits({ ...limits, per: Number(e.target.value) })} />
        </label>
        <label className="small">
          Max total
          <input type="number" min={1} max={50000} value={limits.total} onChange={(e) => setLimits({ ...limits, total: Number(e.target.value) })} />
        </label>
        <button onClick={() => save(status.autopay)} disabled={limits.per === status.max_per_payment && limits.total === status.max_total}>
          Save limits
        </button>
      </div>
      <div className="meter small">
        <div className="row between">
          <span className="muted">Paid so far</span>
          <span>
            {fmtUsd(status.spent)} <span className="muted">of {fmtUsd(status.max_total)}</span>
          </span>
        </div>
        <div className="meter-track">
          <div className="meter-fill" style={{ width: `${Math.min(100, (status.spent / status.max_total) * 100)}%` }} />
        </div>
      </div>
      {status.audit.length > 0 && (
        <ul className="audit small">
          {[...status.audit].reverse().map((a, i) => (
            <li key={i} className={a.decision}>
              <span className="muted">{a.time}</span> <strong className="decision">{a.decision}</strong>
              {a.trip_id && ` · ${status.cash_legs[a.trip_id]?.label ?? a.trip_id}`} · {a.reason}
            </li>
          ))}
        </ul>
      )}
      {toast && createPortal(
        <div className="toast" role="status">
          <svg className="checkmark small-check" viewBox="0 0 52 52" aria-hidden="true">
            <circle className="checkmark-circle" cx="26" cy="26" r="24" />
            <path className="checkmark-check" d="M15 27 l7 7 l15 -15" />
          </svg>
          <div>
            <strong>Pointifly paid {status.cash_legs[toast.trip_id ?? '']?.label}</strong>
            <div className="small">
              {fmtUsd(toast.amount ?? 0)} with {toast.card} · +{(toast.earned_points ?? 0).toLocaleString()} points
            </div>
          </div>
        </div>,
        document.body,
      )}
    </section>
  )
}
