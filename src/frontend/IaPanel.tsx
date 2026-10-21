import { useEffect, useState } from 'react'
import {
    getIaDetails, getIaPricingConfig, getIaSummary, getIaTimeseries,
    type IaDetailsPage, type IaFilters, type IaPricingConfig, type IaResult, type IaSummary, type IaTimeseries,
} from './chatApi'
import { AvisoDeLacuna, formatCurrency, formatDate, formatDuration, formatNumber, IdChip, KpiCard } from './ui'

const pageSize = 20
const initialFilters: IaFilters = { start_date: '', end_date: '', model: '', step: '', result: '' }
const resultNames: Record<IaResult, string> = {
    respond: 'Resposta', open_ticket: 'Ticket', blocked: 'Bloqueado',
    ask_clarification: 'Esclarecimento', failed: 'Falha', running: 'Em andamento',
}
const terminalResults: IaResult[] = ['respond', 'open_ticket', 'blocked']
const otherResults: IaResult[] = ['ask_clarification', 'failed', 'running']

function available(value: number | null | undefined, unit = ''): string {
    return value == null ? 'não disponível' : `${formatNumber(value)}${unit}`
}

function cell(value: number | null | undefined): string {
    return value == null ? '—' : formatNumber(value)
}

function costReason(item: IaDetailsPage['items'][number]): string {
    if (item.estimated_cost_value != null) return `Etapa · amostra 1 · ${item.estimated_cost_currency ?? 'USD'}`
    if (item.state !== 'complete') return 'Etapa não concluída'
    if (!item.model) return 'Modelo não registrado'
    if (!item.deployment_id) return 'Deployment não registrado'
    if ([item.tokens_input, item.tokens_output, item.tokens_cache, item.tokens_cache_write].some((value) => value == null)) return 'Tokens não medidos'
    return 'Sem tarifa ativa correspondente'
}

function Bars({ values, unit = '' }: { values: { label: string; value: number | null }[]; unit?: string }) {
    const max = Math.max(0, ...values.map(({ value }) => value ?? 0))
    return <div className="ia-bars">{values.map(({ label, value }) => <div className="ia-bar-row" key={label}>
        <span>{label}</span><div className="ia-bar-track" aria-hidden="true"><div style={{ width: value == null || max === 0 ? '0%' : `${value / max * 100}%` }} /></div>
        <strong>{available(value, unit)}</strong>
    </div>)}</div>
}

export default function IaPanel({ onConversation, onRun }: { onConversation: (id: string) => void; onRun: (id: string) => void }) {
    const [filters, setFilters] = useState<IaFilters>(initialFilters)
    const [offset, setOffset] = useState(0)
    const [revision, setRevision] = useState(0)
    const [summary, setSummary] = useState<IaSummary | null>(null)
    const [details, setDetails] = useState<IaDetailsPage | null>(null)
    const [series, setSeries] = useState<IaTimeseries | null>(null)
    const [pricing, setPricing] = useState<IaPricingConfig | null>(null)
    const [pricingError, setPricingError] = useState(false)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        setLoading(true)
        setError(null)
        setPricingError(false)
        const pricingRequest = getIaPricingConfig().catch(() => null)
        Promise.all([getIaSummary(filters), getIaDetails(filters, pageSize, offset), getIaTimeseries(filters), pricingRequest])
            .then(([nextSummary, nextDetails, nextSeries, nextPricing]) => {
                if (!active) return
                setSummary(nextSummary)
                setDetails(nextDetails)
                setSeries(nextSeries)
                setPricing(nextPricing)
                setPricingError(nextPricing == null)
            })
            .catch(() => { if (active) setError('Não foi possível carregar a telemetria da IA.') })
            .finally(() => { if (active) setLoading(false) })
        return () => { active = false }
    }, [filters, offset, revision])

    function updateFilter(name: keyof IaFilters, value: string) {
        setOffset(0)
        setFilters((current) => ({ ...current, [name]: value }))
    }

    const period = filters.start_date || filters.end_date ? `${filters.start_date || 'início'} a ${filters.end_date || 'hoje'}` : 'Todo o período'
    const models = [...new Set([...(summary?.available_models ?? []), ...(pricing?.items.map((item) => item.model) ?? []), ...(details?.items.map((item) => item.model).filter((model): model is string => model != null) ?? []), filters.model].filter(Boolean))]
    const noRuns = summary?.executions === 0
    const missingTelemetry = summary?.executions != null && summary.executions > 0 &&
        summary.stage_mean_ms.sample_size === 0 && summary.estimated_cost.sample_size === 0
    const referencePrices = pricing?.reference_prices ?? []
    const tokenLabels: Record<string, string> = { input: 'Entrada', cache: 'Entrada em cache', cache_write: 'Escrita em cache', output: 'Saída' }

    return <div className="ia-panel">
        <div className="ia-filters" aria-label="Filtros IA">
            <label>Início<input type="date" value={filters.start_date} max={filters.end_date || undefined} onChange={(event) => updateFilter('start_date', event.target.value)} /></label>
            <label>Fim<input type="date" value={filters.end_date} min={filters.start_date || undefined} onChange={(event) => updateFilter('end_date', event.target.value)} /></label>
            <label>Modelo<select value={filters.model} onChange={(event) => updateFilter('model', event.target.value)}><option value="">Todos</option>{models.map((model) => <option key={model} value={model}>{model}</option>)}</select></label>
            <label>Etapa<select value={filters.step} onChange={(event) => updateFilter('step', event.target.value)}><option value="">Todas</option>{['triage', 'knowledge', 'response', 'policy', 'ticketing'].map((step) => <option key={step} value={step}>{step}</option>)}</select></label>
            <label>Resultado<select value={filters.result} onChange={(event) => updateFilter('result', event.target.value)}><option value="">Todos</option>{Object.entries(resultNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        </div>
        <p className="admin-muted">Período: {period} · Amostra: {!loading && !error && summary?.executions != null ? `${available(summary.executions)} execuções` : 'não disponível'}</p>
        {loading && <p role="status" className="admin-muted">Carregando telemetria…</p>}
        {error && <div role="alert" className="admin-error">{error} <button type="button" className="admin-text-button" onClick={() => setRevision((value) => value + 1)}>Tentar novamente</button></div>}
        {!loading && !error && noRuns && <p className="admin-muted">Nenhuma execução no período selecionado.</p>}
        {!loading && !error && summary?.executions == null && <p className="admin-muted">Quantidade de execuções não disponível; não é possível determinar se o período está vazio.</p>}
        {!loading && !error && <AvisoDeLacuna notices={[
            ...(missingTelemetry ? [{ type: 'telemetry', text: 'Existem execuções, mas não há telemetria de custo ou latência disponível.' }] : []),
            ...(summary && summary.stage_p95_ms.sample_size > 0 && summary.stage_p95_ms.sample_size < 20 ? [{ type: 'sample', text: 'p95 e máximo ocultos para amostras menores que 20 etapas.' }] : []),
            ...(pricingError ? [{ type: 'pricing', text: 'Configuração de tarifas indisponível; o custo exibido vem apenas do servidor.' }] : []),
            ...(details && details.total > details.items.length ? [{ type: 'page', text: 'Os registros abaixo são apenas a página carregada; não representam o total global.' }] : []),
        ]} />}
        {!loading && !error && summary && series && details && !noRuns && <>
            <section aria-label="Indicadores IA" className="admin-metrics ia-metrics">
                {[
                    ['Execuções', available(summary.executions)],
                    ['Custo estimado', formatCurrency(summary.estimated_cost.value, summary.estimated_cost.currency)],
                    ['Latência média de etapa', formatDuration(summary.stage_mean_ms.value)],
                    ['p95 de etapa (nearest-rank)', summary.stage_p95_ms.sample_size === 0 ? 'não disponível' : summary.stage_p95_ms.sample_size >= 20 ? formatDuration(summary.stage_p95_ms.value) : 'amostra insuficiente'],
                ].map(([label, value]) => <KpiCard key={label} label={label} value={value} definition="Valor agregado retornado pelo servidor para os filtros selecionados." />)}
            </section>
            <p className="admin-muted">{summary.estimated_cost.sample_size >= summary.estimated_cost.required_rows ? `Amostras: custo ${summary.estimated_cost.sample_size} de ${summary.estimated_cost.required_rows} etapas` : `Cobertura incompleta: ${summary.estimated_cost.sample_size} de ${summary.estimated_cost.required_rows} etapas com custo calculável`}; latência média {summary.stage_mean_ms.sample_size}; p95 {summary.stage_p95_ms.sample_size} etapas concluídas.{summary.estimated_cost.value != null && summary.estimated_cost.currency === 'USD' ? ' Custo em USD é estimativa.' : ''}</p>
            <div className="ia-charts">
                <section className="admin-section" aria-label="Evolução de execuções"><div className="admin-section-heading"><h2>Evolução de execuções</h2><span>execuções / dia</span></div>
                    {series.executions.length ? <Bars values={series.executions.map((point) => ({ label: point.date, value: point.count }))} /> : <p className="admin-muted">Série temporal não disponível.</p>}</section>
                <section className="admin-section" aria-label="Distribuição de resultados"><div className="admin-section-heading"><h2>Resultados</h2><span>execuções</span></div>
                    <Bars values={terminalResults.map((result) => ({ label: `${resultNames[result]} · ${available(summary.result_percentages[result as 'respond' | 'open_ticket' | 'blocked'], '%')}`, value: summary.results[result] }))} />
                    <p className="admin-muted">Percentuais: {summary.terminal_sample_size} execuções terminais (resposta, ticket, bloqueio).</p>
                    <Bars values={otherResults.map((result) => ({ label: resultNames[result], value: summary.results[result] }))} /></section>
                <section className="admin-section" aria-label="Latência por etapa"><div className="admin-section-heading"><h2>Latência por etapa</h2><span>média · p95 · máximo / ms</span></div>
                    {series.stages.length ? series.stages.map((stage) => <div className="admin-row" key={stage.step_name}><strong>{stage.step_name}</strong><span>{formatDuration(stage.mean_ms)} · {stage.sample_size === 0 ? 'não disponível' : stage.sample_size >= 20 ? formatDuration(stage.p95_ms) : 'amostra insuficiente'} · {stage.sample_size === 0 ? 'não disponível' : stage.sample_size >= 20 ? formatDuration(stage.max_ms) : 'amostra insuficiente'} · amostra {stage.sample_size}</span></div>) : <p className="admin-muted">Latência por etapa não disponível.</p>}</section>
            </div>
            <section className="admin-section" aria-label="Contadores de tentativas"><div className="admin-section-heading"><h2>Falhas e tentativas</h2></div><div className="ia-counters">
                {[
                    ['Falhas de etapa', summary.step_failures, 'Etapas encerradas com falha; não incluem replays.'],
                    ['Tentativas reais observadas', summary.observed_model_attempts, 'Chamadas ao modelo comprovadas por telemetria do runtime ou provider; execução da crew não prova uma tentativa.'],
                    ['Retentativas operacionais', summary.operational_retries, 'Novas execuções do fluxo vinculadas à execução original.'],
                    ['Replays', summary.replays, 'Respostas persistidas devolvidas por idempotência; não executam etapas nem acrescentam custo.'],
                ].map(([label, value, description]) => <div key={label} className="admin-metric"><span>{label} <span className="ia-help" tabIndex={0} title={String(description)} aria-label={String(description)}>ⓘ</span></span><strong>{available(value as number | null)}</strong><small>{description}</small></div>)}
            </div></section>
            <section className="admin-section" aria-label="Detalhes por execução e etapa"><div className="admin-section-heading"><h2>Execuções e etapas</h2><span>{details.total} registros · {period}</span></div>
                {details.items.length === 0 ? <p className="admin-muted">Nenhuma etapa encontrada para estes filtros.</p> : <div className="ia-table-scroll"><table className="ia-table"><thead><tr><th>Execução / etapa</th><th>Modelo / estado</th><th>Início / fim</th><th>Duração</th><th>Tokens entrada / saída / leitura / escrita de cache</th><th>Custo estimado</th><th>Tentativas / retentativas / replays</th></tr></thead><tbody>
                    {details.items.map((item, index) => <tr key={`${item.agent_run_id}-${item.step_name}-${index}`}><td><strong><IdChip id={item.agent_run_id} /></strong><br />{item.step_name}<br />
                        {item.session_id && <button type="button" className="admin-text-button" onClick={() => onConversation(item.session_id!)}>Ver conversa</button>}{' '}<button type="button" className="admin-text-button" onClick={() => onRun(item.agent_run_id)}>Ver execução</button></td>
                        <td>{item.model ?? 'não disponível'}<br />{item.state}</td><td>{formatDate(item.start_time)}<br />{formatDate(item.end_time)}</td><td>{formatDuration(item.duration_ms)}</td>
                        <td>{[item.tokens_input, item.tokens_output, item.tokens_cache, item.tokens_cache_write].map(cell).join(' / ')}</td>
                        <td>{formatCurrency(item.estimated_cost_value, item.estimated_cost_currency)}<br /><small>{costReason(item)}</small>{item.estimated_cost_value != null && <><br /><small>Tarifa: {formatDate(item.estimated_cost_validity_start)} a {formatDate(item.estimated_cost_validity_end)}</small></>}</td>
                        <td>{[item.attempt_count, item.retry_count, item.replay_count].map(cell).join(' / ')}</td></tr>)}
                </tbody></table></div>}
                {details.total > pageSize && <div className="admin-pagination"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Anterior</button><span>{offset + 1}–{Math.min(offset + pageSize, details.total)} de {details.total}</span><button type="button" disabled={offset + pageSize >= details.total} onClick={() => setOffset(offset + pageSize)}>Próxima</button></div>}
            </section>
        </>}
        {!loading && !error && referencePrices.length > 0 && <details className="admin-section ia-pricing"><summary>Tarifas de referência (não são custo medido)</summary>
            <div className="admin-section-heading"><h2>Preços de referência</h2><span>USD / 1 milhão de tokens</span></div>
            {referencePrices.map((item) => <div className="admin-row" key={item.token_type}><strong>{tokenLabels[item.token_type] ?? item.token_type}</strong><span>US$ {Number(item.rate_per_million).toFixed(2).replace('.', ',')}</span></div>)}
            <p className="admin-muted">Valores de referência; não permitem inferir custo de execuções sem tokens medidos e tarifa ativa.</p>
        </details>}
    </div>
}