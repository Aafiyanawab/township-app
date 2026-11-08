import { useEffect, useState } from 'react'
import { apiRequest, type CommitteeSummary } from '../api'
import { StaffShell } from '../components/StaffShell'
import { Card, EmptyState, ErrorState, PageSkeleton, SectionHeading } from '../components/ui'
import { formatRupees, moneyToCents, periodLabel } from '../lib/format'

const AGEING_LABELS: Record<'0_30' | '31_60' | '61_plus', string> = {
  '0_30': '0–30 days',
  '31_60': '31–60 days',
  '61_plus': '61+ days',
}

function moneyWidth(value: string, max: bigint) {
  const cents = moneyToCents(value)
  if (cents <= 0n || max <= 0n) return '0%'
  const basisPoints = (cents * 10_000n) / max
  return `${basisPoints / 100n}.${String(basisPoints % 100n).padStart(2, '0')}%`
}

function countWidth(value: number, max: number) {
  if (value <= 0 || max <= 0) return '0%'
  const basisPoints = Math.floor((value * 10_000) / max)
  return `${Math.floor(basisPoints / 100)}.${String(basisPoints % 100).padStart(2, '0')}%`
}

export function CommitteePage() {
  const [summary, setSummary] = useState<CommitteeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let alive = true
    apiRequest<CommitteeSummary>('/committee/summary')
      .then((data) => { if (alive) setSummary(data) })
      .catch((caught: unknown) => { if (alive) setError(caught instanceof Error ? caught.message : 'Please try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [reload])

  function retry() {
    setLoading(true)
    setError('')
    setReload((value) => value + 1)
  }

  if (loading) return <StaffShell role="committee"><PageSkeleton /></StaffShell>
  if (error || !summary) {
    return <StaffShell role="committee"><ErrorState message={error || 'The committee summary is unavailable.'} retry={retry} /></StaffShell>
  }

  const collectionMax = [moneyToCents(summary.collections), moneyToCents(summary.billed)].reduce((max, value) => value > max ? value : max, 0n)
  const ageingMax = Object.values(summary.dues_ageing).reduce((max, amount) => {
    const cents = moneyToCents(amount)
    return cents > max ? cents : max
  }, 0n)
  const statusEntries = Object.entries(summary.complaints_by_status)
  const statusMax = statusEntries.reduce((max, [, count]) => Math.max(max, count), 0)
  const totalComplaints = statusEntries.reduce((total, [, count]) => total + count, 0)
  const hasData = collectionMax > 0n || ageingMax > 0n || totalComplaints > 0

  return (
    <StaffShell role="committee">
      <div className="staff-page-stack">
        <div className="page-intro committee-intro">
          <div><p className="eyebrow">COMMUNITY OVERVIEW</p><h1>Committee dashboard</h1></div>
          <span className="period-chip">{periodLabel(`${summary.period}-01`)}</span>
        </div>

        {!hasData && <Card><EmptyState title="No summary data yet">Collections and complaint activity will appear when records are available.</EmptyState></Card>}

        <div className="committee-metrics">
          <Card className="committee-metric"><span>First response average</span><strong>{summary.average_hours_to_first_response === null ? '—' : `${summary.average_hours_to_first_response} hrs`}</strong><small>{summary.average_hours_to_first_response === null ? 'No first responses recorded' : 'From complaint creation'}</small></Card>
          <Card className="committee-metric"><span>Reopened complaints</span><strong>{summary.reopened_percentage}%</strong><small>{summary.reopened_count} {summary.reopened_count === 1 ? 'complaint' : 'complaints'} reopened</small></Card>
          <Card className="committee-metric"><span>Average rating</span><strong>{summary.average_rating === null ? '—' : `${summary.average_rating} / 5`}</strong><small>{summary.average_rating === null ? 'No ratings recorded' : 'Resident feedback'}</small></Card>
        </div>

        <div className="committee-grid">
          <Card className="committee-chart-card">
            <SectionHeading eyebrow="CURRENT PERIOD" title="Collections vs billed" />
            <div className="bar-chart">
              <div className="bar-row">
                <div className="bar-row__label"><span>Collections</span><strong>{formatRupees(summary.collections)}</strong></div>
                <div className="bar-track"><span className="bar-fill bar-fill--forest" style={{ width: moneyWidth(summary.collections, collectionMax) }} /></div>
              </div>
              <div className="bar-row">
                <div className="bar-row__label"><span>Billed</span><strong>{formatRupees(summary.billed)}</strong></div>
                <div className="bar-track"><span className="bar-fill bar-fill--marigold" style={{ width: moneyWidth(summary.billed, collectionMax) }} /></div>
              </div>
            </div>
          </Card>

          <Card className="committee-chart-card">
            <SectionHeading eyebrow="OUTSTANDING PRINCIPAL" title="Dues ageing" />
            <div className="bar-chart">
              {(Object.keys(AGEING_LABELS) as Array<keyof typeof AGEING_LABELS>).map((key) => (
                <div className="bar-row" key={key}>
                  <div className="bar-row__label"><span>{AGEING_LABELS[key]}</span><strong>{formatRupees(summary.dues_ageing[key])}</strong></div>
                  <div className="bar-track"><span className="bar-fill bar-fill--forest" style={{ width: moneyWidth(summary.dues_ageing[key], ageingMax) }} /></div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="committee-chart-card committee-status-card">
            <SectionHeading eyebrow="SERVICE DESK" title="Complaints by status" />
            {totalComplaints ? (
              <div className="bar-chart">
                {statusEntries.map(([status, count]) => (
                  <div className="bar-row" key={status}>
                    <div className="bar-row__label"><span>{status.replaceAll('_', ' ')}</span><strong>{count}</strong></div>
                    <div className="bar-track"><span className="bar-fill bar-fill--forest" style={{ width: countWidth(count, statusMax) }} /></div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No complaints have been recorded for this community.</p>
            )}
          </Card>
        </div>
      </div>
    </StaffShell>
  )
}
