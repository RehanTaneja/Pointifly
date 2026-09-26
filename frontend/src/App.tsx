import { useEffect, useMemo, useRef, useState } from 'react'
import {
  agentPay,
  getAiStatus,
  PAYMENTS_CHANGED,
  type PayResult,
  getDataset,
  holdingNames,
  optimize,
  type Balance,
  type Dataset,
  type OptimizeResponse,
  type Trip,
} from './api'
import { ConnectStep, type LinkedCard } from './components/ConnectStep'
import { Dashboard } from './components/Dashboard'
import { InputStep, type InputApi } from './components/InputStep'
import { VoiceAgent, type VoiceTools } from './components/VoiceAgent'
import { explainTrip, planSummary } from './summaries'

type Step = 'connect' | 'input' | 'loading' | 'dashboard'

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('connect')
  const [cards, setCards] = useState<LinkedCard[]>([])
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [voiceReady, setVoiceReady] = useState(false)
  const inputApi = useRef<InputApi | null>(null)
  const lastInputs = useRef<{ balances: Balance[]; trips: Trip[] } | null>(null)
  const resultRef = useRef<OptimizeResponse | null>(null)

  useEffect(() => {
    getDataset()
      .then(setDataset)
      .catch((e: Error) => setError(`${e.message}. Is the API running on :8000?`))
    getAiStatus()
      .then((s) => setVoiceReady(s.voice))
      .catch(() => setVoiceReady(false))
  }, [])

  const names = useMemo(() => (dataset ? holdingNames(dataset) : {}), [dataset])

  const runOptimize = async (balances: Balance[], trips: Trip[]): Promise<OptimizeResponse | null> => {
    setStep('loading')
    lastInputs.current = { balances, trips }
    try {
      setError(null)
      const r = await optimize(balances, trips, cards.flatMap((c) => (c.product_id ? [c.product_id] : [])))
      setResult(r)
      resultRef.current = r
      setStep('dashboard')
      return r
    } catch (e) {
      setError((e as Error).message)
      setStep('input')
      return null
    }
  }

  // The voice agent's client tools: they drive the same UI a user would.
  const waitForInput = async () => {
    for (let i = 0; i < 40 && !inputApi.current; i++) await new Promise((r) => setTimeout(r, 50))
    return inputApi.current
  }
  const voiceTools: VoiceTools = {
    fill_trip_plan: async (sentence) => {
      if (step === 'connect') return 'Ask the user to connect their cards first.'
      if (step === 'dashboard') setStep('input')
      const api = await waitForInput()
      return api ? api.fill(sentence) : 'The trip form is not open yet.'
    },
    run_optimizer: async () => {
      const inputs = inputApi.current?.current() ?? lastInputs.current
      if (!inputs?.trips.length) return 'There are no trips yet: ask for the trips first.'
      const r = await runOptimize(inputs.balances, inputs.trips)
      return r ? planSummary(r, names) : 'The optimizer could not run: check the trips on screen.'
    },
    explain_trip: async (trip) => explainTrip(resultRef.current, trip),
    // Server-enforced: autopay toggle, spending limits, plan's amount and card, no double charge.
    pay_cash_leg: async (trip) => {
      const planId = resultRef.current?.plan_id
      if (!planId) return 'No plan yet: run the optimizer first.'
      const r = await agentPay(planId, trip).catch((e: Error) => ({ ok: false, message: e.message }) as PayResult)
      window.dispatchEvent(new CustomEvent<PayResult>(PAYMENTS_CHANGED, { detail: r }))
      return r.message
    },
  }

  return (
    <main>
      <header>
        <h1>Pointifly</h1>
        <p className="muted">Award tools optimize one flight. Pointifly optimizes your whole year of points.</p>
      </header>

      {error && <div className="banner error">{error}</div>}

      {dataset && step !== 'connect' && <VoiceAgent tools={voiceTools} enabled={voiceReady} />}

      {!dataset && !error && <p className="muted">Loading…</p>}

      {dataset && step === 'connect' && (
        <ConnectStep
          holdingNames={names}
          onDone={(c) => {
            setCards(c)
            setStep('input')
          }}
        />
      )}

      {/* Stays mounted while loading so edits survive an error and the return to this step. */}
      {dataset && (step === 'input' || step === 'loading') && (
        <div hidden={step === 'loading'}>
          <InputStep
            dataset={dataset}
            holdingNames={names}
            linkedHoldings={[...new Set(cards.flatMap((c) => (c.holding ? [c.holding] : [])))]}
            onOptimize={runOptimize}
            registerApi={(api) => (inputApi.current = api)}
          />
        </div>
      )}

      {step === 'loading' && (
        <section className="card center">
          <div className="spinner" />
          <p className="muted">Optimizing across all trips…</p>
        </section>
      )}

      {step === 'dashboard' && result && (
        <Dashboard
          result={result}
          holdingNames={names}
          currencies={dataset?.currencies ?? []}
          cardIds={cards.flatMap((c) => (c.product_id ? [c.product_id] : []))}
          onReset={() => {
            setResult(null)
            setCards([])
            setStep('connect')
          }}
        />
      )}
    </main>
  )
}
