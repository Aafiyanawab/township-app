import { useEffect, useState } from 'react'
import { apiRequest, postJson, type HelpdeskComplaint } from '../api'
import { useAuth } from '../auth/useAuth'
import { StaffShell } from '../components/StaffShell'
import { Button, Card, EmptyState, ErrorState, PageSkeleton, StatusPill } from '../components/ui'
import { formatDateTime } from '../lib/format'

const CATEGORIES = ['plumbing', 'electrical', 'lift', 'cleaning', 'security', 'parking', 'noise', 'lighting', 'safety', 'general']
const TRANSITIONS: Record<string, string[]> = {
  open: ['assigned', 'in_progress', 'resolved'],
  assigned: ['in_progress', 'resolved'],
  in_progress: ['resolved', 'assigned'],
  resolved: ['closed', 'open'],
  closed: [],
}

function overdueLabel(value: string | null, now: number) {
  if (!value) return ''
  if (!now) return 'Overdue'
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`
  const minutes = Math.max(0, Math.floor((now - new Date(timestamp).getTime()) / 60_000))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const remainder = minutes % 60
  if (days) return `Overdue ${days}d ${hours}h`
  if (hours) return `Overdue ${hours}h ${remainder}m`
  return `Overdue ${remainder}m`
}

export function HelpdeskPage() {
  const { userId } = useAuth()
  const [complaints, setComplaints] = useState<HelpdeskComplaint[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [reload, setReload] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState('active')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [busy, setBusy] = useState(false)
  const [clock, setClock] = useState(0)

  useEffect(() => {
    let alive = true
    apiRequest<HelpdeskComplaint[]>('/helpdesk/complaints')
      .then((data) => { if (alive) setComplaints(data) })
      .catch((caught: unknown) => { if (alive) setError(caught instanceof Error ? caught.message : 'Please try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [reload])

  useEffect(() => {
    const initialTick = window.setTimeout(() => setClock(Date.now()), 0)
    const interval = window.setInterval(() => setClock(Date.now()), 60_000)
    return () => {
      window.clearTimeout(initialTick)
      window.clearInterval(interval)
    }
  }, [])

  function reloadQueue() {
    setLoading(true)
    setError('')
    setActionError('')
    setReload((value) => value + 1)
  }

  async function update(complaintId: number, action: 'category' | 'assign' | 'status', payload: unknown) {
    setBusy(true)
    setActionError('')
    try {
      await postJson<HelpdeskComplaint>(`/helpdesk/complaints/${complaintId}/${action}`, payload)
      reloadQueue()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'The update could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <StaffShell role="helpdesk"><PageSkeleton /></StaffShell>
  if (error || !complaints) {
    return <StaffShell role="helpdesk"><ErrorState message={error || 'The complaint queue is unavailable.'} retry={reloadQueue} /></StaffShell>
  }

  const visible = complaints.filter((complaint) => {
    const statusMatches = statusFilter === 'active'
      ? ['open', 'assigned', 'in_progress'].includes(complaint.status)
      : statusFilter === 'all' || complaint.status === statusFilter
    return statusMatches && (categoryFilter === 'all' || complaint.category === categoryFilter)
  })
  const selected = visible.find((complaint) => complaint.id === selectedId) ?? visible[0] ?? null

  return (
    <StaffShell role="helpdesk">
      <div className="staff-page-stack">
        <div className="page-intro">
          <p className="eyebrow">SERVICE DESK</p>
          <h1>Complaint queue</h1>
          <p className="muted-copy">Urgent reports rise to the top. Open a case to review and update it.</p>
        </div>

        <Card className="queue-toolbar">
          <label className="filter-field">
            <span>Status</span>
            <select className="select-input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="active">Active cases</option>
              <option value="all">All cases</option>
              <option value="open">Open</option>
              <option value="assigned">Assigned</option>
              <option value="in_progress">In progress</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Category</span>
            <select className="select-input" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="all">All categories</option>
              {CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
          </label>
          <span className="queue-count">{visible.length} {visible.length === 1 ? 'case' : 'cases'}</span>
        </Card>

        {actionError && <p className="form-error action-error" role="alert">{actionError}</p>}
        {!visible.length ? (
          <Card><EmptyState title="The queue is clear">There are no complaints for these filters.</EmptyState></Card>
        ) : (
          <div className="helpdesk-layout">
            <div className="helpdesk-queue" aria-label="Complaints ordered by urgency">
              {visible.map((complaint) => (
                <button
                  className={`queue-item${selected?.id === complaint.id ? ' is-selected' : ''}`}
                  key={complaint.id}
                  onClick={() => setSelectedId(complaint.id)}
                  type="button"
                >
                  <div className="queue-item__top">
                    <span className={`urgency-badge urgency-badge--${complaint.urgency}`}>
                      {complaint.urgency === 'critical' && <span aria-hidden="true">!</span>}
                      {complaint.urgency}
                    </span>
                    <StatusPill status={complaint.status} />
                  </div>
                  <strong>{complaint.category}</strong>
                  <span className="queue-item__text">{complaint.text}</span>
                  <span className="queue-item__meta">{formatDateTime(complaint.created_at)}</span>
                  <span className="queue-item__badges">
                    {complaint.overdue && <span className="overdue-badge">{overdueLabel(complaint.respond_by, clock)}</span>}
                    {complaint.duplicates_count > 0 && <span className="duplicate-badge">{complaint.duplicates_count} linked</span>}
                  </span>
                </button>
              ))}
            </div>

            {selected && (
              <Card className="helpdesk-detail">
                <div className="detail-heading">
                  <div>
                    <p className="eyebrow">CASE #{selected.id}</p>
                    <h2>{selected.category}</h2>
                  </div>
                  <StatusPill status={selected.status} />
                </div>
                <p className="helpdesk-detail__text">{selected.text}</p>
                <div className="detail-facts">
                  <div><span>Flat ID</span><strong>{selected.flat_id}</strong></div>
                  <div><span>Raised</span><strong>{formatDateTime(selected.created_at)}</strong></div>
                  <div><span>Respond by</span><strong>{selected.respond_by ? formatDateTime(selected.respond_by) : 'Not set'}</strong></div>
                  <div><span>Assigned to</span><strong>{selected.assigned_to ? `Staff #${selected.assigned_to}` : 'Unassigned'}</strong></div>
                </div>

                <div className="staff-action-section">
                  <h3>Change category</h3>
                  <div className="category-options">
                    {CATEGORIES.map((category) => (
                      <button
                        className={`category-option${selected.category === category ? ' is-active' : ''}`}
                        key={category}
                        disabled={busy || selected.category === category}
                        onClick={() => void update(selected.id, 'category', { category })}
                        type="button"
                      >{category}</button>
                    ))}
                  </div>
                </div>

                <div className="staff-action-section staff-action-section--row">
                  <div><h3>Assignment</h3><p className="muted-copy">Take ownership of this case.</p></div>
                  <Button variant="secondary" disabled={busy || selected.assigned_to === userId || !userId} onClick={() => void update(selected.id, 'assign', { assignee_id: userId })}>
                    {selected.assigned_to === userId ? 'Assigned to me' : 'Assign to me'}
                  </Button>
                </div>

                <div className="staff-action-section">
                  <h3>Update status</h3>
                  <div className="status-actions">
                    {(TRANSITIONS[selected.status] ?? []).map((next) => (
                      <Button key={next} variant={next === 'resolved' ? 'primary' : 'secondary'} disabled={busy} onClick={() => void update(selected.id, 'status', { status: next })}>
                        {next.replaceAll('_', ' ')}
                      </Button>
                    ))}
                    {!TRANSITIONS[selected.status]?.length && <p className="muted-copy">This case has no further status changes.</p>}
                  </div>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </StaffShell>
  )
}
