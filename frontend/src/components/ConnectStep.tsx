import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { usePlaidLink } from 'react-plaid-link'
import { plaid, type LinkedCard, type PlaidStatus } from '../api'

export type { LinkedCard }

// Used only when the backend has no Plaid keys: a clearly labeled stand-in for Plaid Link.
const MOCK_INSTITUTIONS: { institution: string; cards: Omit<LinkedCard, 'institution'>[] }[] = [
  { institution: 'American Express', cards: [{ product: 'American Express Gold Card', holding: 'amex_mr', product_id: 'amex_gold' }] },
  {
    institution: 'Chase',
    cards: [
      { product: 'Chase Sapphire Preferred', holding: 'chase_ur', product_id: 'chase_sapphire_preferred' },
      { product: 'United Explorer Card', holding: 'united', product_id: 'united_explorer' },
    ],
  },
  { institution: 'Capital One', cards: [{ product: 'Capital One Venture Rewards', holding: 'capital_one', product_id: 'capital_one_venture' }] },
]

type Props = { holdingNames: Record<string, string>; onDone: (cards: LinkedCard[]) => void }

export function ConnectStep({ holdingNames, onDone }: Props) {
  const [status, setStatus] = useState<PlaidStatus | null>(null)
  const [cards, setCards] = useState<LinkedCard[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    plaid
      .status()
      .then(setStatus)
      .catch(() => setStatus({ configured: false, env: 'sandbox', presentation: false }))
  }, [])

  const addCards = (more: LinkedCard[]) =>
    setCards((prev) => [...prev, ...more.filter((c) => !prev.some((p) => p.product === c.product && p.mask === c.mask))])

  const run = async (fn: () => Promise<LinkedCard[]>) => {
    setBusy(true)
    setError(null)
    try {
      addCards(await fn())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const mapped = cards.filter((c) => c.holding)

  return (
    <section className="card">
      <h2>1. Connect your cards</h2>
      <p className="muted">
        Link each issuer once. We detect your card products and map them to the points programs they earn. Point
        balances stay manual (no aggregator exposes them).
      </p>

      {status === null ? (
        <p className="muted small">Checking Plaid…</p>
      ) : status.configured && status.presentation ? (
        // Pitch UI: one button; connects the demo profile through Plaid's API (no Plaid test pages).
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => run(async () => (await plaid.sandboxDemo()).cards)}>
            {busy ? 'Connecting your cards…' : 'Connect with Plaid'}
          </button>
        </div>
      ) : status.configured ? (
        <div className="row">
          <PlaidLinkButton disabled={busy} onCards={(c) => run(async () => c)} onError={setError} />
          {status.env === 'sandbox' && (
            <button disabled={busy} onClick={() => run(async () => (await plaid.sandboxDemo()).cards)}>
              {busy ? 'Connecting…' : 'Use Sandbox demo cards'}
            </button>
          )}
          <span className="tag">Plaid {status.env}</span>
        </div>
      ) : (
        <MockConnect disabled={busy} linked={new Set(cards.map((c) => c.institution))} onCards={addCards} />
      )}

      {error && <div className="banner error small">{error}</div>}

      {cards.length > 0 && (
        <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Issuer</th>
              <th>Card detected</th>
              <th>Earns into</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((c) => (
              <tr key={`${c.institution}-${c.product}-${c.mask ?? ''}`} className={c.holding ? '' : 'muted'}>
                <td>{c.institution}</td>
                <td>
                  {c.product}
                  {c.mask && <span className="muted"> ···{c.mask}</span>}
                </td>
                <td>
                  {c.holding ? holdingNames[c.holding] : 'Not a program Pointifly models'}
                  {c.note && <div className="muted small">{c.note}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      <div className="row end">
        <button className="primary" disabled={mapped.length === 0} onClick={() => onDone(mapped)}>
          Continue<span className="arrow">→</span>
        </button>
      </div>
    </section>
  )
}

// Real Plaid Link: fetch a link token, open Link, exchange the public token on the backend.
function PlaidLinkButton(props: { disabled: boolean; onCards: (c: LinkedCard[]) => void; onError: (m: string) => void }) {
  const { disabled, onCards, onError } = props
  const [token, setToken] = useState<string | null>(null)

  useEffect(() => {
    plaid
      .linkToken()
      .then((r) => setToken(r.link_token))
      .catch((e: Error) => onError(e.message))
  }, [onError])

  const { open, ready } = usePlaidLink({
    token,
    onSuccess: (publicToken, metadata) => {
      if (!publicToken) return onError('Plaid Link finished without a public token')
      plaid
        .exchange(publicToken, metadata.institution?.name ?? null)
        .then((r) => onCards(r.cards))
        .catch((e: Error) => onError(e.message))
    },
  })

  return (
    <button className="primary" disabled={disabled || !ready} onClick={() => open()}>
      Connect with Plaid
    </button>
  )
}

function MockConnect(props: { disabled: boolean; linked: Set<string>; onCards: (c: LinkedCard[]) => void }) {
  const { disabled, linked, onCards } = props
  const [open, setOpen] = useState(false)
  return (
    <>
      <div className="row">
        <button className="primary" disabled={disabled} onClick={() => setOpen(true)}>
          Connect with Plaid <span className="tag">mock</span>
        </button>
        <span className="muted small">Plaid keys not set on the server: using a mock.</span>
      </div>
      {open && createPortal(
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Select your institution</h3>
            <p className="muted small">Mock of Plaid Link: no real connection is made.</p>
            {MOCK_INSTITUTIONS.map((i) => (
              <button
                key={i.institution}
                className="list-item"
                disabled={linked.has(i.institution)}
                onClick={() => {
                  onCards(i.cards.map((c) => ({ ...c, institution: i.institution })))
                  setOpen(false)
                }}
              >
                {i.institution}
                {linked.has(i.institution) && <span className="tag">linked</span>}
              </button>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
