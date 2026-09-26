import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { fmtUsd, PAYMENTS_CHANGED, type OptimizeResponse, type PayResult } from '../api'

// "Pointifly paid …" with the green check, whenever the agent completes a payment (any page).
export function PaymentToast({ result }: { result: OptimizeResponse | null }) {
  const [toast, setToast] = useState<PayResult | null>(null)
  useEffect(() => {
    let timer = 0
    const onChange = (e: Event) => {
      const r = (e as CustomEvent<PayResult>).detail
      if (r?.decision !== 'paid') return
      setToast(r)
      clearTimeout(timer)
      timer = window.setTimeout(() => setToast(null), 4500)
    }
    window.addEventListener(PAYMENTS_CHANGED, onChange)
    return () => {
      window.removeEventListener(PAYMENTS_CHANGED, onChange)
      clearTimeout(timer)
    }
  }, [])
  if (!toast) return null
  const label = result?.portfolio.allocations.find((a) => a.trip_id === toast.trip_id)?.trip_label ?? 'your trip'
  return createPortal(
    <div className="toast" role="status">
      <svg className="checkmark small-check" viewBox="0 0 52 52" aria-hidden="true">
        <circle className="checkmark-circle" cx="26" cy="26" r="24" />
        <path className="checkmark-check" d="M15 27 l7 7 l15 -15" />
      </svg>
      <div>
        <strong>Pointifly paid {label}</strong>
        <div className="small">
          {fmtUsd(toast.amount ?? 0)} with {toast.card} (Visa) · +{(toast.earned_points ?? 0).toLocaleString()} points
        </div>
      </div>
    </div>,
    document.body,
  )
}
