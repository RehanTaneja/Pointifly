import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  agentPay,
  fmtPts,
  fmtUsd,
  getAgentStatus,
  getVisaBenefits,
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
import { BuiltOnVisa } from './components/VisaImpact'
import { VisaMoments } from './components/VisaMoments'
import { AGENT_CONTEXT, VoiceAgent, type VoiceTools } from './components/VoiceAgent'
import { prefetchVoiceSession } from './voiceSession'
import { visaMoment } from './visaMoments'
import { explainTrip, planSummary, programsSummary } from './summaries'

type Step = 'connect' | 'agent' | 'manual' | 'loading' | 'dashboard'

const MIN_WORKING_MS = 1200 // a Visa call's "working" label stays long enough to be seen

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
  const lastError = useRef<string | null>(null) // why the last optimize failed, for the agent to say
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

  // While the user connects cards, get the agent's session URL ready so its page greets at once.
  useEffect(() => {
    if (voiceReady && step === 'connect') prefetchVoiceSession()
  }, [voiceReady, step])

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
      lastError.current = (e as Error).message
      setError(lastError.current)
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
      visaMoment({ id: 'fx', kind: 'working', title: 'Foreign Exchange Rates API', detail: 'Converting local fares for your trips…' })
      const began = Date.now()
      const r = await runOptimize(inputs.balances, inputs.trips, stepRef.current === 'agent')
      const hold = Math.max(0, MIN_WORKING_MS - (Date.now() - began)) // saved fares are instant: keep "working" visible
      if (!r) {
        visaMoment({ id: 'fx', kind: 'dismiss', title: '' }) // not a Visa failure: don't show it as one
        return `The optimizer could not run: ${lastError.current ?? 'check the trips on screen'}. Tell the user this reason plainly.`
      }
      const fx = [...new Set(r.portfolio.allocations.flatMap((a) => (a.local_fx?.currency ? [a.local_fx.currency] : [])))]
      if (fx.length) status(`Visa Foreign Exchange Rates API: USD → ${fx.join(', ')} (Sandbox sample rates)`)
      // What Visa did in this plan, one label at a time while the agent talks it through.
      visaMoment(
        {
          id: 'fx',
          kind: 'done',
          title: 'Foreign Exchange Rates API',
          detail: fx.length ? `USD → ${fx.join(', ')} · Sandbox sample rates` : 'All fares already in US dollars',
        },
        hold,
      )
      const cash = r.portfolio.allocations.filter((a) => a.method === 'cash' && a.payment_card)
      if (cash.length) {
        const cardNames = [...new Set(cash.map((a) => a.payment_card!.name))]
        const earned = cash.reduce((sum, a) => sum + a.payment_card!.earned_points, 0)
        const total = cash.reduce((sum, a) => sum + a.cash_usd, 0)
        visaMoment({ id: 'card', kind: 'done', title: 'Best Visa card for each cash trip', detail: cardNames.join(', ') }, hold + 1100)
        visaMoment(
          { id: 'earn', kind: 'done', title: `+${fmtPts(earned)} points earned with Visa`, detail: `${cash.length} cash trip${cash.length === 1 ? '' : 's'} · ${fmtUsd(total)} on your Visa` },
          hold + 2200,
        )
      }
      getVisaBenefits(cardIds)
        .then(({ offers }) => {
          if (offers.length)
            visaMoment({ id: 'benefits', kind: 'done', title: `${offers.length} Visa travel benefit${offers.length === 1 ? '' : 's'} for your cards`, detail: offers[0].title }, hold + 3300)
        })
        .catch(() => undefined)
      const mandate = r.plan_id ? await getAgentStatus(r.plan_id).catch(() => null) : null
      return planSummary(r, names, mandate)
    },
    explain_trip: async (trip) => explainTrip(resultRef.current, trip),
    // Server-enforced: autopay switch, spending limits, plan's amount and card, no double charge.
    pay_cash_leg: async (trip) => {
      const planId = resultRef.current?.plan_id
      if (!planId) return 'No plan yet: run the optimizer first.'
      const id = `pay-${trip.toLowerCase()}`
      visaMoment({ id, kind: 'working', title: 'Cybersource payment', detail: `Sending ${trip} to Visa's gateway…` })
      const began = Date.now()
      const r = await agentPay(planId, trip).catch((e: Error) => ({ ok: false, message: e.message }) as PayResult)
      await new Promise((done) => setTimeout(done, Math.max(0, MIN_WORKING_MS - (Date.now() - began))))
      const label = resultRef.current?.portfolio.allocations.find((a) => a.trip_id === r.trip_id)?.trip_label ?? trip
      if (r.decision === 'paid')
        visaMoment({ id, kind: 'done', title: 'Paid through Cybersource', detail: `${label} · ${fmtUsd(r.amount ?? 0)} · ${r.card} · +${fmtPts(r.earned_points ?? 0)} pts` })
      else if (r.decision === 'skipped') visaMoment({ id, kind: 'done', title: 'Already paid with Visa', detail: label })
      else {
        const why = r.message.replace(/^Blocked: /, '')
        visaMoment({ id, kind: 'held', title: 'Payment held by your guardrails', detail: why.charAt(0).toUpperCase() + why.slice(1) })
      }
      window.dispatchEvent(new CustomEvent<PayResult>(PAYMENTS_CHANGED, { detail: r }))
      return r.message
    },
  }

  // Development only: lets the agent's tools be exercised without a voice session (saves credits).
  useEffect(() => {
    if (import.meta.env.DEV) (window as unknown as { __pointiflyTools?: VoiceTools }).__pointiflyTools = voiceTools
  })

  const onAgentPage = step === 'agent'
  return (
    <>
      {intro && <Splash onDone={endIntro} />}
      <main className={onAgentPage ? 'agent-mode' : ''}>
        <header className="app-header">
          <Logo />
          <BuiltOnVisa />
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
      <VisaMoments />
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
