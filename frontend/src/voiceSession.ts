import { getVoiceSession } from './api'

const SESSION_MAX_AGE_MS = 10 * 60 * 1000 // signed URLs are valid for 15 minutes

// A session URL fetched ahead of time (on the Connect page), so the agent page connects at once.
let prefetched: { at: number; p: Promise<{ signed_url: string }> } | null = null
export function prefetchVoiceSession() {
  if (prefetched && Date.now() - prefetched.at < SESSION_MAX_AGE_MS) return
  const p = getVoiceSession()
  p.catch(() => (prefetched = null))
  prefetched = { at: Date.now(), p }
}
export function takeVoiceSession() {
  const fresh = prefetched && Date.now() - prefetched.at < SESSION_MAX_AGE_MS ? prefetched.p : getVoiceSession()
  prefetched = null // each URL is used once
  return fresh
}
