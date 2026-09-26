import { useState } from 'react'

// Mock of Plaid Link (Sandbox). The real flow will return card product names from
// Plaid, which we auto-map to the loyalty holding they earn into.
export type LinkedCard = { institution: string; product: string; holding: string }

const SANDBOX_INSTITUTIONS: { institution: string; cards: Omit<LinkedCard, 'institution'>[] }[] = [
  { institution: 'American Express', cards: [{ product: 'American Express Gold Card', holding: 'amex_mr' }] },
  {
    institution: 'Chase',
    cards: [
      { product: 'Chase Sapphire Preferred', holding: 'chase_ur' },
      { product: 'United Explorer Card', holding: 'united' },
    ],
  },
  { institution: 'Capital One', cards: [{ product: 'Capital One Venture', holding: 'capital_one' }] },
]

type Props = { holdingNames: Record<string, string>; onDone: (cards: LinkedCard[]) => void }

export function ConnectStep({ holdingNames, onDone }: Props) {
  const [linked, setLinked] = useState<LinkedCard[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const linkedInstitutions = new Set(linked.map((c) => c.institution))

  const link = (institution: string) => {
    const inst = SANDBOX_INSTITUTIONS.find((i) => i.institution === institution)!
    setLinked((prev) => [...prev, ...inst.cards.map((c) => ({ ...c, institution }))])
    setModalOpen(false)
  }

  return (
    <section className="card">
      <h2>1. Connect your cards</h2>
      <p className="muted">
        Link each issuer once. We detect your card products and map them to the points programs they earn.
      </p>

      <button className="primary" onClick={() => setModalOpen(true)}>
        Connect with Plaid <span className="tag">Sandbox · mock</span>
      </button>

      {linked.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Issuer</th>
              <th>Card detected</th>
              <th>Earns into</th>
            </tr>
          </thead>
          <tbody>
            {linked.map((c) => (
              <tr key={c.product}>
                <td>{c.institution}</td>
                <td>{c.product}</td>
                <td>{holdingNames[c.holding]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="row end">
        <button className="primary" disabled={linked.length === 0} onClick={() => onDone(linked)}>
          Continue
        </button>
      </div>

      {modalOpen && (
        <div className="modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Select your institution</h3>
            <p className="muted small">Plaid Sandbox (mocked): no real credentials are used.</p>
            {SANDBOX_INSTITUTIONS.map((i) => (
              <button
                key={i.institution}
                className="list-item"
                disabled={linkedInstitutions.has(i.institution)}
                onClick={() => link(i.institution)}
              >
                {i.institution}
                {linkedInstitutions.has(i.institution) && <span className="tag">linked</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
