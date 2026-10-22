import { useEffect, useState, type ReactNode } from 'react'

export type Tone = 'success' | 'info' | 'warning' | 'danger' | 'neutral'
type Theme = 'system' | 'light' | 'dark'
const themeKey = 'support-theme'

function savedTheme(): Theme {
    try {
        const value = localStorage.getItem(themeKey)
        return value === 'light' || value === 'dark' ? value : 'system'
    } catch { return 'system' }
}

export function ThemeToggle() {
    const [theme, setTheme] = useState<Theme>(savedTheme)
    useEffect(() => {
        const media = window.matchMedia?.('(prefers-color-scheme: dark)')
        const apply = () => { document.documentElement.dataset.theme = theme === 'system' ? (media?.matches ? 'dark' : 'light') : theme }
        apply()
        media?.addEventListener('change', apply)
        return () => media?.removeEventListener('change', apply)
    }, [theme])
    function change(value: Theme) {
        setTheme(value)
        try { localStorage.setItem(themeKey, value) } catch { /* Storage may be disabled. */ }
    }
    return <label className="theme-choice">Tema <select aria-label="Tema" value={theme} onChange={(event) => change(event.target.value as Theme)}><option value="system">Sistema</option><option value="light">Claro</option><option value="dark">Escuro</option></select></label>
}

export function formatDate(value: string | null | undefined): string {
    if (!value) return 'não disponível'
    const timestamp = new Date(value)
    return Number.isNaN(timestamp.getTime()) ? 'não disponível' : new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(timestamp).replace(',', '')
}
export function formatNumber(value: number | null | undefined): string {
    return value == null ? 'não disponível' : new Intl.NumberFormat('pt-BR').format(value)
}
export function formatDuration(value: number | null | undefined): string {
    if (value == null) return 'não disponível'
    if (value < 1000) return `${formatNumber(Math.round(value))} ms`
    if (value < 60000) return `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(value / 1000)} s`
    return `${Math.floor(value / 60000)} min ${Math.floor(value % 60000 / 1000)} s`
}
export function formatCurrency(value: number | null | undefined, currency: string | null): string {
    return value == null || currency !== 'USD' ? 'não disponível' : `USD ${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 6 }).format(value)} (estimativa)`
}
export function TableValue({ value }: { value: ReactNode | null | undefined }) {
    return value == null ? <span aria-label="não disponível" title="não disponível">—</span> : <>{value}</>
}
export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
    return <span className={`status-badge ${tone}`}>{children}</span>
}
const codes: Record<string, string> = {
    MINIMUM_TICKET_DATA_MISSING: 'Faltam dados mínimos para abrir o ticket',
    TICKET_OUTCOME_UNKNOWN: 'Resultado do ticket incerto',
    TICKET_CREATE_FAILED: 'Abertura do ticket falhou',
}
export function ErrorCodeLabel({ code }: { code: string | null }) {
    return code ? <span className="error-code">{codes[code] ?? 'Falha registrada'} <small>{code}</small></span> : null
}
export function IdChip({ id }: { id: string }) {
    return <span className="id-chip"><span title={id}>{id.slice(0, 8)}</span><button type="button" aria-label={`Copiar ID ${id}`} title="Copiar ID completo" onClick={() => void navigator.clipboard?.writeText(id)}>⧉</button></span>
}
export function KpiCard({ label, value, definition, period }: { label: string; value: string | number; definition: string; period?: string }) {
    return <div className="admin-metric"><span>{label} <span className="ia-help" tabIndex={0} role="img" title={definition} aria-label={definition}>i</span></span><strong>{value}</strong>{period && <small>{period}</small>}</div>
}
export function AvisoDeLacuna({ notices }: { notices: { type: string; text: string }[] }) {
    return <div className="gap-notices">{[...new Map(notices.map((notice) => [notice.type, notice])).values()].map((notice) => <p role="status" className="admin-muted" key={notice.type}>{notice.text}</p>)}</div>
}