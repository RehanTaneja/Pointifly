import { useEffect, useRef, useState } from 'react'

// Numbers ease up from zero when they first appear.
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const [reduced] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)
  const [shown, setShown] = useState(0)
  const raf = useRef(0)
  useEffect(() => {
    if (reduced) return
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900)
      setShown(value * (1 - Math.pow(1 - t, 3)))
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value, reduced])
  return <>{format(Math.round(reduced ? value : shown))}</>
}
