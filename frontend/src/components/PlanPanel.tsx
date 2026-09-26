import { useCallback, useEffect, useState } from 'react'
import { cabinLabel, fmtPts, fmtUsd, getAgentStatus, PAYMENTS_CHANGED, type Allocation, type OptimizeResponse } from '../api'
import { CheckoutModal } from './CheckoutModal'
import { CountUp } from './CountUp'

// The plan on the agent page, once the agent has optimized: headline numbers, one line per trip,
// and each cash trip's state. With autonomous payments off, the user pays with the button here.
type Props = {
  result: OptimizeResponse
  holdingNames: Record<string, string>
  autopay: boolean
  onDetails: () => void
}

export function PlanPanel({ result, holdingNames, autopay, onDetails }: Props) {
  const [paid, setPaid] = useState<Set<string>>(new Set())
  const [checkout, setCheckout] = useState<Allocation | null>(null)
  const [limit, setLimit] = useState<number | null>(null) // the server's per-payment limit for the agent
  const planId = result.plan_id
  const p = result.portfolio

  const refresh = useCallback(() => {
    if (planId)
      getAgentStatus(planId)
        .then((s) => {
          setPaid(new Set(s.paid))
          setLimit(s.max_per_payment)
        })
        .catch(() => undefined)
  }, [planId])
  useEffect(() => {
    refresh()
    window.addEventListener(PAYMENTS_CHANGED, refresh)
    return () => window.removeEventListener(PAYMENTS_CHANGED, refresh)
  }, [refresh])

  return (
    <section className="card plan-panel">
      <div className="plan-head">
        <div>
          <div className="stat">
            <CountUp value={p.total_points} format={fmtPts} />
          </div>
          <div className="muted small">points used</div>
        </div>
        <div>
          <div className="stat">
            <CountUp value={p.total_value_usd} format={fmtUsd} />
          </div>
          <div className="muted small">travel value</div>
        </div>
        <div>
          {result.value_gained_usd > 0 ? (
            <>
              <div className="stat gain">
                +<CountUp value={result.value_gained_usd} format={fmtUsd} />
              </div>
              <div className="muted small">more value than trip-by-trip</div>
            </>
          ) : (
            <>
              <div className="stat">Same</div>
              <div className="muted small">as trip-by-trip here</div>
            </>
          )}
        </div>
      </div>
      <ul className="plan-trips">
        {p.allocations.map((a) => (
          <li key={a.trip_id}>
            <div>
              <strong>{a.trip_label}</strong>
              <div className="muted small">
                {a.method === 'cash'
                  ? `Cash ${fmtUsd(a.cash_usd)}${a.payment_card ? ` · ${a.payment_card.name} (Visa) · +${fmtPts(a.payment_card.earned_points)} pts` : ''}`
                  : `${fmtPts(a.award_points)} ${holdingNames[a.program!]} · ${cabinLabel(a.cabin)}`}
              </div>
            </div>
            {a.method === 'cash' &&
              (paid.has(a.trip_id) ? (
                <span className="tag ok pop">✓ Paid</span>
              ) : autopay && (limit === null || a.cash_usd <= limit) ? (
                <span className="tag">Pointifly pays on your OK</span>
              ) : (
                // Autonomous payments off, or above the agent's per-payment limit: the user pays.
                <button className="primary" disabled={!a.payment_card} onClick={() => setCheckout(a)}>
                  Pay with Visa
                </button>
              ))}
            {a.method === 'points' && a.cents_per_point !== null && <span className="tag">{a.cents_per_point.toFixed(1)}¢/pt</span>}
          </li>
        ))}
      </ul>
      <div className="row end">
        <button className="link" onClick={onDetails}>
          See full breakdown<span className="arrow">→</span>
        </button>
      </div>
      {checkout && (
        <CheckoutModal
          allocation={checkout}
          holdingNames={holdingNames}
          planId={planId}
          onClose={() => setCheckout(null)}
          onPaid={() => window.dispatchEvent(new Event(PAYMENTS_CHANGED))}
        />
      )}
    </section>
  )
}
