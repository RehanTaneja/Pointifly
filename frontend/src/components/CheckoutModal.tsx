import { useEffect, useState } from 'react'
import { fmtPts, fmtUsd, getVisaStatus, payWithVisa, type Allocation, type CheckoutResult } from '../api'

// Pays a cash leg through the Cybersource Sandbox (Visa's payment gateway): a test transaction
// with Cybersource's test Visa card, so no money moves. The demo always completes: if the
// sandbox gateway fails, the confirmation still shows, but gateway ids are only ever shown
// for a real authorization (never invented), and only outside presentation mode.
type Props = {
  allocation: Allocation
  holdingNames: Record<string, string>
  onClose: () => void
  onPaid: (r: CheckoutResult | null) => void
}

const MIN_PROCESSING_MS = 1400 // same pacing whether the gateway is fast, slow or down

export function CheckoutModal({ allocation, holdingNames, onClose, onPaid }: Props) {
  const card = allocation.payment_card
  const [presentation, setPresentation] = useState(false)
  const [stage, setStage] = useState<'review' | 'processing' | 'done'>('review')
  const [result, setResult] = useState<CheckoutResult | null>(null)

  useEffect(() => {
    getVisaStatus()
      .then((s) => setPresentation(s.presentation))
      .catch(() => setPresentation(false))
  }, [])

  const pay = async () => {
    if (!card) return
    setStage('processing')
    const started = Date.now()
    const r = await payWithVisa(allocation.trip_id, allocation.cash_usd, card.id).catch(() => null)
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, MIN_PROCESSING_MS - (Date.now() - started))))
    setResult(r)
    setStage('done')
    onPaid(r)
  }

  return (
    <div className="modal-backdrop" onClick={stage === 'processing' ? undefined : onClose}>
      <div className="modal checkout" onClick={(e) => e.stopPropagation()}>
        {stage === 'done' ? (
          <Success allocation={allocation} holdingNames={holdingNames} result={result} presentation={presentation} onClose={onClose} />
        ) : (
          <>
            <h3>Checkout · {allocation.trip_label}</h3>
            <div className="row between checkout-line">
              <span>Flight (cash fare)</span>
              <strong>{fmtUsd(allocation.cash_usd)}</strong>
            </div>
            {card ? (
              <>
                <div className="visa-card">
                  <span className="visa-mark">VISA</span>
                  <span>
                    {card.name}
                    {card.tier && <span className="small"> · {card.tier}</span>}
                  </span>
                </div>
                <p className="small">
                  Earns <strong>{fmtPts(card.earned_points)}</strong> {holdingNames[card.holding]} ({card.rate}x on this
                  fare)
                </p>
              </>
            ) : (
              <p className="small muted">No Visa card linked: connect a Visa card to pay cash legs.</p>
            )}
            <p className="muted small">Secured by Cybersource · test transaction, no money moves</p>
            <div className="row end">
              <button onClick={onClose} disabled={stage === 'processing'}>
                Cancel
              </button>
              <button className="primary pay-button" onClick={pay} disabled={stage === 'processing' || !card}>
                {stage === 'processing' ? (
                  <>
                    <span className="button-spinner" /> Processing…
                  </>
                ) : (
                  `Pay ${fmtUsd(allocation.cash_usd)}`
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Success(props: {
  allocation: Allocation
  holdingNames: Record<string, string>
  result: CheckoutResult | null
  presentation: boolean
  onClose: () => void
}) {
  const { allocation, holdingNames, result, presentation, onClose } = props
  const card = allocation.payment_card!
  return (
    <div className="success">
      <svg className="checkmark" viewBox="0 0 52 52" aria-hidden="true">
        <circle className="checkmark-circle" cx="26" cy="26" r="24" />
        <path className="checkmark-check" d="M15 27 l7 7 l15 -15" />
      </svg>
      <h3>Payment complete</h3>
      <div className="success-amount">{fmtUsd(allocation.cash_usd)}</div>
      <p className="small">
        {allocation.trip_label} · paid with {card.name}
      </p>
      <p className="small earned">
        +{fmtPts(card.earned_points)} {holdingNames[card.holding]}
      </p>
      <p className="muted small">Secured by Cybersource · test transaction, no money moves</p>
      {!presentation && (
        <p className="muted small dev-note">
          {result?.authorized
            ? `Gateway: authorized · approval ${result.approval_code ?? '—'} · transaction ${result.id ?? '—'}`
            : `Gateway: ${result ? `${result.status}${result.message ? ` (${result.message})` : ''}` : 'unreachable'} · demo fallback`}
        </p>
      )}
      <button className="primary" onClick={onClose}>
        Done
      </button>
    </div>
  )
}
