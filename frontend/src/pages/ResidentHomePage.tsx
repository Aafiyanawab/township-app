import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiRequest, type Bill, type Complaint } from '../api'
import { Card, EmptyState, ErrorState, PageSkeleton, SectionHeading, StatusPill, Button } from '../components/ui'
import { addMoney, formatDate, formatRupees, isPositiveMoney, periodLabel } from '../lib/format'

const ACTIVE_STATUSES = new Set(['open', 'assigned', 'in_progress'])

export function ResidentHomePage() {
  const [bills, setBills] = useState<Bill[] | null>(null)
  const [complaints, setComplaints] = useState<Complaint[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    let alive = true
    Promise.all([apiRequest<Bill[]>('/me/bills'), apiRequest<Complaint[]>('/me/complaints')])
      .then(([billData, complaintData]) => {
        if (alive) {
          setBills(billData)
          setComplaints(complaintData)
        }
      })
      .catch((caught: unknown) => {
        if (alive) setError(caught instanceof Error ? caught.message : 'Please try again.')
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [reload])

  if (loading) return <PageSkeleton />
  if (error || !bills || !complaints) {
    return <ErrorState message={error || 'Your home information is unavailable.'} retry={() => {
      setLoading(true)
      setError('')
      setReload((n) => n + 1)
    }} />
  }

  const nextBill = bills.find((bill) => isPositiveMoney(bill.outstanding))
  const totalDue = nextBill ? addMoney(nextBill.outstanding, nextBill.late_fee) : '0.00'
  const activeComplaints = complaints.filter((complaint) => ACTIVE_STATUSES.has(complaint.status)).slice(0, 3)

  return (
    <div className="page-stack">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">YOUR COMMUNITY</p>
          <h1>Good to see you.</h1>
          <p className="muted-copy">Home, bills and the things you’ve raised — all together.</p>
        </div>
        <div className="date-stamp">{new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date())}</div>
      </div>

      <Card className="dues-card">
        <div className="dues-card__topline"><span>YOUR DUES</span><span className="dues-card__ornament" aria-hidden="true">✳</span></div>
        {nextBill ? (
          <>
            <p className="dues-card__period">{periodLabel(nextBill.period)}</p>
            <p className="dues-card__amount">{formatRupees(totalDue)}</p>
            <p className="dues-card__caption">Outstanding amount with late fee</p>
            <div className="dues-facts">
              <div><span>Due date</span><strong>{formatDate(nextBill.due_on)}</strong></div>
              <div><span>Days overdue</span><strong>{nextBill.days_overdue}</strong></div>
              <div><span>Late fee</span><strong>{formatRupees(nextBill.late_fee)}</strong></div>
            </div>
            <Button className="dues-card__button" variant="secondary" onClick={() => navigate(`/bills?bill=${nextBill.id}`)}>
              Pay this bill <span aria-hidden="true">→</span>
            </Button>
          </>
        ) : (
          <div className="dues-clear">
            <h2>You’re all caught up.</h2>
            <p>There are no outstanding bills right now.</p>
            <Link to="/bills">View your bills <span aria-hidden="true">→</span></Link>
          </div>
        )}
      </Card>

      <section className="page-section">
        <SectionHeading eyebrow="HERE TO HELP" title="Open complaints" action={<Link className="text-link" to="/complaints">See all <span aria-hidden="true">→</span></Link>} />
        {activeComplaints.length ? (
          <div className="compact-list">
            {activeComplaints.map((complaint) => (
              <Link to="/complaints" className="complaint-preview" key={complaint.id}>
                <span className="complaint-preview__icon" aria-hidden="true">↗</span>
                <span className="complaint-preview__body">
                  <strong>{complaint.category}</strong>
                  <span>{complaint.text}</span>
                </span>
                <StatusPill status={complaint.status} />
              </Link>
            ))}
          </div>
        ) : (
          <Card><EmptyState title="Nothing needs attention">When you raise a complaint, you can follow its progress here.</EmptyState></Card>
        )}
      </section>

      <section className="home-note">
        <span className="home-note__icon" aria-hidden="true">✳</span>
        <p>Need a hand with something around home?</p>
        <Button variant="quiet" onClick={() => navigate('/complaints')}>Raise a complaint <span aria-hidden="true">→</span></Button>
      </section>
    </div>
  )
}
