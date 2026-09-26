import { useEffect, useRef, useState } from 'react'
import { AddTripForm } from './AddTripForm'
import { TransferPartners } from './TransferPartners'
import { parseSummary } from '../summaries'
import {
  CABINS,
  cabinLabel,
  fmtUsd,
  parseSentence,
  type Balance,
  type Cabin,
  type Dataset,
  type ParseResult,
  type Trip,
} from '../api'

const EXAMPLE_SENTENCE =
  'I have 100k Amex, 120k Chase, 80k Capital One and 100k United miles. This year I am going to Miami in March, London in May, Delhi in August and Tokyo in November.'

// What the voice agent's tools use: fill the form from a sentence, read the current inputs.
export type InputApi = {
  fill: (sentence: string) => Promise<string>
  current: () => { balances: Balance[]; trips: Trip[] }
}

type Props = {
  dataset: Dataset
  holdingNames: Record<string, string>
  linkedHoldings: string[]
  onOptimize: (balances: Balance[], trips: Trip[]) => void
  registerApi?: (api: InputApi | null) => void
}

export function InputStep({ dataset, holdingNames, linkedHoldings, onOptimize, registerApi }: Props) {
  // Balances stay manual: no aggregator exposes points balances.
  const [balances, setBalances] = useState<Balance[]>(() =>
    linkedHoldings.map((h) => ({
      holding: h,
      points: dataset.sample_balances.find((b) => b.holding === h)?.points ?? 0,
    })),
  )
  const [sentence, setSentence] = useState(EXAMPLE_SENTENCE)
  const [trips, setTrips] = useState<Trip[]>([])
  const [home, setHome] = useState('ATL')
  const [parsing, setParsing] = useState(false)
  const [notes, setNotes] = useState<string[]>([])
  const [parseError, setParseError] = useState<string | null>(null)
  const latest = useRef({ balances, trips, home })
  useEffect(() => {
    latest.current = { balances, trips, home }
  }, [balances, trips, home])

  const setCabin = (id: string, cabin: Cabin) =>
    setTrips((prev) => prev.map((t) => (t.id === id ? { ...t, cabin } : t)))

  const removeTrip = (id: string) => setTrips((prev) => prev.filter((t) => t.id !== id))

  const setPoints = (holding: string, points: number) =>
    setBalances((prev) => prev.map((b) => (b.holding === holding ? { ...b, points } : b)))

  const loadSampleYear = () => setTrips((prev) => [...dataset.sample_trips, ...prev.filter((t) => t.custom)])

  // Apply parsed balances (update or add a row) and trips (added unless already listed).
  const apply = (p: ParseResult) => {
    setBalances((prev) => {
      const next = [...prev]
      for (const b of p.balances) {
        const i = next.findIndex((x) => x.holding === b.holding)
        if (i >= 0) next[i] = b
        else next.push(b)
      }
      return next
    })
    setTrips((prev) => [...prev, ...p.trips.filter((t) => !prev.some((x) => x.id === t.id))].slice(0, 8))
    setNotes(p.warnings)
  }

  const fill = async (text: string) => {
    setParsing(true)
    setParseError(null)
    try {
      const p = await parseSentence(text, latest.current.home)
      apply(p)
      return parseSummary(p, holdingNames)
    } catch (e) {
      setParseError((e as Error).message)
      return `Couldn't read that: ${(e as Error).message}`
    } finally {
      setParsing(false)
    }
  }

  useEffect(() => {
    registerApi?.({ fill, current: () => ({ balances: latest.current.balances, trips: latest.current.trips }) })
    return () => registerApi?.(null)
  })

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
      <p className="muted small">Describe your balances and trips in one sentence, or talk to Pointifly.</p>
      <textarea rows={3} value={sentence} onChange={(e) => setSentence(e.target.value)} />
      <div className="row">
        <label className="home-airport small">
          From
          <input value={home} maxLength={3} onChange={(e) => setHome(e.target.value.toUpperCase())} />
        </label>
        <button className="primary" onClick={() => fill(sentence)} disabled={parsing || !sentence.trim()}>
          {parsing ? 'Reading…' : 'Parse trips'}
        </button>
        <button onClick={loadSampleYear}>Load sample year</button>
      </div>
      {parseError && <div className="banner error small">{parseError}</div>}
      {notes.length > 0 && (
        <ul className="notes small muted">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

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
                <td>
                  {t.outbound_date ?? t.month}
                  {t.date_is_estimate && <div className="muted small">estimated (15th of the month)</div>}
                </td>
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
