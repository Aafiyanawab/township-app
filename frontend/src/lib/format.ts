export type MoneyValue = string | number

export function addMoney(left: MoneyValue, right: MoneyValue): string {
  const toCents = (value: MoneyValue) => moneyToCents(value)
  const cents = toCents(left) + toCents(right)
  const sign = cents < 0 ? '-' : ''
  const absolute = cents < 0 ? -cents : cents
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}

export function moneyToCents(value: MoneyValue) {
  const [whole = '0', fraction = ''] = String(value).split('.')
  const sign = whole.startsWith('-') ? -1n : 1n
  return sign * (BigInt(whole.replace('-', '') || '0') * 100n + BigInt((fraction + '00').slice(0, 2)))
}

export function isPositiveMoney(value: MoneyValue) {
  return moneyToCents(value) > 0n
}

export function formatRupees(value: MoneyValue) {
  const text = String(value)
  const [wholeRaw = '0', fraction = '00'] = text.split('.')
  const negative = wholeRaw.startsWith('-')
  const whole = wholeRaw.replace('-', '')
  const grouped = whole.length > 3
    ? `${whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',')},${whole.slice(-3)}`
    : whole
  return `${negative ? '−' : ''}₹${grouped}.${fraction.padEnd(2, '0').slice(0, 2)}`
}

export function formatDate(value: string) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00`)
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

export function formatDateTime(value: string) {
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
  }).format(new Date(timestamp))
}

export function periodLabel(value: string) {
  const [year, month] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(new Date(year, month - 1, 1))
}
