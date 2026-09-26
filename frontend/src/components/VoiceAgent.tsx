import { useEffect, useRef, useState } from 'react'
import { ConversationProvider, useConversation } from '@elevenlabs/react'
import { getVoiceSession } from '../api'

// Handlers the agent's client tools call. They run here in the browser against the local
// backend, so balances, cards and trips stay off ElevenLabs; the agent only gets the summaries.
// `status` shows a line under the agent (e.g. which Visa API is being called) while a tool runs.
export type VoiceTools = {
  fill_trip_plan: (sentence: string) => Promise<string>
  describe_programs: () => Promise<string>
  run_optimizer: (status: (text: string) => void) => Promise<string>
  explain_trip: (trip: string) => Promise<string>
  pay_cash_leg: (trip: string) => Promise<string>
}

type Line = { role: 'user' | 'agent' | 'tool'; text: string }

// Fired by other parts of the page (e.g. the trip form's "Talk to agent") to start a voice session.
export const TALK_TO_AGENT = 'pointifly:talk'
// Fired with a CustomEvent<string> to tell a live agent about something the user did on screen
// (e.g. switching autopay off), without it being a user message.
export const AGENT_CONTEXT = 'pointifly:agent-context'

type Props = {
  tools: VoiceTools
  enabled: boolean
  // 'stage': the full-screen agent with the speaking circle, started automatically.
  // 'bar': a compact bar above the manual pages. Same instance, so the conversation carries over.
  variant: 'stage' | 'bar'
}

function Agent({ tools, enabled, variant }: Props) {
  const [lines, setLines] = useState<Line[]>([])
  const [error, setError] = useState<string | null>(null)
  const [textMode, setTextMode] = useState(false)
  const [draft, setDraft] = useState('')
  const [flash, setFlash] = useState(false)
  const [working, setWorking] = useState<string | null>(null) // the tool status shown right now
  const panel = useRef<HTMLDivElement>(null)
  const orb = useRef<HTMLDivElement>(null)
  const autoStarted = useRef(false)
  const logEnd = useRef<HTMLLIElement>(null)
  const log = (l: Line) => setLines((prev) => [...prev.slice(-11), l])
  const textModeRef = useRef(false)
  const toolsRef = useRef(tools) // tool calls always use the latest handlers (page state changes mid-call)
  useEffect(() => {
    textModeRef.current = textMode
    toolsRef.current = tools
  })

  // Runs a tool while showing what it's doing; the last status stays in the log.
  const run = async (status: string, fn: () => Promise<string>) => {
    setWorking(status)
    log({ role: 'tool', text: status })
    try {
      return await fn()
    } finally {
      setWorking(null)
    }
  }

  const conversation = useConversation({
    // Names must match the agent's tool definitions exactly (case-sensitive).
    clientTools: {
      fill_trip_plan: ({ sentence }: Record<string, unknown>) =>
        run('Reading your balances and trips…', () => toolsRef.current.fill_trip_plan(String(sentence ?? ''))),
      describe_programs: () => run('Looking up your programs’ official transfer ratios…', () => toolsRef.current.describe_programs()),
      run_optimizer: () =>
        run('Searching live fares and the Visa Foreign Exchange Rates API now…', () =>
          toolsRef.current.run_optimizer((text) => log({ role: 'tool', text })),
        ),
      explain_trip: ({ trip }: Record<string, unknown>) => toolsRef.current.explain_trip(String(trip ?? '')),
      pay_cash_leg: ({ trip }: Record<string, unknown>) =>
        run(`Paying ${String(trip ?? '')} with your Visa via Cybersource now…`, () =>
          toolsRef.current.pay_cash_leg(String(trip ?? '')),
        ),
    },
    onMessage: ({ message, source }) => {
      if (source === 'user' && textModeRef.current) return // already shown when typed
      log({ role: source === 'user' ? 'user' : 'agent', text: message })
    },
    onError: (message) => setError(String(message)),
  })

  // Leaving the agent (e.g. back to Connect) always closes the session, so it stops using credits.
  const conversationRef = useRef(conversation)
  useEffect(() => {
    conversationRef.current = conversation
  })
  useEffect(
    () => () => {
      try {
        void Promise.resolve(conversationRef.current.endSession()).catch(() => undefined)
      } catch {
        // no session open
      }
    },
    [],
  )

  const live = conversation.status === 'connected' || conversation.status === 'connecting'
  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  })

  // Voice first; without a microphone (denied, missing, or a loud room) the same agent, tools and
  // knowledge base run as a text chat.
  const start = async (text: boolean) => {
    setError(null)
    let asText = text
    if (!asText) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach((t) => t.stop()) // permission only; the SDK opens its own stream
      } catch {
        asText = true
        log({ role: 'tool', text: 'No microphone available: type your messages below.' })
      }
    }
    setTextMode(asText)
    try {
      const { signed_url } = await getVoiceSession()
      conversation.startSession({ signedUrl: signed_url, textOnly: asText })
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const startRef = useRef(start)
  useEffect(() => {
    startRef.current = start
  })

  // The agent page starts listening on its own, once.
  useEffect(() => {
    if (variant === 'stage' && enabled && !autoStarted.current && !liveRef.current) {
      autoStarted.current = true
      startRef.current(false)
    }
  }, [variant, enabled])

  useEffect(() => {
    const onTalk = () => {
      panel.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setFlash(true)
      setTimeout(() => setFlash(false), 1000)
      if (enabled && !liveRef.current) startRef.current(false)
    }
    const onContext = (e: Event) => {
      if (liveRef.current) conversation.sendContextualUpdate((e as CustomEvent<string>).detail)
    }
    window.addEventListener(TALK_TO_AGENT, onTalk)
    window.addEventListener(AGENT_CONTEXT, onContext)
    return () => {
      window.removeEventListener(TALK_TO_AGENT, onTalk)
      window.removeEventListener(AGENT_CONTEXT, onContext)
    }
  }, [enabled, conversation])

  // The speaking circle follows the agent's voice (or the user's while listening).
  useEffect(() => {
    if (variant !== 'stage' || !live) return
    let raf = 0
    const tick = () => {
      const level = conversation.isSpeaking ? conversation.getOutputVolume() : conversation.getInputVolume() * 0.6
      orb.current?.style.setProperty('--level', Math.min(1, level * 1.8).toFixed(3))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [variant, live, conversation])

  // Keep the newest line in view (the transcript scrolls inside its box).
  useEffect(() => {
    const box = logEnd.current?.parentElement
    if (box) box.scrollTop = box.scrollHeight
  }, [lines])

  const send = () => {
    const text = draft.trim()
    if (!text) return
    log({ role: 'user', text })
    conversation.sendUserMessage(text)
    setDraft('')
  }

  const state = !live ? 'idle' : conversation.status === 'connecting' ? 'connecting' : working ? 'working' : conversation.isSpeaking ? 'speaking' : 'listening'
  const statusText =
    state === 'idle'
      ? enabled
        ? 'Tap the circle to talk to Pointifly'
        : 'Voice agent unavailable: use Manual mode'
      : state === 'connecting'
        ? 'Connecting…'
        : state === 'working'
          ? working
          : state === 'speaking'
            ? 'Pointifly is speaking'
            : textMode
              ? 'Type your message below'
              : 'Listening…'

  const input = live && (
    <form
      className="row voice-input"
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
    >
      <input
        value={draft}
        placeholder={textMode ? 'Message Pointifly' : 'Or type a message'}
        onChange={(e) => setDraft(e.target.value)}
        disabled={conversation.status !== 'connected'}
      />
    </form>
  )

  const transcript = lines.length > 0 && (
    <ul className="voice-log small" aria-live="polite">
      {lines.map((l, i) => (
        <li key={i} ref={i === lines.length - 1 ? logEnd : undefined} className={l.role}>
          {l.text}
        </li>
      ))}
    </ul>
  )

  if (variant === 'stage') {
    return (
      <div ref={panel} className={`agent-voice ${state}`}>
        <div
          ref={orb}
          className="orb"
          role="img"
          aria-label={statusText ?? ''}
          onClick={() => enabled && !live && start(false)}
        >
          <span className="orb-ring r1" />
          <span className="orb-ring r2" />
          <span className="orb-core" />
        </div>
        <p className="orb-status">{statusText}</p>
        {error && <div className="banner error small">{error}</div>}
        {transcript}
        {input}
      </div>
    )
  }

  return (
    <div ref={panel} className={`voice ${live ? 'live' : ''} ${flash ? 'flash' : ''}`}>
      <div className="row between">
        <div className="voice-status small">
          <span className={`voice-dot ${live ? (conversation.isSpeaking ? 'speaking' : 'listening') : ''}`} />
          {live ? statusText : 'Talk to Pointifly'}
        </div>
        {live ? (
          <button onClick={() => conversation.endSession()}>End</button>
        ) : (
          <div className="row" style={{ marginTop: 0 }}>
            <button disabled={!enabled} onClick={() => start(true)}>
              Type instead
            </button>
            <button className="primary icon" onClick={() => start(false)} disabled={!enabled} title={enabled ? '' : 'Voice needs ElevenLabs keys'}>
              <MicIcon /> Talk
            </button>
          </div>
        )}
      </div>
      {error && <div className="banner error small">{error}</div>}
      {input}
      {transcript}
    </div>
  )
}

export function MicIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  )
}

export function VoiceAgent(props: Props) {
  return (
    <ConversationProvider>
      <Agent {...props} />
    </ConversationProvider>
  )
}
