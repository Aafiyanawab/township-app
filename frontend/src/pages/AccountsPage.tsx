import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiRequest, postJson, type BankImportSummary, type BankRowsPage, type FlatOption } from '../api'
import { StaffShell } from '../components/StaffShell'
import { Button, Card, EmptyState, ErrorState, PageSkeleton, SectionHeading, StatusPill } from '../components/ui'
import { formatRupees } from '../lib/format'

type RowStatus = 'queued' | 'unmatched' | 'posted' | 'ignored'

export function AccountsPage() {
  const [queue, setQueue] = useState<BankRowsPage | null>(null)
  const [flats, setFlats] = useState<FlatOption[] | null>(null)
  const [status, setStatus] = useState<RowStatus>('queued')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [summary, setSummary] = useState<BankImportSummary | null>(null)
  const [flatSelections, setFlatSelections] = useState<Record<number, number>>({})
  const [busyRow, setBusyRow] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      apiRequest<FlatOption[]>('/accounts/flats'),
      apiRequest<BankRowsPage>(`/accounts/bank-rows?status=${status}&page=${page}`),
    ])
      .then(([flatData, queueData]) => {
        if (alive) {
          setFlats(flatData)
          setQueue(queueData)
        }
      })
      .catch((caught: unknown) => { if (alive) setLoadError(caught instanceof Error ? caught.message : 'Please try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [page, reload, status])

  function reloadRows() {
    setLoading(true)
    setLoadError('')
    setReload((value) => value + 1)
  }

  async function uploadStatement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setUploadError('')
    if (!file) {
      setUploadError('Choose a CSV file to upload.')
      return
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadError('Choose a file with a .csv extension.')
      return
    }
    if (file.size > 1_048_576) {
      setUploadError('The file must be 1 MB or smaller.')
      return
    }
    setUploadBusy(true)
    try {
      const body = new FormData()
      body.append('file', file)
      const result = await apiRequest<BankImportSummary>('/accounts/bank-statements', { method: 'POST', body })
      setSummary(result)
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setStatus('queued')
      setPage(1)
      setLoading(true)
      setLoadError('')
      setReload((value) => value + 1)
    } catch (caught) {
      setUploadError(caught instanceof Error ? caught.message : 'The statement could not be imported.')
    } finally {
      setUploadBusy(false)
    }
  }

  async function resolve(rowId: number, suggestedCode: string | null) {
    const suggestedId = flats?.find((flat) => flat.code === suggestedCode)?.id
    const flatId = flatSelections[rowId] ?? suggestedId
    if (!flatId) {
      setActionError('Choose the flat to attach this payment to.')
      return
    }
    setBusyRow(rowId)
    setActionError('')
    try {
      await postJson(`/accounts/bank-rows/${rowId}/resolve`, { flat_id: flatId })
      reloadRows()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'The row could not be resolved.')
    } finally {
      setBusyRow(null)
    }
  }

  async function ignore(rowId: number) {
    setBusyRow(rowId)
    setActionError('')
    try {
      await apiRequest(`/accounts/bank-rows/${rowId}/ignore`, { method: 'POST' })
      reloadRows()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'The row could not be ignored.')
    } finally {
      setBusyRow(null)
    }
  }

  if (loading) return <StaffShell role="accounts"><PageSkeleton /></StaffShell>
  if (loadError || !queue || !flats) {
    return <StaffShell role="accounts"><ErrorState message={loadError || 'Account data is unavailable.'} retry={reloadRows} /></StaffShell>
  }

  const pageCount = Math.max(1, Math.ceil(queue.total / queue.page_size))

  return (
    <StaffShell role="accounts">
      <div className="staff-page-stack">
        <div className="page-intro">
          <p className="eyebrow">RECONCILIATION</p>
          <h1>Bank statements</h1>
          <p className="muted-copy">Import a statement, review suggested matches and decide where unclear payments belong.</p>
        </div>

        <Card className="upload-card">
          <SectionHeading eyebrow="CSV IMPORT" title="Upload a statement" action={<a className="text-link" href="/sample_bank_statement.csv" download>Download sample CSV <span aria-hidden="true">↓</span></a>} />
          <form className="upload-form" onSubmit={uploadStatement}>
            <label className="file-picker">
              <span className="file-picker__icon" aria-hidden="true">↑</span>
              <span className="file-picker__copy"><strong>{file?.name ?? 'Choose a bank statement'}</strong><small>CSV file · up to 1 MB</small></span>
              <input ref={fileInput} type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setUploadError('') }} />
            </label>
            {uploadError && <p className="form-error" role="alert">{uploadError}</p>}
            <Button type="submit" disabled={uploadBusy || !file}>{uploadBusy ? 'Importing…' : 'Upload CSV'}</Button>
          </form>
        </Card>

        {summary && (
          <Card className="import-result" aria-live="polite">
            <div className="import-result__heading"><div><p className="eyebrow">IMPORT COMPLETE</p><h2>Statement summary</h2></div><span className="batch-reference">Batch {summary.batch_id}</span></div>
            <div className="summary-stats summary-stats--six">
              <div><strong>{summary.posted}</strong><span>Posted</span></div>
              <div><strong>{summary.queued}</strong><span>Queued</span></div>
              <div><strong>{summary.unmatched}</strong><span>Unmatched</span></div>
              <div><strong>{summary.ignored}</strong><span>Ignored</span></div>
              <div><strong>{summary.duplicates_skipped}</strong><span>Duplicates skipped</span></div>
              <div><strong>{summary.total_rows}</strong><span>Total rows</span></div>
            </div>
          </Card>
        )}

        <section className="page-section">
          <SectionHeading eyebrow="REVIEW &amp; RESOLVE" title="Bank rows" />
          <div className="bank-toolbar">
            <div className="bank-tabs" role="tablist" aria-label="Bank row status">
              {(['queued', 'unmatched', 'posted', 'ignored'] as const).map((value) => (
                <button className={`bank-tab${status === value ? ' is-active' : ''}`} key={value} onClick={() => {
                  setStatus(value)
                  setPage(1)
                  setLoading(true)
                  setLoadError('')
                }} role="tab" aria-selected={status === value} type="button">{value}</button>
              ))}
            </div>
            <span className="muted-copy bank-total">{queue.total} rows</span>
          </div>

          {actionError && <p className="form-error action-error" role="alert">{actionError}</p>}
          {queue.items.length ? (
            <div className="bank-row-list">
              {queue.items.map((row) => {
                const suggestedId = flats.find((flat) => flat.code === row.suggested_flat_code)?.id
                const selectedFlatId = flatSelections[row.id] ?? suggestedId
                const actionable = row.status === 'queued' || row.status === 'unmatched'
                return (
                  <Card className="bank-row-card" key={row.id}>
                    <div className="bank-row-card__top">
                      <div><StatusPill status={row.status} /><span className="bank-row-id">Row #{row.id}</span></div>
                      <strong className="bank-amount">{formatRupees(row.amount)}</strong>
                    </div>
                    <h3>{row.description}</h3>
                    <div className="bank-match-facts">
                      <div><span>Reference</span><strong>{row.reference || '—'}</strong></div>
                      <div><span>Confidence</span><strong>{row.confidence === null ? '—' : `${row.confidence}%`}</strong></div>
                      <div><span>Suggested flat</span><strong>{row.suggested_flat_code || 'No suggestion'}</strong></div>
                    </div>
                    <p className="match-reason">{row.match_reason || 'No match details are available.'}</p>
                    {actionable && (
                      <div className="bank-row-actions">
                        <label className="flat-select-field">
                          <span>Resolve to flat</span>
                          <select
                            className="select-input"
                            value={selectedFlatId ? String(selectedFlatId) : ''}
                            onChange={(event) => setFlatSelections((values) => ({ ...values, [row.id]: Number(event.target.value) }))}
                          >
                            <option value="">Choose a flat</option>
                            {flats.map((flat) => <option value={flat.id} key={flat.id}>{flat.code}</option>)}
                          </select>
                        </label>
                        <div className="bank-row-actions__buttons">
                          <Button variant="secondary" disabled={busyRow === row.id} onClick={() => void resolve(row.id, row.suggested_flat_code)}>{busyRow === row.id ? 'Saving…' : 'Resolve'}</Button>
                          <Button variant="quiet" disabled={busyRow === row.id} onClick={() => void ignore(row.id)}>Ignore</Button>
                        </div>
                      </div>
                    )}
                  </Card>
                )
              })}
            </div>
          ) : (
            <Card><EmptyState title={`No ${status} rows`}>Rows in this part of the reconciliation queue will appear here.</EmptyState></Card>
          )}

          {queue.total > queue.page_size && (
            <div className="pagination-row">
              <Button variant="secondary" disabled={page <= 1} onClick={() => { setPage((value) => value - 1); setLoading(true) }}>Previous</Button>
              <span>Page {page} of {pageCount}</span>
              <Button variant="secondary" disabled={page >= pageCount} onClick={() => { setPage((value) => value + 1); setLoading(true) }}>Next</Button>
            </div>
          )}
        </section>
      </div>
    </StaffShell>
  )
}
