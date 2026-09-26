import { useState } from 'react'
import { ConversationProvider, useConversation } from '@elevenlabs/react'
import { getVoiceSession } from '../api'

// Handlers the agent's client tools call. They run here in the browser against the local
// backend, so balances, cards and trips stay off ElevenLabs; the agent only gets the summaries.
export type VoiceTools = {
  fill_trip_plan: (sentence: string) => Promise<string>
  run_optimizer: () => Promise<string>
  explain_trip: (trip: string) => Promise<string>
}

type Line = { role: 'user' | 'agent' | 'tool'; text: string }

function Agent({ tools, enabled }: { tools: VoiceTools; enabled: boolean }) {
  const [lines, setLines] = useState<Line[]>([])
  const [error, setError] = useState<string | null>(null)
  const log = (l: Line) => setLines((prev) => [...prev.slice(-5), l])

  const conversation = useConversation({
    // Names must match the agent's tool definitions exactly (case-sensitive).
    clientTools: {
      fill_trip_plan: async ({ sentence }: Record<string, unknown>) => {
        log({ role: 'tool', text: 'Reading your balances and trips…' })
        return tools.fill_trip_plan(String(sentence ?? ''))
      },
      run_optimizer: async () => {
        log({ role: 'tool', text: 'Running the optimizer…' })
        return tools.run_optimizer()
      },
      explain_trip: async ({ trip }: Record<string, unknown>) => tools.explain_trip(String(trip ?? '')),
    },
    onMessage: ({ message, source }) => log({ role: source === 'user' ? 'user' : 'agent', text: message }),
    onError: (message) => setError(String(message)),
  })

  const live = conversation.status === 'connected' || conversation.status === 'connecting'

  const start = async () => {
    setError(null)
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true }) // ask for the mic before connecting
      const { signed_url } = await getVoiceSession()
      conversation.startSession({ signedUrl: signed_url })
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="voice">
      <div className="row between">
        <div className="voice-status small">
          <span className={`voice-dot ${live ? (conversation.isSpeaking ? 'speaking' : 'listening') : ''}`} />
          {conversation.status === 'connecting'
            ? 'Connecting…'
            : live
              ? conversation.isSpeaking
                ? 'Pointifly is speaking'
                : 'Listening'
              : 'Talk to Pointifly'}
        </div>
        {live ? (
          <button onClick={() => conversation.endSession()}>End</button>
        ) : (
          <button className="primary" onClick={start} disabled={!enabled} title={enabled ? '' : 'Voice needs ElevenLabs keys'}>
            🎙 Talk
          </button>
        )}
      </div>
      {error && <div className="banner error small">{error}</div>}
      {lines.length > 0 && (
        <ul className="voice-log small">
          {lines.map((l, i) => (
            <li key={i} className={l.role}>
              {l.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function VoiceAgent(props: { tools: VoiceTools; enabled: boolean }) {
  return (
    <ConversationProvider>
      <Agent {...props} />
    </ConversationProvider>
  )
}
