// Short, speakable summaries: what the voice agent receives from its tools.
import { cabinLabel, fmtPts, fmtUsd, type Allocation, type OptimizeResponse, type ParseResult } from './api'

export function parseSummary(p: ParseResult, names: Record<string, string>): string {
  const parts: string[] = []
  if (p.balances.length) parts.push(`Balances: ${p.balances.map((b) => `${names[b.holding]} ${fmtPts(b.points)}`).join('; ')}.`)
  if (p.trips.length)
    parts.push(
      `Trips: ${p.trips
        .map((t) => `${t.label} (${t.origin} to ${t.destination}, ${cabinLabel(t.cabin)}, ${t.outbound_date}${t.date_is_estimate ? ', date estimated' : ''})`)
        .join('; ')}.`,
    )
  if (p.warnings.length) parts.push(`Unclear: ${p.warnings.join('; ')}.`)
  return parts.join(' ') || 'Nothing recognizable: ask for balances and trips again.'
}

function allocationLine(a: Allocation, names: Record<string, string>): string {
  if (a.method === 'cash') {
    const c = a.payment_card
    return `${a.trip_label}: pay cash ${fmtUsd(a.cash_usd)}${c ? ` with ${c.name}, earning ${fmtPts(c.earned_points)} ${names[c.holding]}` : ''}`
  }
  const from = a.sources.map((s) => names[s.holding]).join(' and ')
  return `${a.trip_label}: ${fmtPts(a.award_points)} ${names[a.program!]} points in ${cabinLabel(a.cabin)}, from ${from}`
}

export function planSummary(r: OptimizeResponse, names: Record<string, string>): string {
  const head =
    r.value_gained_usd > 0
      ? `Planning the whole year gets ${fmtUsd(r.value_gained_usd)} more travel value than booking trip by trip` +
        (r.points_saved > 0 ? ` and uses ${fmtPts(r.points_saved)} fewer points.` : '.')
      : 'Whole-year and trip-by-trip planning agree for these trips.'
  return `${head} Plan: ${r.portfolio.allocations.map((a) => allocationLine(a, names)).join('. ')}.`
}

export function explainTrip(r: OptimizeResponse | null, trip: string): string {
  if (!r) return 'No plan yet: run the optimizer first.'
  const q = trip.trim().toLowerCase()
  const a = r.portfolio.allocations.find((x) => x.trip_label.toLowerCase().includes(q) || x.trip_id.toLowerCase().includes(q))
  return a ? `${a.trip_label}: ${a.reason}` : `No trip called ${trip} in the plan.`
}
