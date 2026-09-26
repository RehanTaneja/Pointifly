import { useEffect, useState } from 'react'
import { getVisaBenefits, type VisaBenefit } from '../api'

// Travel benefits from Visa Merchant Offers Resource Center, only for card tiers the user holds
// (e.g. Visa Infinite benefits need a Visa Infinite card). Display only: they're card program
// benefits, not flight prices, so they don't change the plan.
export function VisaBenefits({ cardIds }: { cardIds: string[] }) {
  const [offers, setOffers] = useState<VisaBenefit[] | null>(null)
  const key = cardIds.join(',')

  useEffect(() => {
    getVisaBenefits(key ? key.split(',') : [])
      .then((r) => setOffers(r.offers))
      .catch(() => setOffers([]))
  }, [key])

  if (!offers?.length) return null
  return (
    <section className="card">
      <h2>Your Visa travel benefits</h2>
      <div className="benefits">
        {offers.map((o) => (
          <div key={o.id} className="benefit">
            {o.image && (
              <img src={o.image} alt="" loading="lazy" onError={(e) => (e.currentTarget.style.display = 'none')} />
            )}
            <div>
              <strong>{o.title}</strong>
              <div className="small">{o.description}</div>
              <div className="muted small">
                {o.cards.length > 0 && `Eligible cards: ${o.cards.join(', ')}`}
                {o.url && (
                  <>
                    {' · '}
                    <a href={o.url} target="_blank" rel="noreferrer">
                      Details ↗
                    </a>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
