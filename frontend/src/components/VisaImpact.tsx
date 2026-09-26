import { fmtPts, fmtUsd, type OptimizeResponse } from '../api'

export function VisaMark() {
  return <span className="visa-chip">VISA</span>
}

// Shown on every page: which Visa services Pointifly runs on.
export function BuiltOnVisa() {
  return (
    <div className="built-on-visa" title="Visa services Pointifly uses">
      <VisaMark />
      <span>Cybersource payments · FX rates · card offers</span>
    </div>
  )
}

// What Visa does in this plan, at a glance: cash trips paid on Visa (through Cybersource), points
// earned by paying with Visa cards, and currency conversions from the Visa Foreign Exchange Rates API.
export function VisaImpact({ result, compact = false }: { result: OptimizeResponse; compact?: boolean }) {
  const p = result.portfolio
  const cash = p.allocations.filter((a) => a.method === 'cash' && a.payment_card)
  const paid = cash.reduce((sum, a) => sum + a.cash_usd, 0)
  const earned = cash.reduce((sum, a) => sum + (a.payment_card?.earned_points ?? 0), 0)
  const cards = [...new Set(cash.map((a) => `${a.payment_card!.name}${a.payment_card!.tier ? ` (${a.payment_card!.tier})` : ''}`))]
  const fx = [...new Set(p.allocations.flatMap((a) => (a.local_fx?.currency ? [a.local_fx.currency] : [])))]

  return (
    <section className={`visa-impact ${compact ? 'compact' : 'card'}`}>
      <div className="visa-impact-head">
        <VisaMark />
        <strong>What Visa does in this plan</strong>
      </div>
      <div className="visa-tiles">
        <div className="visa-tile">
          <div className="visa-value">{fmtUsd(paid)}</div>
          <div className="small">
            {cash.length ? `${cash.length} cash trip${cash.length === 1 ? '' : 's'} paid with Visa` : 'No cash trips to pay'}
          </div>
          <div className="muted small">Checkout through Visa's Cybersource gateway</div>
        </div>
        <div className="visa-tile">
          <div className="visa-value gain">+{fmtPts(earned)}</div>
          <div className="small">points earned paying with Visa</div>
          <div className="muted small">{cards.length ? cards.join(', ') : 'Best Visa card chosen per trip'}</div>
        </div>
        <div className="visa-tile">
          <div className="visa-value">{fx.length ? `USD → ${fx.join(', ')}` : 'USD only'}</div>
          <div className="small">{fx.length ? 'local prices via Visa FX' : 'no currency conversion needed'}</div>
          <div className="muted small">Visa Foreign Exchange Rates API · Sandbox sample rates</div>
        </div>
      </div>
    </section>
  )
}
