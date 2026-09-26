import { fmtMoney, fmtPts, type Allocation } from '../api'

// Where an award's points price came from: an official published chart, or sample data.
export function AwardSourceNote({ a }: { a: Allocation }) {
  const src = a.award_source
  if (!src) return null
  const leftover = a.points - a.award_points
  if (src.type === 'sample') {
    return (
      <div className="small">
        <span className="tag">sample price</span> {fmtPts(a.award_points)} pts, not from a published chart
      </div>
    )
  }
  return (
    <div className="small award-source">
      <span className="tag ok">official chart</span> {fmtPts(a.award_points)} pts · {src.detail}
      {leftover > 0 && <span className="muted"> · transfers {fmtPts(a.points)} ({fmtPts(leftover)} left over)</span>}
      {src.fee && (
        <div>
          + {fmtMoney(src.fee.amount, src.fee.currency)} partner booking fee
          {src.fee.usd ? (
            <span className="muted">
              {' '}
              ≈ {fmtMoney(src.fee.usd.amount, 'USD')} at the Visa rate (retrieved {src.fee.usd.date}), included in the plan
            </span>
          ) : (
            <span className="muted"> (not converted: no Visa rate available)</span>
          )}
        </div>
      )}
      <div className="muted">
        {src.notes}{' '}
        <a href={src.url} target="_blank" rel="noreferrer">
          {src.title} ↗
        </a>
      </div>
    </div>
  )
}
