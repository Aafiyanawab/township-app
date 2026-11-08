import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest, postJson, type Complaint } from '../api'
import { Button, Card, EmptyState, ErrorState, PageSkeleton, SectionHeading, StatusPill } from '../components/ui'
import { formatDateTime } from '../lib/format'

export function ComplaintsPage() {
  const [complaints, setComplaints] = useState<Complaint[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reload, setReload] = useState(0)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [actionId, setActionId] = useState<number | null>(null)
  const [actionError, setActionError] = useState('')
  const [formError, setFormError] = useState('')
  const [ratings, setRatings] = useState<Record<number, number>>({})

  useEffect(() => {
    let alive = true
    apiRequest<Complaint[]>('/me/complaints')
      .then((data) => { if (alive) setComplaints(data) })
      .catch((caught: unknown) => { if (alive) setLoadError(caught instanceof Error ? caught.message : 'Please try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [reload])

  function reloadComplaints() {
    setLoading(true)
    setLoadError('')
    setReload((value) => value + 1)
  }

  async function createComplaint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (text.trim().length < 5) {
      setFormError('Please add a little more detail (at least 5 characters).')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      await postJson<Complaint>('/complaints', { text })
      setText('')
      reloadComplaints()
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : 'Your complaint could not be sent.')
    } finally {
      setSaving(false)
    }
  }

  async function actOnComplaint(id: number, action: 'rate' | 'reopen', rating?: number) {
    setActionId(id)
    setActionError('')
    try {
      await postJson<Complaint>(`/complaints/${id}/${action}`, action === 'rate' ? { rating } : {})
      reloadComplaints()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'The request could not be completed.')
    } finally {
      setActionId(null)
    }
  }

  if (loading) return <PageSkeleton />
  if (loadError || !complaints) {
    return <ErrorState message={loadError || 'Your complaints are unavailable.'} retry={reloadComplaints} />
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <p className="eyebrow">WE’RE HERE TO HELP</p>
        <h1>Complaints</h1>
        <p className="muted-copy">Tell us what needs attention. You can follow every update here.</p>
      </div>

      <Card className="raise-card">
        <SectionHeading eyebrow="LET US KNOW" title="Raise a complaint" />
        <form className="form-stack" onSubmit={createComplaint}>
          <label className="field-label" htmlFor="complaint-text">What’s happening?</label>
          <textarea
            id="complaint-text"
            className="text-input text-area"
            rows={4}
            maxLength={1000}
            placeholder="Share a few details so the team can help…"
            value={text}
            onChange={(event) => { setText(event.target.value); setFormError('') }}
            required
          />
          <div className="textarea-footer"><span>5–1000 characters</span><span>{text.length}/1000</span></div>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <Button type="submit" disabled={saving || text.trim().length < 5}>
            {saving ? 'Sending…' : 'Send complaint'} <span aria-hidden="true">→</span>
          </Button>
        </form>
      </Card>

      <section className="page-section">
        <SectionHeading eyebrow="YOUR UPDATES" title="Your complaints" />
        {actionError && <p className="form-error action-error" role="alert">{actionError}</p>}
        {complaints.length ? (
          <div className="complaint-list">
            {complaints.map((complaint) => (
              <Card className="complaint-card" key={complaint.id}>
                <div className="complaint-card__top">
                  <div><span className="complaint-card__category">{complaint.category}</span><span className="complaint-card__date">Raised {formatDateTime(complaint.created_at)}</span></div>
                  <StatusPill status={complaint.status} />
                </div>
                <p className="complaint-card__text">{complaint.text}</p>
                <div className="complaint-meta"><span className={`urgency-dot urgency-dot--${complaint.urgency}`} />{complaint.urgency} priority</div>
                <div className="timeline">
                  {complaint.events.map((event) => (
                    <div className="timeline__item" key={event.id}>
                      <span className="timeline__dot" />
                      <div><strong>{event.kind.replaceAll('_', ' ')}</strong>{event.detail && <p>{event.detail}</p>}<time>{formatDateTime(event.at)}</time></div>
                    </div>
                  ))}
                  {!complaint.events.length && <p className="muted-copy">Updates will appear here.</p>}
                </div>
                {complaint.status === 'resolved' && (
                  <div className="complaint-actions">
                    <label className="rating-field" htmlFor={`rating-${complaint.id}`}>
                      <span>How did we do?</span>
                      <select
                        id={`rating-${complaint.id}`}
                        value={ratings[complaint.id] ?? 5}
                        onChange={(event) => setRatings((value) => ({ ...value, [complaint.id]: Number(event.target.value) }))}
                        className="select-input"
                        aria-label="Choose a rating from 1 to 5"
                      >
                        {[5, 4, 3, 2, 1].map((rating) => <option key={rating} value={rating}>{rating} {rating === 1 ? 'star' : 'stars'}</option>)}
                      </select>
                    </label>
                    <Button disabled={actionId === complaint.id} onClick={() => void actOnComplaint(complaint.id, 'rate', ratings[complaint.id] ?? 5)}>Rate &amp; close</Button>
                    <Button variant="secondary" disabled={actionId === complaint.id} onClick={() => void actOnComplaint(complaint.id, 'reopen')}>Reopen</Button>
                  </div>
                )}
              </Card>
            ))}
          </div>
        ) : (
          <Card><EmptyState title="No complaints yet">If something needs attention, you can let the help desk know here.</EmptyState></Card>
        )}
      </section>
    </div>
  )
}
