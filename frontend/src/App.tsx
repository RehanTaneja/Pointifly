import { useEffect, useMemo, useState } from 'react'
import { getDataset, holdingNames, optimize, type Balance, type Dataset, type OptimizeResponse, type Trip } from './api'
import { ConnectStep, type LinkedCard } from './components/ConnectStep'
import { Dashboard } from './components/Dashboard'
import { InputStep } from './components/InputStep'

type Step = 'connect' | 'input' | 'loading' | 'dashboard'

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('connect')
  const [cards, setCards] = useState<LinkedCard[]>([])
  const [result, setResult] = useState<OptimizeResponse | null>(null)

  useEffect(() => {
    getDataset()
      .then(setDataset)
      .catch((e: Error) => setError(`${e.message}. Is the API running on :8000?`))
  }, [])

  const names = useMemo(() => (dataset ? holdingNames(dataset) : {}), [dataset])

  const runOptimize = async (balances: Balance[], trips: Trip[]) => {
    setStep('loading')
    try {
      setError(null)
      setResult(await optimize(balances, trips, cards.flatMap((c) => (c.product_id ? [c.product_id] : []))))
      setStep('dashboard')
    } catch (e) {
      setError((e as Error).message)
      setStep('input')
    }
  }

  return (
    <main>
      <header>
        <h1>Pointifly</h1>
        <p className="muted">Award tools optimize one flight. Pointifly optimizes your whole year of points.</p>
      </header>

      {error && <div className="banner error">{error}</div>}

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
