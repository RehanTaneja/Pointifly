// Types mirror backend/app/models.py and backend/app/data/redemptions.json.

export type Balance = { holding: string; points: number }

export type AwardOption = { program: string; points: number; cabin?: string; cash_price_usd?: number }

export type Trip = {
  id: string
  label: string
  origin: string
  destination: string
  month: string
  cabin: string
  cash_price_usd: number
  award_options: AwardOption[]
}

export type Dataset = {
  _note: string
  currencies: { id: string; name: string; transfers: Record<string, number> }[]
  programs: { id: string; name: string }[]
  sample_balances: Balance[]
  sample_trips: Trip[]
}

export type Allocation = {
  trip_id: string
  trip_label: string
  method: 'points' | 'cash'
  source: string | null
  program: string | null
  points: number
  cash_usd: number
  value_usd: number
  cents_per_point: number | null
  reason: string
}

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
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export const getDataset = () => request<Dataset>('/api/dataset')

export const optimize = (balances: Balance[], tripIds: string[]) =>
  request<OptimizeResponse>('/api/optimize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ balances, trip_ids: tripIds }),
  })

export function holdingNames(ds: Dataset): Record<string, string> {
  return Object.fromEntries([...ds.currencies, ...ds.programs].map((h) => [h.id, h.name]))
}

export const fmtPts = (n: number) => n.toLocaleString('en-US')
export const fmtUsd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
