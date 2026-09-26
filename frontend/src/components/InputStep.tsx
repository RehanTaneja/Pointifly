import { useState } from 'react'
import { AddTripForm } from './AddTripForm'
import { TransferPartners } from './TransferPartners'
import { CABINS, cabinLabel, fmtUsd, type Balance, type Cabin, type Dataset, type Trip } from '../api'

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

  const setCabin = (id: string, cabin: Cabin) =>
    setTrips((prev) => prev.map((t) => (t.id === id ? { ...t, cabin } : t)))

  const removeTrip = (id: string) => setTrips((prev) => prev.filter((t) => t.id !== id))

  const setPoints = (holding: string, points: number) =>
    setBalances((prev) => prev.map((b) => (b.holding === holding ? { ...b, points } : b)))

  // Mock parse: the LLM parse isn't wired yet, so this loads the sample trips (keeping custom ones).
  const parse = () => setTrips((prev) => [...dataset.sample_trips, ...prev.filter((t) => t.custom)])

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

      <h3>Transfer partners and ratios</h3>
      <TransferPartners dataset={dataset} holdings={balances.map((b) => b.holding)} holdingNames={holdingNames} />

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

      <AddTripForm existing={trips} max={8} onAdd={(t) => setTrips((prev) => [...prev, t])} />

      {trips.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Trip</th>
              <th>Route</th>
              <th>Date</th>
              <th>Cabin</th>
              <th>Cash price</th>
              <th>Price source</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trips.map((t) => (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td>
                  {t.origin} → {t.destination}
                </td>
                <td>{t.outbound_date ?? t.month}</td>
                <td>
                  <select value={t.cabin} onChange={(e) => setCabin(t.id, e.target.value as Cabin)}>
                    {CABINS.map((c) => (
                      <option key={c} value={c}>
                        {cabinLabel(c)}
                      </option>
                    ))}
                  </select>
                </td>
                <CashPrice trip={t} base={dataset.sample_trips.find((b) => b.id === t.id)} />
                <td>
                  <button className="link" title="Remove trip" onClick={() => removeTrip(t.id)}>
                    ✕
                  </button>
                </td>
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

// Price for the selected cabin: already fetched, sample, or fetched live on optimize.
function CashPrice({ trip, base }: { trip: Trip; base?: Trip }) {
  const fetched = trip.cash_fares?.[trip.cabin]
  if (fetched) {
    return (
      <>
        <td>{fmtUsd(fetched.price)}</td>
        <td className="small">
          Google Flights via SerpApi
          <div className="muted">fetched {fetched.fetched_at.slice(0, 10)}</div>
        </td>
      </>
    )
  }
  if (base && trip.cabin === base.cabin) {
    return (
      <>
        <td>{fmtUsd(base.cash_price_usd)}</td>
        <td className="small">
          <span className="tag">sample</span>
        </td>
      </>
    )
  }
  return (
    <>
      <td className="muted">—</td>
      <td className="small muted">Fetched live when you optimize</td>
    </>
  )
}
