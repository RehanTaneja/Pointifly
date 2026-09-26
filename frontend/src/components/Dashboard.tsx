import { useState } from 'react'
import { fmtPts, fmtUsd, type Allocation, type OptimizeResponse, type StrategyResult } from '../api'
import { CheckoutModal } from './CheckoutModal'
import { FlowSankey } from './FlowSankey'

type Props = { result: OptimizeResponse; holdingNames: Record<string, string>; onReset: () => void }

function describe(a: Allocation, names: Record<string, string>) {
  if (a.method === 'cash') return `Pay cash · ${fmtUsd(a.cash_usd)}`
  const from = a.sources.map((s) => (s.holding === a.program ? `${fmtPts(s.points)} miles` : `${names[s.holding]} ${fmtPts(s.points)}`))
  return `${names[a.program!]} ${a.cabin} · ${from.join(' + ')}`
}

function StrategyColumn({ s, names, highlight }: { s: StrategyResult; names: Record<string, string>; highlight?: boolean }) {
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
      <ul className="allocs">
        {s.allocations.map((a) => (
          <li key={a.trip_id}>
            <div className="row between">
              <strong>{a.trip_label}</strong>
              {a.cents_per_point !== null && <span className="tag">{a.cents_per_point.toFixed(1)}¢/pt</span>}
            </div>
            <div>{describe(a, names)}</div>
            <div className="muted small">{a.reason}</div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Dashboard({ result, holdingNames, onReset }: Props) {
  const [checkout, setCheckout] = useState<Allocation | null>(null)
  const [paid, setPaid] = useState<Set<string>>(new Set())
  const cashLegs = result.portfolio.allocations.filter((a) => a.method === 'cash')

  return (
    <>
      <div className="banner">
        {result.mock ? 'Mock optimizer output. ' : 'Computed by the optimizer on '}
        sample data: award and cash prices are placeholders, not live quotes.
      </div>

      <section className="card headline">
        <p>
          Optimizing trip-by-trip spends <strong>{fmtPts(result.points_saved)} more points</strong> and gets{' '}
          <strong>{fmtUsd(result.value_gained_usd)} less travel value</strong> than optimizing the portfolio.
        </p>
      </section>

      <section className="card">
        <h2>Greedy vs. Pointfolio</h2>
        <div className="compare">
          <StrategyColumn s={result.greedy} names={holdingNames} />
          <StrategyColumn s={result.portfolio} names={holdingNames} highlight />
        </div>
      </section>

      <section className="card">
        <h2>Where your points flow</h2>
        <p className="muted small">Pointfolio plan, in points. Cash legs are paid separately below.</p>
        <FlowSankey data={result.sankey} />
      </section>

      {cashLegs.length > 0 && (
        <section className="card">
          <h2>Cash legs</h2>
          <p className="muted small">
            FX: Visa Foreign Exchange Rates API <span className="tag">not connected yet</span>
          </p>
          {cashLegs.map((a) => (
            <div key={a.trip_id} className="row between cash-leg">
              <span>
                <strong>{a.trip_label}</strong> · {fmtUsd(a.cash_usd)}
              </span>
              {paid.has(a.trip_id) ? (
                <span className="tag ok">Paid (demo)</span>
              ) : (
                <button className="primary" onClick={() => setCheckout(a)}>
                  Pay with Visa
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      <div className="row end">
        <button onClick={onReset}>Start over</button>
      </div>

      {checkout && (
        <CheckoutModal
          allocation={checkout}
          onClose={() => setCheckout(null)}
          onPaid={() => {
            setPaid((prev) => new Set(prev).add(checkout.trip_id))
            setCheckout(null)
          }}
        />
      )}
    </>
  )
}
