import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiRequest, postJson, type Bill, type LedgerEntry, type PaymentReceipt } from '../api'
import { Button, Card, EmptyState, ErrorState, PageSkeleton, SectionHeading } from '../components/ui'
import { addMoney, formatDate, formatRupees, isPositiveMoney, periodLabel } from '../lib/format'

export function BillsPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [bills, setBills] = useState<Bill[] | null>(null)
  const [ledger, setLedger] = useState<LedgerEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [selectedBillId, setSelectedBillId] = useState<number | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [paymentBusy, setPaymentBusy] = useState(false)
  const [paymentError, setPaymentError] = useState('')
  const [receipt, setReceipt] = useState<PaymentReceipt | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([apiRequest<Bill[]>('/me/bills'), apiRequest<LedgerEntry[]>('/me/ledger')])
      .then(([billData, ledgerData]) => {
        if (alive) {
          setBills(billData)
          setLedger(ledgerData)
        }
      })
      .catch((caught: unknown) => { if (alive) setError(caught instanceof Error ? caught.message : 'Please try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [reload])

  const requestedBillId = selectedBillId === null ? searchParams.get('bill') : String(selectedBillId)
  const selectedBill = bills?.find((bill) => String(bill.id) === requestedBillId) ?? null

  function reloadData() {
    setLoading(true)
    setError('')
    setReload((value) => value + 1)
  }

  async function confirmPayment() {
    if (!selectedBill) return
    setPaymentBusy(true)
    setPaymentError('')
    try {
      const result = await postJson<PaymentReceipt>(`/bills/${selectedBill.id}/pay-test`, {
        amount: addMoney(selectedBill.outstanding, selectedBill.late_fee),
      })
      setReceipt(result)
      setConfirming(false)
      setSelectedBillId(null)
      navigate('/bills', { replace: true })
      reloadData()
    } catch (caught) {
      setPaymentError(caught instanceof Error ? caught.message : 'Payment could not be completed.')
    } finally {
      setPaymentBusy(false)
    }
  }

  if (loading) return <PageSkeleton />
  if (error || !bills || !ledger) {
    return <ErrorState message={error || 'Your billing information is unavailable.'} retry={reloadData} />
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <p className="eyebrow">YOUR ACCOUNT</p>
        <h1>Bills &amp; payments</h1>
        <p className="muted-copy">Keep track of bills and payments for your home.</p>
      </div>

      {receipt && (
        <Card className="receipt-card" aria-live="polite">
          <div className="receipt-card__stamp" aria-hidden="true">✓</div>
          <div className="receipt-card__copy">
            <p className="eyebrow">PAYMENT RECORDED</p>
            <h2>Thank you.</h2>
            <p>Your test payment has been added to your account.</p>
          </div>
          <div className="receipt-grid">
            <div><span>Receipt</span><strong>#{receipt.payment_id}</strong></div>
            <div><span>Bill</span><strong>#{receipt.bill_id}</strong></div>
            <div><span>Amount</span><strong>{formatRupees(receipt.amount)}</strong></div>
            <div><span>Date</span><strong>{formatDate(new Date().toISOString())}</strong></div>
          </div>
          <Button variant="quiet" onClick={() => setReceipt(null)}>Dismiss receipt</Button>
        </Card>
      )}

      <section className="page-section">
        <SectionHeading eyebrow="MONTHLY STATEMENTS" title="Your bills" />
        {bills.length ? (
          <div className="bill-list">
            {bills.map((bill) => {
              const due = addMoney(bill.outstanding, bill.late_fee)
              return (
                <Card className="bill-card" key={bill.id}>
                  <div className="bill-card__heading">
                    <div><span className="bill-card__period">{periodLabel(bill.period)}</span><span className="bill-card__due">Due {formatDate(bill.due_on)}</span></div>
                    <span className={`bill-card__indicator${isPositiveMoney(bill.outstanding) ? ' is-due' : ''}`} aria-hidden="true" />
                  </div>
                  <div className="bill-card__amount-row">
                    <div><span>Outstanding</span><strong>{formatRupees(bill.outstanding)}</strong></div>
                    <div><span>Late fee</span><strong>{formatRupees(bill.late_fee)}</strong></div>
                    <div><span>Total due</span><strong>{formatRupees(due)}</strong></div>
                  </div>
                  <div className="bill-card__footer">
                    <span>{bill.days_overdue > 0 ? `${bill.days_overdue} days overdue` : 'On time'}</span>
                    {isPositiveMoney(bill.outstanding) && (
                      <Button variant="secondary" onClick={() => { setSelectedBillId(bill.id); setPaymentError('') }}>Pay bill</Button>
                    )}
                    {!isPositiveMoney(bill.outstanding) && <span className="paid-label">Paid</span>}
                  </div>
                </Card>
              )
            })}
          </div>
        ) : (
          <Card><EmptyState title="No bills yet">When a bill is issued for your home, it will appear here.</EmptyState></Card>
        )}
      </section>

      <section className="page-section">
        <SectionHeading eyebrow="ACCOUNT ACTIVITY" title="Ledger" />
        {ledger.length ? (
          <Card className="ledger-card">
            {ledger.map((entry) => (
              <div className="ledger-row" key={entry.id}>
                <span className={`ledger-mark ledger-mark--${entry.kind}`} aria-hidden="true">{entry.kind === 'payment' ? '↓' : '↑'}</span>
                <div className="ledger-row__description">
                  <strong>{entry.note || entry.kind.replaceAll('_', ' ')}</strong>
                  <span>{formatDate(entry.entry_date)}</span>
                </div>
                <strong className={entry.amount.startsWith('-') ? 'ledger-credit' : ''}>{formatRupees(entry.amount)}</strong>
              </div>
            ))}
          </Card>
        ) : (
          <Card><EmptyState title="No account activity">Bills and payments will show here as they are added.</EmptyState></Card>
        )}
      </section>

      {confirming && selectedBill && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setConfirming(false) }}>
          <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
            <button className="dialog-close" type="button" aria-label="Close" onClick={() => setConfirming(false)}>×</button>
            <p className="eyebrow">TEST PAYMENT</p>
            <h2 id="confirm-title">Confirm payment</h2>
            <p className="muted-copy">This uses the mock payment flow and records the payment in your account.</p>
            <div className="confirm-total"><span>{periodLabel(selectedBill.period)}</span><strong>{formatRupees(addMoney(selectedBill.outstanding, selectedBill.late_fee))}</strong></div>
            {paymentError && <p className="form-error" role="alert">{paymentError}</p>}
            <Button fullWidth disabled={paymentBusy} onClick={confirmPayment}>
              {paymentBusy ? 'Recording payment…' : 'Confirm test payment'}
            </Button>
            <Button fullWidth variant="quiet" disabled={paymentBusy} onClick={() => setConfirming(false)}>Go back</Button>
          </section>
        </div>
      )}

      {selectedBill && !confirming && !receipt && (
        <div className="payment-action-bar">
          <span>{formatRupees(addMoney(selectedBill.outstanding, selectedBill.late_fee))} due</span>
          <Button onClick={() => setConfirming(true)}>Continue to payment</Button>
        </div>
      )}
    </div>
  )
}
