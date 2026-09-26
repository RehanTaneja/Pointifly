import { useState } from 'react'
import {
  cabinLabel,
  fmtMoney,
  fmtPts,
  fmtUsd,
  ratioLabel,
  type Allocation,
  type Currency,
  type OptimizeResponse,
  type StrategyResult,
} from '../api'
import { AwardSourceNote } from './AwardSourceNote'
import { CheckoutModal } from './CheckoutModal'
import { FareDetails } from './FareDetails'
import { VisaBenefits } from './VisaBenefits'
import { FlowSankey } from './FlowSankey'

type Props = {
  result: OptimizeResponse
  holdingNames: Record<string, string>
  currencies: Currency[]
  onReset: () => void
}

function describe(a: Allocation, names: Record<string, string>, currencies: Currency[]) {
  if (a.method === 'cash') {
    const c = a.payment_card
    return c
      ? `Pay cash · ${fmtUsd(a.cash_usd)} with ${c.name} · earns ${fmtPts(c.earned_points)} ${names[c.holding]} (${c.rate}x)`
      : `Pay cash · ${fmtUsd(a.cash_usd)}`
  }
  const from = a.sources.map((s) => {
    if (s.holding === a.program) return `${fmtPts(s.points)} miles`
    const d = currencies.find((c) => c.id === s.holding)?.transfer_details[a.program!]
    return `${names[s.holding]} ${fmtPts(s.points)}${d ? ` (${ratioLabel(d.ratio)}${d.via ? `, via ${d.via.split('.')[0]}` : ''})` : ''}`
  })
  return `${names[a.program!]} ${cabinLabel(a.cabin)} · ${from.join(' + ')}`
}

type ColumnProps = { s: StrategyResult; names: Record<string, string>; currencies: Currency[]; highlight?: boolean }

function StrategyColumn({ s, names, currencies, highlight }: ColumnProps) {
  return (
    <div className={`strategy ${highlight ? 'highlight' : ''}`}>
      <h3>{s.name}</h3>
      <div className="stats">
        <div>
          <div className="stat">{fmtPts(s.total_points)}</div>
          <div className="muted small">points spent</div>
        </div>
        <div>
          <div className="stat">{fmtUsd(s.total_value_usd)}</div>
          <div className="muted small">travel value from points</div>
        </div>
        <div>
          <div className="stat">{fmtUsd(s.cash_out_of_pocket_usd)}</div>
          <div className="muted small">cash</div>
        </div>
      </div>
      {s.points_earned > 0 && (
        <div className="small earned">+{fmtPts(s.points_earned)} points earned paying cash with Visa</div>
      )}
      <ul className="allocs">
        {s.allocations.map((a) => (
          <li key={a.trip_id}>
            <div className="row between">
              <strong>{a.trip_label}</strong>
              {a.cents_per_point !== null && <span className="tag">{a.cents_per_point.toFixed(1)}¢/pt</span>}
            </div>
            {a.local_fx && <LocalRate fx={a.local_fx} />}
            <div>{describe(a, names, currencies)}</div>
            <AwardSourceNote a={a} />
            <div className="muted small">{a.reason}</div>
            <FareDetails a={a} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Dashboard({ result, holdingNames, currencies, onReset }: Props) {
  const [checkout, setCheckout] = useState<Allocation | null>(null)
  const [paid, setPaid] = useState<Set<string>>(new Set())
  const cashLegs = result.portfolio.allocations.filter((a) => a.method === 'cash')

  return (
    <>
      <div className="banner">
        {result.portfolio.allocations.some((a) => a.fare)
          ? 'Cash fares are live from Google Flights. Aeroplan and ANA award prices come from their official published charts (availability not checked); other programs use sample prices. Currency conversions use Visa FX Sandbox rates: sample data, not live market rates.'
          : 'Sample data: award and cash prices are placeholders, not live quotes.'}
      </div>

      <section className="card headline">
        <Headline r={result} />
      </section>

      <section className="card">
        <h2>Greedy vs. Pointifly</h2>
        <div className="compare">
          <StrategyColumn s={result.greedy} names={holdingNames} currencies={currencies} />
          <StrategyColumn s={result.portfolio} names={holdingNames} currencies={currencies} highlight />
        </div>
      </section>

      <section className="card">
        <h2>Where your points flow</h2>
        <p className="muted small">Pointifly plan, in points. Cash legs are paid separately below.</p>
        <FlowSankey data={result.sankey} />
      </section>

      {cashLegs.length > 0 && (
        <section className="card">
          <h2>Cash legs</h2>
          {cashLegs.map((a) => (
            <div key={a.trip_id} className="row between cash-leg">
              <span>
                <strong>{a.trip_label}</strong> · {fmtUsd(a.cash_usd)}
                {a.local_fx && <LocalRate fx={a.local_fx} />}
              </span>
              {paid.has(a.trip_id) ? (
                <span className="tag ok">✓ Paid</span>
              ) : (
                <button className="primary" onClick={() => setCheckout(a)} disabled={!a.payment_card}>
                  Pay with Visa
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      <VisaBenefits />

      <div className="row end">
        <button onClick={onReset}>Start over</button>
      </div>

      {checkout && (
        <CheckoutModal
          allocation={checkout}
          holdingNames={holdingNames}
          onClose={() => setCheckout(null)}
          onPaid={() => setPaid((prev) => new Set(prev).add(checkout.trip_id))}
        />
      )}
    </>
  )
}

const cpp = (s: StrategyResult) => (s.total_points ? (s.total_value_usd / s.total_points) * 100 : 0)

// Says what the numbers show: points spent can go either way, value is the claim.
function Headline({ r }: { r: OptimizeResponse }) {
  if (r.value_gained_usd <= 0) {
    return <p>Trip-by-trip and whole-year planning agree for these trips and balances.</p>
  }
  const value = <strong>{fmtUsd(r.value_gained_usd)} less travel value</strong>
  if (r.points_saved >= 0) {
    return (
      <p>
        Optimizing trip-by-trip spends <strong>{fmtPts(r.points_saved)} more points</strong> and gets {value} than
        optimizing the portfolio.
      </p>
    )
  }
  return (
    <p>
      Optimizing trip-by-trip gets {value} than optimizing the portfolio. Pointifly spends{' '}
      {fmtPts(-r.points_saved)} more points, but each goes further: <strong>{cpp(r.portfolio).toFixed(1)}¢</strong>{' '}
      vs {cpp(r.greedy).toFixed(1)}¢ per point.
    </p>
  )
}

function LocalRate({ fx }: { fx: NonNullable<Allocation['local_fx']> }) {
  return (
    <div className="muted small">
      Local currency: {fmtMoney(1, 'USD')} = {fmtMoney(fx.rate, fx.currency!)}{' '}
      <span className="tag warn">Visa Sandbox sample rate · not live</span>
    </div>
  )
}
