// Types mirror backend/app/models.py and backend/app/data/redemptions.json.

export type Balance = { holding: string; points: number }

export const CABINS = ['economy', 'premium_economy', 'business', 'first'] as const
export type Cabin = (typeof CABINS)[number]
export const cabinLabel = (c: string) => c.replace('_', ' ')

export type AwardOption = { program: string; points: number; cabin: Cabin; cash_price_usd?: number }

export type TransferDetail = {
  ratio: number
  quoted: string
  minimum: number
  increment: number
  transfer_time: string | null
  via?: string
}

export type Currency = {
  id: string
  name: string
  transfers: Record<string, number>
  transfer_details: Record<string, TransferDetail>
  transfer_source: { url: string; title: string; eligibility: string; verified_on: string }
}

// Official ratio as "1:1", or "1,000 → 800" when not 1:1.
export const ratioLabel = (r: number) => (r === 1 ? '1:1' : `1,000 → ${fmtPts(Math.round(1000 * r))}`)

export type Flight = {
  airline: string | null
  flight_number: string | null
  from: string | null
  to: string | null
  departs: string | null
  arrives: string | null
  duration_min: number | null
  travel_class: string | null
  airplane: string | null
}

export type Fare = {
  price: number
  airlines: string[]
  source: string
  fetched_at: string
  google_flights_url: string | null
  itinerary?: {
    total_duration_min: number | null
    flights: Flight[]
    layovers: { airport: string | null; duration_min: number | null }[]
  }
}

export type Trip = {
  id: string
  label: string
  origin: string
  destination: string
  month: string
  cabin: Cabin
  cash_price_usd: number
  award_options: AwardOption[]
  cash_fares?: Partial<Record<Cabin, { price: number; fetched_at: string }>>
  outbound_date?: string
  cash_source?: { source: string; fetched_at: string }
  custom?: boolean // entered by the user; priced live on optimize
  custom_label?: string // a name the user typed (else the backend uses the destination city)
}

export type Airport = { code: string; name: string; city: string; country: string }
export const searchAirports = (q: string) => request<Airport[]>(`/api/airports?q=${encodeURIComponent(q)}`)

export type Dataset = {
  _note: string
  reserve_value_cpp: { default: number }
  currencies: Currency[]
  programs: { id: string; name: string }[]
  sample_balances: Balance[]
  sample_trips: Trip[]
}

export type Allocation = {
  trip_id: string
  trip_label: string
  method: 'points' | 'cash'
  program: string | null
  cabin: string
  sources: Balance[]
  points: number
  cash_usd: number
  fees_usd: number
  value_usd: number
  cents_per_point: number | null
  reason: string
  fare: Fare | null
  award_points: number
  award_source: AwardSource | null
  local_fx: FxRate | null
}

// Visa FX rate; `date` is when Pointifly retrieved it from Visa.
export type FxRate = { currency?: string; rate: number; date: string; source: string }

export type Fee = { amount: number; currency: string; per: string; source_url: string; usd: (FxRate & { amount: number }) | null }

export type VisaBenefit = {
  id: number
  title: string
  description: string
  merchant: string
  cards: string[]
  valid_to: string | null
  url: string | null
  image: string | null
}

export const getVisaBenefits = () => request<{ offers: VisaBenefit[]; date: string | null; source: string }>('/api/visa/benefits')

export const fmtMoney = (amount: number, currency: string) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: amount >= 100 ? 0 : 2 }).format(amount)

export type AwardSource =
  | { type: 'chart'; title: string; url: string; effective: string; detail: string; notes: string; fee?: Fee }
  | { type: 'sample' }

export type StrategyResult = {
  name: string
  allocations: Allocation[]
  total_points: number
  total_value_usd: number
  cash_out_of_pocket_usd: number
  remaining_balances: Balance[]
}

export type OptimizeResponse = {
  mock: boolean
  greedy: StrategyResult
  portfolio: StrategyResult
  points_saved: number
  value_gained_usd: number
  sankey: { nodes: { name: string }[]; links: { source: number; target: number; value: number }[] }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail).catch(() => null)
    throw new Error(detail ?? `${init?.method ?? 'GET'} ${path} failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const getDataset = () => request<Dataset>('/api/dataset')

// A credit card detected through Plaid (or the mock), mapped to the points program it earns.
export type LinkedCard = {
  institution: string
  product: string
  holding: string | null
  note?: string | null
  mask?: string | null
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const plaid = {
  status: () => request<PlaidStatus>('/api/plaid/status'),
  linkToken: () => post<{ link_token: string }>('/api/plaid/link_token'),
  exchange: (public_token: string, institution_name: string | null) =>
    post<{ connection_id: string; cards: LinkedCard[] }>('/api/plaid/exchange', { public_token, institution_name }),
  sandboxDemo: () => post<{ cards: LinkedCard[] }>('/api/plaid/sandbox_demo'),
}

export type PlaidStatus = { configured: boolean; env: string; presentation: boolean }

export const optimize = (balances: Balance[], trips: Trip[]) =>
  request<OptimizeResponse>('/api/optimize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      balances,
      trip_ids: trips.filter((t) => !t.custom).map((t) => t.id),
      cabins: Object.fromEntries(trips.filter((t) => !t.custom).map((t) => [t.id, t.cabin])),
      custom_trips: trips
        .filter((t) => t.custom)
        .map((t) => ({ origin: t.origin, destination: t.destination, date: t.outbound_date, cabin: t.cabin, label: t.custom_label })),
    }),
  })

export function holdingNames(ds: Dataset): Record<string, string> {
  return Object.fromEntries([...ds.currencies, ...ds.programs].map((h) => [h.id, h.name]))
}

export const fmtPts = (n: number) => n.toLocaleString('en-US')
export const fmtDuration = (min: number | null) => (min == null ? '' : `${Math.floor(min / 60)}h ${min % 60}m`)
export const fmtUsd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
