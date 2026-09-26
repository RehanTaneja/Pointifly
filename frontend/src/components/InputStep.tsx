import { useState } from 'react'
import { fmtUsd, type Balance, type Dataset, type Trip } from '../api'

const EXAMPLE_SENTENCE =
  'I have 100k Amex, 120k Chase, 80k Capital One and 100k United miles. This year I am going to Miami in March, London in May, Delhi in August and Tokyo in November.'

type Props = {
  dataset: Dataset
  holdingNames: Record<string, string>
  linkedHoldings: string[]
  onOptimize: (balances: Balance[], trips: Trip[]) => void
}

export function InputStep({ dataset, holdingNames, linkedHoldings, onOptimize }: Props) {
  // Balances stay manual: no aggregator exposes points balances.
  const [balances, setBalances] = useState<Balance[]>(() =>
    linkedHoldings.map((h) => ({
      holding: h,
      points: dataset.sample_balances.find((b) => b.holding === h)?.points ?? 0,
    })),
  )
  const [sentence, setSentence] = useState(EXAMPLE_SENTENCE)
  const [trips, setTrips] = useState<Trip[]>([])

  const setPoints = (holding: string, points: number) =>
    setBalances((prev) => prev.map((b) => (b.holding === holding ? { ...b, points } : b)))

  // Mock parse: the LLM parse isn't wired yet, so this loads the sample trips.
  const parse = () => setTrips(dataset.sample_trips)

  return (
    <section className="card">
      <h2>2. Tell us your points and trips</h2>

      <h3>Point balances</h3>
      <div className="balances">
        {balances.map((b) => (
          <label key={b.holding} className="balance">
            <span>{holdingNames[b.holding]}</span>
            <input
              type="number"
              min={0}
              step={1000}
              value={b.points}
              onChange={(e) => setPoints(b.holding, Number(e.target.value))}
            />
          </label>
        ))}
      </div>

      <h3>Trips this year</h3>
      <textarea rows={3} value={sentence} onChange={(e) => setSentence(e.target.value)} />
      <div className="row">
        <button onClick={parse}>
          Parse trips <span className="tag">mock: loads sample trips</span>
        </button>
        <button disabled title="ElevenLabs voice agent: not connected yet">
          🎙 Talk to agent <span className="tag">not connected</span>
        </button>
      </div>

      {trips.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Trip</th>
              <th>Route</th>
              <th>Month</th>
              <th>Cabin</th>
              <th>Cash price</th>
            </tr>
          </thead>
          <tbody>
            {trips.map((t) => (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td>
                  {t.origin} → {t.destination}
                </td>
                <td>{t.month}</td>
                <td>{t.cabin}</td>
                <td>{fmtUsd(t.cash_price_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="row end">
        <button className="primary" disabled={trips.length === 0} onClick={() => onOptimize(balances, trips)}>
          Optimize my year
        </button>
      </div>
    </section>
  )
}
