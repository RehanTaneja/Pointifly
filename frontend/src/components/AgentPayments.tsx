import { useCallback, useEffect, useState } from 'react'
import { fmtUsd, getAgentStatus, PAYMENTS_CHANGED, setMandate, type AgentStatus } from '../api'
import { AGENT_CONTEXT } from './VoiceAgent'

// The user's mandate for the agent: autopay on/off and spending limits, enforced by the server,
// plus the audit log of every payment attempt (paid or blocked, and why).
type Props = {
  planId: string
  onPaidChange: (ids: string[]) => void
  onAutopayChange: (on: boolean) => void // the app-wide switch (also on the agent page)
}

export function AgentPayments({ planId, onPaidChange, onAutopayChange }: Props) {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [limits, setLimits] = useState({ per: 1000, total: 2500 })

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
    window.addEventListener(PAYMENTS_CHANGED, refresh)
    return () => window.removeEventListener(PAYMENTS_CHANGED, refresh)
  }, [refresh])

  // New limits apply on the server at once; the plan card and a live agent are told too.
  const saveLimits = () =>
    setMandate(planId, status!.autopay, limits.per, limits.total)
      .then((s) => {
        setStatus(s)
        window.dispatchEvent(new Event(PAYMENTS_CHANGED))
        window.dispatchEvent(
          new CustomEvent(AGENT_CONTEXT, {
            detail: `The user changed the spending limits to ${fmtUsd(s.max_per_payment)} per payment and ${fmtUsd(s.max_total)} total. Trips within the new limits can now be paid after one confirmation.`,
          }),
        )
      })
      .catch(() => undefined)

  if (!status) return null
  const legs = Object.keys(status.cash_legs).length
  return (
    <section className="card">
      <div className="row between">
        <h2>Agent payments</h2>
        <label className="switch small">
          <input type="checkbox" checked={status.autopay} onChange={(e) => onAutopayChange(e.target.checked)} />
          <span>Autonomous payments</span>
        </label>
      </div>
      <p className="muted small">
        {status.autopay
          ? `Pointifly asks once, then pays the plan's ${legs} cash trip${legs === 1 ? '' : 's'} with Visa, within your limits.`
          : 'Autonomous payments are off: Pointifly can plan and explain, but only you can pay.'}{' '}
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
        <button onClick={saveLimits} disabled={limits.per === status.max_per_payment && limits.total === status.max_total}>
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
    </section>
  )
}
