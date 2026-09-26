import { useState } from 'react'
import { fmtUsd, type Allocation } from '../api'

// UI-only mock of an in-app Visa checkout. No payment is processed and no card data is collected.
type Props = { allocation: Allocation; onClose: () => void; onPaid: () => void }

export function CheckoutModal({ allocation, onClose, onPaid }: Props) {
  const [processing, setProcessing] = useState(false)

  const pay = () => {
    setProcessing(true)
    setTimeout(onPaid, 1200)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Checkout · {allocation.trip_label}</h3>
        <p className="muted small">Demo checkout: no real payment is processed.</p>
        <div className="row between checkout-line">
          <span>Flight (cash fare)</span>
          <strong>{fmtUsd(allocation.cash_usd)}</strong>
        </div>
        <div className="visa-card">
          <span className="visa-mark">VISA</span>
          <span>Demo card</span>
        </div>
        <div className="row end">
          <button onClick={onClose} disabled={processing}>
            Cancel
          </button>
          <button className="primary" onClick={pay} disabled={processing}>
            {processing ? 'Processing…' : `Pay ${fmtUsd(allocation.cash_usd)}`}
          </button>
        </div>
      </div>
    </div>
  )
}
