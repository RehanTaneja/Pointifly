import { useEffect, useState } from 'react'
import { CABINS, cabinLabel, searchAirports, type Airport, type Cabin, type Trip } from '../api'

const MAX_DAYS_AHEAD = 330 // Google Flights' booking window (matches the backend)
const isoDay = (offset: number) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10)

// Airport picker: type a city, airport or code; results come from our own airport data.
function AirportInput(props: { label: string; value: string; onChange: (code: string, city?: string) => void }) {
  const { label, value, onChange } = props
  const [text, setText] = useState(value)
  const [options, setOptions] = useState<Airport[]>([])
  const listId = `airports-${label}`

  const searchable = text.trim().length >= 2
  useEffect(() => {
    if (!searchable) return
    const t = setTimeout(() => searchAirports(text).then(setOptions).catch(() => setOptions([])), 200)
    return () => clearTimeout(t)
  }, [text, searchable])

  return (
    <label className="field">
      <span>{label}</span>
      <input
        list={listId}
        value={text}
        placeholder="City or code"
        onChange={(e) => {
          setText(e.target.value)
          const code = e.target.value.trim().toUpperCase()
          const match = options.find((a) => a.code === code)
          onChange(/^[A-Z]{3}$/.test(code) ? code : '', match?.city.replace(/\s*\(.*\)/, ''))
        }}
      />
      <datalist id={listId}>
        {(searchable ? options : []).map((a) => (
          <option key={a.code} value={a.code}>
            {a.city}, {a.country} · {a.name}
          </option>
        ))}
      </datalist>
    </label>
  )
}

type Props = { existing: Trip[]; onAdd: (t: Trip) => void; max: number }

export function AddTripForm({ existing, onAdd, max }: Props) {
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [destinationCity, setDestinationCity] = useState<string | undefined>()
  const [date, setDate] = useState(isoDay(30))
  const [cabin, setCabin] = useState<Cabin>('economy')
  const [label, setLabel] = useState('')
  const [key, setKey] = useState(0) // remounts the airport inputs after adding

  const id = `c-${origin}-${destination}-${date}`
  const error =
    existing.length >= max
      ? `At most ${max} trips`
      : origin && origin === destination
        ? 'Origin and destination must differ'
        : existing.some((t) => t.id === id)
          ? 'That trip is already on the list'
          : null
  const ready = origin && destination && date && !error

  const add = () => {
    onAdd({
      id,
      // Only a typed name is sent; otherwise the backend names the trip after the destination city.
      label: label.trim() || destinationCity || destination,
      custom_label: label.trim() || undefined,
      origin,
      destination,
      outbound_date: date,
      month: date.slice(0, 7),
      cabin,
      cash_price_usd: 0,
      award_options: [],
      custom: true,
    })
    setDestination('')
    setDestinationCity(undefined)
    setLabel('')
    setKey((k) => k + 1)
  }

  return (
    <div className="add-trip">
      <AirportInput key={`o${key}`} label="From" value={origin} onChange={setOrigin} />
      <AirportInput
        key={`d${key}`}
        label="To"
        value=""
        onChange={(code, city) => {
          setDestination(code)
          setDestinationCity(city)
        }}
      />
      <label className="field">
        <span>Date</span>
        <input type="date" value={date} min={isoDay(1)} max={isoDay(MAX_DAYS_AHEAD)} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className="field">
        <span>Cabin</span>
        <select value={cabin} onChange={(e) => setCabin(e.target.value as Cabin)}>
          {CABINS.map((c) => (
            <option key={c} value={c}>
              {cabinLabel(c)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Name (optional)</span>
        <input value={label} placeholder="e.g. Paris" onChange={(e) => setLabel(e.target.value)} />
      </label>
      <button disabled={!ready} onClick={add}>
        Add trip
      </button>
      {error && <span className="small muted">{error}</span>}
    </div>
  )
}
