import { useEffect, useState } from 'react'
import { fmtPts, fmtUsd, getVisaStatus, payWithVisa, type Allocation, type CheckoutResult } from '../api'

// Pays a cash leg through the Cybersource Sandbox (Visa's payment gateway). Test transaction:
// Cybersource's test Visa card stands in for the user's card and no money moves.
type Props = {
  allocation: Allocation
  holdingNames: Record<string, string>
  onClose: () => void
  onPaid: (r: CheckoutResult) => void
}

export function CheckoutModal({ allocation, holdingNames, onClose, onPaid }: Props) {
  const card = allocation.payment_card
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState<CheckoutResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getVisaStatus()
      .then((s) => setConfigured(s.checkout_configured))
      .catch(() => setConfigured(false))
  }, [])

  const pay = async () => {
    if (!card) return
    setProcessing(true)
    setError(null)
    try {
      const r = await payWithVisa(allocation.trip_id, allocation.cash_usd, card.id)
      setResult(r)
      if (r.status === 'AUTHORIZED' || r.status === 'AUTHORIZED_PENDING_REVIEW') onPaid(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setProcessing(false)
    }
  }

  const ok = result && (result.status === 'AUTHORIZED' || result.status === 'AUTHORIZED_PENDING_REVIEW')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Checkout · {allocation.trip_label}</h3>
        <p className="small">
          <span className="tag warn">Cybersource Sandbox</span> test transaction: a Cybersource test Visa card stands in
          for yours and no money moves.
        </p>
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
              {card.source_url && (
                <>
                  {' · '}
                  <a href={card.source_url} target="_blank" rel="noreferrer">
                    earn rate source ↗
                  </a>
                </>
              )}
            </p>
          </>
        ) : (
          <p className="small muted">No Visa card linked: connect a Visa card to pay cash legs.</p>
        )}

        {configured === false && <div className="banner error small">Cybersource keys aren't set on the server.</div>}
        {error && <div className="banner error small">{error}</div>}
        {result && (
          <div className={`banner small ${ok ? '' : 'error'}`}>
            {ok ? 'Authorized' : result.status}
            {result.approval_code && ` · approval ${result.approval_code}`}
            {result.id && ` · transaction ${result.id}`}
            {result.message && ` · ${result.message}`}
            {result.repeat && ' · already paid (no new charge)'}
            <div className="muted">
              {result.environment} · test card ···{result.test_card_last4}
              {result.trigger_range_warning && ' · amounts $7,001–$7,145 can return canned test responses'}
            </div>
          </div>
        )}

        <div className="row end">
          <button onClick={onClose} disabled={processing}>
            {ok ? 'Done' : 'Cancel'}
          </button>
          {!ok && (
            <button className="primary" onClick={pay} disabled={processing || !card || configured === false}>
              {processing ? 'Processing…' : `Pay ${fmtUsd(allocation.cash_usd)} with Visa`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
