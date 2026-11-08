import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth/useAuth'
import { Button, Card } from '../components/ui'

export function LoginPage() {
  const { role, requestOtp, signIn } = useAuth()
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState<'phone' | 'otp'>('phone')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (role) return <Navigate to="/" replace />

  async function submitPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await requestOtp(phone)
      setStep('otp')
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not request a code.')
    } finally {
      setBusy(false)
    }
  }

  async function submitOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await signIn(phone, otp)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not verify the code.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-art" aria-hidden="true">
        <div className="sun-disc" />
        <div className="line-house"><span /><span /><span /></div>
        <div className="landscape landscape--back" />
        <div className="landscape landscape--front" />
        <span className="art-caption">A little closer to home</span>
      </div>
      <section className="login-side">
        <NavBrand />
        <div className="login-copy">
          <p className="eyebrow">YOUR COMMUNITY, SIMPLIFIED</p>
          <h1>Welcome<br />home.</h1>
          <p className="login-description">Sign in to take care of the little things that make a place feel like yours.</p>
          <Card className="login-card">
            {step === 'phone' ? (
              <form className="form-stack" onSubmit={submitPhone}>
                <label className="field-label" htmlFor="phone">Mobile number</label>
                <input
                  id="phone"
                  className="text-input"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="e.g. 9000020001"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  pattern="\+?[0-9]{7,15}"
                  required
                />
                <p className="field-hint">Use the number registered with your home.</p>
                {error && <p className="form-error" role="alert">{error}</p>}
                <Button type="submit" fullWidth disabled={busy}>
                  {busy ? 'Sending…' : 'Continue'}
                  <span aria-hidden="true">→</span>
                </Button>
              </form>
            ) : (
              <form className="form-stack" onSubmit={submitOtp}>
                <button className="text-back" type="button" onClick={() => { setStep('phone'); setError('') }}>
                  ← Change number
                </button>
                <label className="field-label" htmlFor="otp">Enter your code</label>
                <input
                  id="otp"
                  className="text-input otp-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="6-digit code"
                  value={otp}
                  onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                />
                <p className="demo-hint">Demo OTP: <strong>123456</strong></p>
                {error && <p className="form-error" role="alert">{error}</p>}
                <Button type="submit" fullWidth disabled={busy || otp.length !== 6}>
                  {busy ? 'Verifying…' : 'Verify and sign in'}
                  <span aria-hidden="true">→</span>
                </Button>
              </form>
            )}
          </Card>
        </div>
        <p className="login-footnote">A calmer way to manage community living.</p>
      </section>
    </main>
  )
}

function NavBrand() {
  return <div className="brand brand--login"><span className="brand__mark">T</span><span>Township</span></div>
}
