import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  agentPay,
  getAgentStatus,
  getAiStatus,
  PAYMENTS_CHANGED,
  setMandate,
  type PayResult,
  getDataset,
  holdingNames,
  optimize,
  type Balance,
  type Dataset,
  type OptimizeResponse,
  type Trip,
} from './api'
import { Logo, PlaneLoader, Splash } from './components/Brand'
import { ConnectStep, type LinkedCard } from './components/ConnectStep'
import { Dashboard } from './components/Dashboard'
import { InputStep, type InputApi } from './components/InputStep'
import { PaymentToast } from './components/PaymentToast'
import { PlanPanel } from './components/PlanPanel'
import { AGENT_CONTEXT, VoiceAgent, type VoiceTools } from './components/VoiceAgent'
import { explainTrip, planSummary, programsSummary } from './summaries'

type Step = 'connect' | 'agent' | 'manual' | 'loading' | 'dashboard'

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('connect')
  const [cards, setCards] = useState<LinkedCard[]>([])
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [voiceReady, setVoiceReady] = useState(false)
  const [intro, setIntro] = useState(true)
  const [autopay, setAutopay] = useState(true) // autonomous payments: on by default, the user's switch
  const [origin, setOrigin] = useState<'agent' | 'manual'>('agent') // where the dashboard's Back goes
  const endIntro = useCallback(() => setIntro(false), [])
  const inputApi = useRef<InputApi | null>(null)
  const lastInputs = useRef<{ balances: Balance[]; trips: Trip[] } | null>(null)
  const resultRef = useRef<OptimizeResponse | null>(null)
  const stepRef = useRef(step)
  const autopayRef = useRef(autopay)
  useEffect(() => {
    stepRef.current = step
    autopayRef.current = autopay
  })

  useEffect(() => {
    getDataset()
      .then(setDataset)
      .catch((e: Error) => setError(`${e.message}. Is the API running on :8000?`))
    getAiStatus()
      .then((s) => setVoiceReady(s.voice))
      .catch(() => setVoiceReady(false))
  }, [])

  const names = useMemo(() => (dataset ? holdingNames(dataset) : {}), [dataset])
  const cardIds = useMemo(() => cards.flatMap((c) => (c.product_id ? [c.product_id] : [])), [cards])
  const linkedHoldings = useMemo(() => [...new Set(cards.flatMap((c) => (c.holding ? [c.holding] : [])))], [cards])

  // From the manual page: loader, then the dashboard. From the agent page: the plan appears in place.
  const runOptimize = async (balances: Balance[], trips: Trip[], inPlace = false): Promise<OptimizeResponse | null> => {
    lastInputs.current = { balances, trips }
    if (!inPlace) setStep('loading')
    try {
      setError(null)
      const r = await optimize(balances, trips, cardIds, autopayRef.current)
      setResult(r)
      resultRef.current = r
      if (!inPlace) {
        setOrigin('manual')
        setStep('dashboard')
      }
      return r
    } catch (e) {
      setError((e as Error).message)
      if (!inPlace) setStep('manual')
      return null
    }
  }

  // One switch for the agent page, the dashboard and the server's mandate; the agent is told too.
  const changeAutopay = async (on: boolean) => {
    setAutopay(on)
    autopayRef.current = on
    const planId = resultRef.current?.plan_id
    if (planId) {
      try {
        const s = await getAgentStatus(planId)
        await setMandate(planId, on, s.max_per_payment, s.max_total)
      } catch {
        // the dashboard's audit log shows the server's state either way
      }
      window.dispatchEvent(new Event(PAYMENTS_CHANGED))
    }
    window.dispatchEvent(
      new CustomEvent(AGENT_CONTEXT, {
        detail: on
          ? 'The user switched autonomous payments ON: after one confirmation you may pay the cash trips.'
          : 'The user switched autonomous payments OFF: do not call pay_cash_leg; tell them to tap Pay with Visa.',
      }),
    )
  }

  // The voice agent's client tools: they drive the same state a user would.
  const waitForInput = async () => {
    for (let i = 0; i < 40 && !inputApi.current; i++) await new Promise((r) => setTimeout(r, 50))
    return inputApi.current
  }
  const currentInputs = () => inputApi.current?.current() ?? lastInputs.current
  const voiceTools: VoiceTools = {
    fill_trip_plan: async (sentence) => {
      if (stepRef.current === 'connect') return 'Ask the user to connect their cards first.'
      if (stepRef.current === 'dashboard') setStep(origin)
      const api = await waitForInput()
      return api ? api.fill(sentence) : 'The trip form is not open yet.'
    },
    describe_programs: async () => {
      const inputs = currentInputs()
      return dataset && inputs ? programsSummary(dataset, inputs.balances, names) : 'No balances yet: ask for them first.'
    },
    run_optimizer: async (status) => {
      const inputs = currentInputs()
      if (!inputs?.trips.length) return 'There are no trips yet: ask for the trips first.'
      const r = await runOptimize(inputs.balances, inputs.trips, stepRef.current === 'agent')
      if (!r) return 'The optimizer could not run: check the trips on screen.'
      const fx = [...new Set(r.portfolio.allocations.flatMap((a) => (a.local_fx?.currency ? [a.local_fx.currency] : [])))]
      if (fx.length) status(`Visa Foreign Exchange Rates API: USD → ${fx.join(', ')} (Sandbox sample rates)`)
      const mandate = r.plan_id ? await getAgentStatus(r.plan_id).catch(() => null) : null
      return planSummary(r, names, mandate)
    },
    explain_trip: async (trip) => explainTrip(resultRef.current, trip),
    // Server-enforced: autopay switch, spending limits, plan's amount and card, no double charge.
    pay_cash_leg: async (trip) => {
      const planId = resultRef.current?.plan_id
      if (!planId) return 'No plan yet: run the optimizer first.'
      const r = await agentPay(planId, trip).catch((e: Error) => ({ ok: false, message: e.message }) as PayResult)
      window.dispatchEvent(new CustomEvent<PayResult>(PAYMENTS_CHANGED, { detail: r }))
      return r.message
    },
  }

  const onAgentPage = step === 'agent'
  return (
    <>
      {intro && <Splash onDone={endIntro} />}
      <main className={onAgentPage ? 'agent-mode' : ''}>
        <header>
          <Logo />
        </header>

        {error && <div className="banner error">{error}</div>}

        {!dataset && !error && <p className="muted">Loading…</p>}

        {dataset && step === 'connect' && (
          <ConnectStep
            holdingNames={names}
            onDone={(c) => {
              setCards(c)
              setResult(null)
              resultRef.current = null
              setStep('agent')
            }}
          />
        )}

        {/* One agent instance for every page after Connect, so a conversation carries over. */}
        {dataset && step !== 'connect' && (
          <div className={onAgentPage ? 'agent-stage' : 'voice-slot'}>
            {onAgentPage ? (
              <div className="agent-top">
                <button className="icon-button" aria-label="Back to connecting cards" onClick={() => setStep('connect')}>
                  <BackIcon />
                </button>
                <label className="switch small">
                  <input type="checkbox" checked={autopay} onChange={(e) => changeAutopay(e.target.checked)} />
                  <span>Autonomous payments</span>
                </label>
              </div>
            ) : null}
            <VoiceAgent tools={voiceTools} enabled={voiceReady} variant={onAgentPage ? 'stage' : 'bar'} />
            {onAgentPage ? (
              <>
                {result && (
                  <PlanPanel
                    result={result}
                    holdingNames={names}
                    autopay={autopay}
                    onDetails={() => {
                      setOrigin('agent')
                      setStep('dashboard')
                    }}
                  />
                )}
                <div className="agent-bottom">
                  <button onClick={() => setStep('manual')}>Manual mode</button>
                </div>
              </>
            ) : null}
          </div>
        )}

        {/* Mounted from the agent page on (hidden there), so what the agent fills in shows in Manual mode. */}
        {dataset && step !== 'connect' && (
          <div hidden={step !== 'manual'}>
            <button className="link back-link" onClick={() => setStep('agent')}>
              ← Back to the agent
            </button>
            <InputStep
              dataset={dataset}
              holdingNames={names}
              linkedHoldings={linkedHoldings}
              onOptimize={runOptimize}
              registerApi={(api) => (inputApi.current = api)}
              voiceEnabled={voiceReady}
            />
          </div>
        )}

        {step === 'loading' && <PlaneLoader label="Optimizing across all trips…" />}

        {step === 'dashboard' && result && (
          <Dashboard
            result={result}
            holdingNames={names}
            currencies={dataset?.currencies ?? []}
            cardIds={cardIds}
            onBack={() => setStep(origin)}
            onAutopayChange={changeAutopay}
            onReset={() => {
              setResult(null)
              resultRef.current = null
              setCards([])
              setStep('connect')
            }}
          />
        )}
      </main>
      <PaymentToast result={result} />
    </>
  )
}

function BackIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  )
}
