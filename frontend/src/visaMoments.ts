// "Visa moments": short labels that appear on screen whenever Pointifly uses a Visa service
// (Foreign Exchange Rates API, Cybersource, Visa card earning, card benefits), then fade away.
// A moment with the same id replaces the earlier one (e.g. "working" becomes "done").
export type VisaMoment = {
  id: string
  kind: 'working' | 'done' | 'held' // held: a guardrail stopped a payment
  title: string
  detail?: string
  ttl?: number // ms on screen once done or held (working stays until replaced)
}

export const VISA_MOMENT = 'pointifly:visa-moment'

export function visaMoment(m: VisaMoment, delayMs = 0) {
  const fire = () => window.dispatchEvent(new CustomEvent<VisaMoment>(VISA_MOMENT, { detail: m }))
  if (delayMs > 0) window.setTimeout(fire, delayMs)
  else fire()
}
