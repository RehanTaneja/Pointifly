import { fmtPts, ratioLabel, type Dataset } from '../api'

type Props = { dataset: Dataset; holdings: string[]; holdingNames: Record<string, string> }

// Official transfer ratios for each of the user's banks, and which banks feed each airline program they hold.
export function TransferPartners({ dataset, holdings, holdingNames }: Props) {
  const banks = dataset.currencies.filter((c) => holdings.includes(c.id))
  const programs = dataset.programs.filter((p) => holdings.includes(p.id))

  return (
    <div className="partners">
      {banks.map((c) => (
        <div key={c.id} className="partner-card">
          <div className="row between">
            <strong>{c.name}</strong>
            <a className="small" href={c.transfer_source.url} target="_blank" rel="noreferrer">
              Official source ↗
            </a>
          </div>
          <table className="table small">
            <thead>
              <tr>
                <th>Transfers to</th>
                <th>Ratio</th>
                <th>Min · blocks</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(c.transfer_details).map(([pid, d]) => (
                <tr key={pid}>
                  <td>
                    {holdingNames[pid]}
                    {d.via && <div className="muted">via {d.via.split('.')[0]}</div>}
                  </td>
                  <td title={d.quoted}>{ratioLabel(d.ratio)}</td>
                  <td>
                    {fmtPts(d.minimum)} · {fmtPts(d.increment)}
                  </td>
                  <td className="muted">{d.transfer_time ?? 'not published'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            {c.transfer_source.eligibility} Verified {c.transfer_source.verified_on}.
          </p>
        </div>
      ))}
      {programs.map((p) => {
        const feeders = dataset.currencies.filter((c) => c.transfer_details[p.id])
        return (
          <div key={p.id} className="partner-card">
            <strong>{p.name}</strong>
            <p className="small">
              {feeders.length
                ? `Miles you hold are used directly. Banks that transfer in: ${feeders
                    .map((c) => `${c.name} (${ratioLabel(c.transfer_details[p.id].ratio)})`)
                    .join(', ')}.`
                : 'Miles you hold are used directly. None of your banks transfer in.'}
            </p>
          </div>
        )
      })}
    </div>
  )
}
