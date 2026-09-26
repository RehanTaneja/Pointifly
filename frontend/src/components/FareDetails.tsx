import { fmtDuration, fmtUsd, type Allocation } from '../api'

const time = (t: string | null) => t?.slice(11) ?? ''

// The real itinerary behind a decision: the flight you'd buy (cash) or the cash fare an
// award is measured against (points). Links to the same search on Google Flights.
export function FareDetails({ a }: { a: Allocation }) {
  const fare = a.fare
  if (!fare) return <div className="muted small">Sample price, no live fare fetched.</div>
  const it = fare.itinerary
  return (
    <details className="fare">
      <summary className="small">
        {a.method === 'cash' ? 'Cheapest fare' : 'Cash fare this award replaces'}: {fmtUsd(fare.price)} ·{' '}
        {fare.airlines.join(', ')}
        {it?.total_duration_min != null && ` · ${fmtDuration(it.total_duration_min)}`}
      </summary>
      {it && (
        <ol className="legs small">
          {it.flights.map((f, i) => (
            <li key={i}>
              <strong>{f.flight_number}</strong> {f.from} {time(f.departs)} → {f.to} {time(f.arrives)}
              <span className="muted">
                {' '}
                · {f.departs?.slice(0, 10)} · {f.travel_class} · {fmtDuration(f.duration_min)}
                {f.airplane && ` · ${f.airplane}`}
              </span>
              {it.layovers[i] && (
                <div className="muted">
                  Layover {it.layovers[i].airport} · {fmtDuration(it.layovers[i].duration_min)}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      <div className="row between small">
        <span className="muted">
          {fare.source}, fetched {fare.fetched_at.slice(0, 10)}
        </span>
        {fare.google_flights_url && (
          <a href={fare.google_flights_url} target="_blank" rel="noreferrer">
            View on Google Flights ↗
          </a>
        )}
      </div>
    </details>
  )
}
