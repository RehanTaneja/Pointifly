import { useEffect, useRef, useState } from 'react'
import { AddTripForm } from './AddTripForm'
import { TransferPartners } from './TransferPartners'
import { parseSummary } from '../summaries'
import { MicIcon, TALK_TO_AGENT } from './VoiceAgent'
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
  voiceEnabled?: boolean
}

export function InputStep({ dataset, holdingNames, linkedHoldings, onOptimize, registerApi, voiceEnabled }: Props) {
  // Balances come from the user (typed, parsed or spoken): no aggregator exposes points balances.
  // Nothing is pre-filled.
  const [balances, setBalances] = useState<Balance[]>(() => linkedHoldings.map((h) => ({ holding: h, points: 0 })))
  const [sentence, setSentence] = useState('')
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

  // Apply parsed balances (update or add a row) and trips (added unless already listed).
  const merge = (p: ParseResult, prev: { balances: Balance[]; trips: Trip[] }) => {
    const balances = [...prev.balances]
    for (const b of p.balances) {
      const i = balances.findIndex((x) => x.holding === b.holding)
      if (i >= 0) balances[i] = b
      else balances.push(b)
    }
    const trips = [...prev.trips, ...p.trips.filter((t) => !prev.trips.some((x) => x.id === t.id))].slice(0, 8)
    return { balances, trips }
  }

  const fill = async (text: string) => {
    setParsing(true)
    setParseError(null)
    try {
      const p = await parseSentence(text, latest.current.home)
      const next = merge(p, latest.current)
      latest.current = { ...latest.current, ...next } // visible to the next tool call right away
      setBalances(next.balances)
      setTrips(next.trips)
      setNotes(p.warnings)
      return parseSummary(p, holdingNames, next)
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
      <p className="muted small">Describe your balances and trips in a sentence, or talk to Pointifly.</p>
      <textarea
        rows={3}
        value={sentence}
        placeholder="Your point balances and the trips you're planning: where, when and in which cabin"
        onChange={(e) => setSentence(e.target.value)}
      />
      <div className="row">
        <label className="home-airport small">
          From
          <input value={home} maxLength={3} onChange={(e) => setHome(e.target.value.toUpperCase())} />
        </label>
        <button className="pay-button" onClick={() => fill(sentence)} disabled={parsing || !sentence.trim()}>
          {parsing && <span className="button-spinner light" />}
          {parsing ? 'Reading…' : 'Parse trips'}
        </button>
        {voiceEnabled && (
          <button className="icon" onClick={() => window.dispatchEvent(new Event(TALK_TO_AGENT))}>
            <MicIcon /> Talk to agent
          </button>
        )}
      </div>
      {parseError && <div className="banner error small">{parseError}</div>}
      {notes.length > 0 && (
        <ul className="notes small muted">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      <h3>Point balances</h3>
      <div className="balances">
        {balances.map((b) => (
          <label key={b.holding} className="balance">
            <span>{holdingNames[b.holding]}</span>
            <input
              type="number"
              min={0}
              step={1000}
              value={b.points || ''}
              placeholder="0"
              onChange={(e) => setPoints(b.holding, Number(e.target.value))}
            />
          </label>
        ))}
      </div>

      <h3>Trips this year</h3>
      <AddTripForm existing={trips} max={8} onAdd={(t) => setTrips((prev) => [...prev, t])} />

      {trips.length > 0 && (
        <div className="table-wrap">
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
        </div>
      )}

      <div className="row end">
        <button className="primary" disabled={trips.length === 0} onClick={() => onOptimize(balances, trips)}>
          Optimize my year<span className="arrow">→</span>
        </button>
      </div>

      <h3>Your programs and transfer ratios</h3>
      <TransferPartners dataset={dataset} holdings={balances.map((b) => b.holding)} holdingNames={holdingNames} />
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
