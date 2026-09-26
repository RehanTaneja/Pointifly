// A jet takeoff for the opening splash, synthesized with the Web Audio API (no audio file, no
// licence, no API credits): an engine rumble, a roar that climbs as it accelerates, a turbine
// whine spooling up, a left-to-right pass and a fade as it flies away.
// Browsers only allow sound after the page has had a click or key press (or when autoplay is
// allowed for the site): play() resolves false when the sound was blocked.

const DURATION = 3.6 // seconds
let playedAt = 0 // StrictMode runs effects twice in development: never play twice in a row

type AudioContextClass = typeof AudioContext

export async function playTakeoff(): Promise<boolean> {
  if (Date.now() - playedAt < 4000) return true
  const Ctx: AudioContextClass | undefined =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextClass }).webkitAudioContext
  if (!Ctx) return false
  const ctx = new Ctx()
  if (ctx.state !== 'running') {
    // resume() can stay pending until a user gesture: don't wait on it for long
    await Promise.race([ctx.resume().catch(() => undefined), new Promise((r) => setTimeout(r, 250))])
  }
  if (ctx.state !== 'running') {
    void ctx.close()
    return false
  }
  playedAt = Date.now()

  const t0 = ctx.currentTime + 0.03
  const end = t0 + DURATION

  // Brown noise: the raw material for the rumble and the roar.
  const len = Math.floor(ctx.sampleRate * (DURATION + 0.2))
  const buffer = ctx.createBuffer(1, len, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  let last = 0
  for (let i = 0; i < len; i++) {
    last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02
    data[i] = last * 3.5
  }

  const master = ctx.createGain()
  master.gain.setValueAtTime(0.0001, t0)
  master.gain.exponentialRampToValueAtTime(0.32, t0 + 1.1) // spool-up
  master.gain.exponentialRampToValueAtTime(0.5, t0 + 2.1) // full thrust, passing by
  master.gain.exponentialRampToValueAtTime(0.0001, end) // flying away
  const pan = ctx.createStereoPanner ? ctx.createStereoPanner() : null
  if (pan) {
    pan.pan.setValueAtTime(-0.6, t0)
    pan.pan.linearRampToValueAtTime(0.7, end)
    master.connect(pan).connect(ctx.destination)
  } else {
    master.connect(ctx.destination)
  }

  // Roar: noise through a band that sweeps up with speed, then drops as it recedes.
  const roar = ctx.createBufferSource()
  roar.buffer = buffer
  const band = ctx.createBiquadFilter()
  band.type = 'bandpass'
  band.Q.value = 0.7
  band.frequency.setValueAtTime(220, t0)
  band.frequency.exponentialRampToValueAtTime(1500, t0 + DURATION * 0.65)
  band.frequency.exponentialRampToValueAtTime(600, end)
  roar.connect(band).connect(master)

  // Rumble: the low end of the engines.
  const rumble = ctx.createBufferSource()
  rumble.buffer = buffer
  const low = ctx.createBiquadFilter()
  low.type = 'lowpass'
  low.frequency.value = 140
  const rumbleGain = ctx.createGain()
  rumbleGain.gain.value = 0.9
  rumble.connect(low).connect(rumbleGain).connect(master)

  // Whine: the turbines spooling up, kept soft.
  const whine = ctx.createOscillator()
  whine.type = 'sawtooth'
  whine.frequency.setValueAtTime(380, t0)
  whine.frequency.exponentialRampToValueAtTime(1800, t0 + DURATION * 0.7)
  whine.frequency.exponentialRampToValueAtTime(1300, end) // a touch of doppler as it passes
  const whineTone = ctx.createBiquadFilter()
  whineTone.type = 'lowpass'
  whineTone.frequency.value = 2400
  const whineGain = ctx.createGain()
  whineGain.gain.value = 0.018
  whine.connect(whineTone).connect(whineGain).connect(master)

  for (const node of [roar, rumble, whine]) {
    node.start(t0)
    node.stop(end + 0.05)
  }
  window.setTimeout(() => void ctx.close(), (DURATION + 0.4) * 1000)
  return true
}
