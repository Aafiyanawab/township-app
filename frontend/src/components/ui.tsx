import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  fullWidth?: boolean
}

export function Button({ variant = 'primary', fullWidth, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`button button--${variant}${fullWidth ? ' button--full' : ''} ${className}`.trim()}
      {...props}
    />
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`.trim()}>{children}</section>
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`.trim()} />
}

export function PageSkeleton() {
  return (
    <div className="stack-lg" aria-label="Loading content">
      <Skeleton className="skeleton-heading" />
      <Skeleton className="skeleton-panel" />
      <Skeleton className="skeleton-row" />
      <Skeleton className="skeleton-row" />
    </div>
  )
}

export function EmptyState({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-state__mark" aria-hidden="true">✳</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  )
}

export function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>We couldn’t load this just now.</strong>
        <p>{message}</p>
      </div>
      <Button variant="secondary" onClick={retry}>Try again</Button>
    </div>
  )
}

export function SectionHeading({
  eyebrow,
  title,
  action,
}: {
  eyebrow?: string
  title: string
  action?: ReactNode
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  )
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-pill--${status.replaceAll('_', '-')}`}>{status.replaceAll('_', ' ')}</span>
}

export function Icon({ name }: { name: 'home' | 'bill' | 'chat' | 'arrow' | 'back' }) {
  const paths = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-6h6v6" /></>,
    bill: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6M9 16h2" /></>,
    chat: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-2 2v-6A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8 11h.01M12 11h.01M16 11h.01" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    back: <><path d="M19 12H5M11 18l-6-6 6-6" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}
