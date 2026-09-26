// Short, speakable summaries: what the voice agent receives from its tools.
import {
  cabinLabel,
  fmtPts,
  fmtUsd,
  ratioLabel,
  type Allocation,
  type AgentStatus,
  type Balance,
  type Dataset,
  type OptimizeResponse,
  type ParseResult,
  type Trip,
} from './api'

// What was understood, plus what's still missing (so the agent asks for only that).
export function parseSummary(p: ParseResult, names: Record<string, string>, after: { balances: Balance[]; trips: Trip[] }): string {
  const parts: string[] = []
  if (p.balances.length) parts.push(`Balances: ${p.balances.map((b) => `${names[b.holding]} ${fmtPts(b.points)}`).join('; ')}.`)
  if (p.trips.length)
    parts.push(
      `Trips: ${p.trips
        .map((t) => `${t.label} (${t.origin} to ${t.destination}, ${cabinLabel(t.cabin)}, ${t.outbound_date}${t.date_is_estimate ? ', date estimated' : ''})`)
        .join('; ')}.`,
    )
  if (p.warnings.length) parts.push(`Unclear: ${p.warnings.join('; ')}.`)
  const empty = after.balances.filter((b) => !b.points).map((b) => names[b.holding])
  if (!after.trips.length) parts.push('Still missing: trips (where, when, cabin).')
  if (empty.length)
    parts.push(
      `No balance given for ${empty.join(', ')}: ask once only if the user hasn't already said they have none there; otherwise treat them as zero.`,
    )
  if (after.trips.length) parts.push('Continue with describe_programs once nothing is missing.')
  return parts.join(' ')
}

// The user's programs and how their points move, grouped by ratio: short enough to say aloud.
export function programsSummary(ds: Dataset, balances: Balance[], names: Record<string, string>): string {
  const lines = balances
    .filter((b) => b.points > 0)
    .map((b) => {
      const cur = ds.currencies.find((c) => c.id === b.holding)
      if (!cur) return `${names[b.holding]} (${fmtPts(b.points)} miles): used directly for its own awards.`
      const byRatio = new Map<string, string[]>()
      for (const [pid, d] of Object.entries(cur.transfer_details)) {
        const r = ratioLabel(d.ratio)
        byRatio.set(r, [...(byRatio.get(r) ?? []), names[pid]])
      }
      const groups = [...byRatio.entries()].map(([r, ps]) => `${r} to ${ps.length > 3 ? `${ps.slice(0, 3).join(', ')} and ${ps.length - 3} more` : ps.join(', ')}`)
      return `${cur.name} (${fmtPts(b.points)} points): transfers ${groups.join('; ')}.`
    })
  return lines.length ? lines.join(' ') : 'No balances yet: ask for them first.'
}

function allocationLine(a: Allocation, names: Record<string, string>): string {
  if (a.method === 'cash') {
    const c = a.payment_card
    return `${a.trip_label}: cash ${fmtUsd(a.cash_usd)}${c ? ` with the ${c.name} Visa, earning ${fmtPts(c.earned_points)} ${names[c.holding]}` : ''}`
  }
  const from = a.sources.map((s) => names[s.holding]).join(' and ')
  return `${a.trip_label}: ${fmtPts(a.award_points)} ${names[a.program!]} points in ${cabinLabel(a.cabin)}, from ${from}`
}

// Leads with points used and value gained over trip-by-trip, then one clause per trip, then
// what happens next (autonomous payment on or off).
export function planSummary(r: OptimizeResponse, names: Record<string, string>, mandate: AgentStatus | null): string {
  const p = r.portfolio
  const head =
    r.value_gained_usd > 0
      ? `Points used: ${fmtPts(p.total_points)}, for ${fmtUsd(p.total_value_usd)} of travel: ${fmtUsd(r.value_gained_usd)} more value than booking trip by trip` +
        (r.points_saved > 0 ? `, with ${fmtPts(r.points_saved)} fewer points.` : '.')
      : `Points used: ${fmtPts(p.total_points)}, for ${fmtUsd(p.total_value_usd)} of travel. Trip-by-trip booking would do the same here.`
  const trips = `Trips: ${p.allocations.map((a) => allocationLine(a, names)).join('. ')}.`
  const fx = p.allocations.filter((a) => a.local_fx).map((a) => `${a.trip_label} in ${a.local_fx!.currency}`)
  const fxLine = fx.length ? ` Local prices converted with the Visa Foreign Exchange Rates API (Sandbox sample rates): ${fx.join(', ')}.` : ''
  const cash = p.allocations.filter((a) => a.method === 'cash' && a.payment_card)
  // Trips above the user's per-payment limit can't be paid by the agent: say so up front.
  const within = cash.filter((a) => !mandate || a.cash_usd <= mandate.max_per_payment)
  const over = cash.filter((a) => mandate && a.cash_usd > mandate.max_per_payment)
  const overLine = over.length
    ? ` Above the user's ${fmtUsd(mandate!.max_per_payment)} per-payment limit, so the user pays these with the Pay with Visa button (or raises the limit in the full breakdown): ${over.map((a) => `${a.trip_label} ${fmtUsd(a.cash_usd)}`).join(', ')}. Don't offer to pay them.`
    : ''
  const next = !cash.length
    ? ' No cash trips: nothing to pay.'
    : mandate?.autopay
      ? ` Autonomous payment is ON (limit ${fmtUsd(mandate.max_per_payment)} per payment, ${fmtUsd(mandate.max_total)} total).` +
        (within.length ? ` Ask once to confirm paying ${within.map((a) => `${a.trip_label} ${fmtUsd(a.cash_usd)}`).join(' and ')}, then call pay_cash_leg for each.` : '') +
        overLine
      : ` Autonomous payment is OFF: tell the user to tap Pay with Visa for ${cash.map((a) => a.trip_label).join(' and ')}.`
  return `${head} ${trips}${fxLine}${next}`
}

export function explainTrip(r: OptimizeResponse | null, trip: string): string {
  if (!r) return 'No plan yet: run the optimizer first.'
  const q = trip.trim().toLowerCase()
  const a = r.portfolio.allocations.find((x) => x.trip_label.toLowerCase().includes(q) || x.trip_id.toLowerCase().includes(q))
  return a ? `${a.trip_label}: ${a.reason}` : `No trip called ${trip} in the plan.`
}
