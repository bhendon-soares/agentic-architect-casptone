import { useEffect, useState, type FormEvent } from 'react'
import {
    getAdminConversation, getAdminConversations, getAgentRun, getKnowledgeSources, getMetrics, getTickets,
    type AdminConversation, type AdminConversationDetail, type AdminConversationPage, type AgentRun, type KnowledgeSource, type Metrics, type RunError, type TicketPage,
} from './chatApi'
import './style.css'

const pageSize = 20

const actionLabels: Record<string, string> = {
    respond: 'Resposta', ask_clarification: 'Esclarecimento', open_ticket: 'Ticket', blocked: 'Bloqueado',
}
const ticketStatusLabels: Record<string, string> = {
    pending: 'Pendente', created: 'Criado', failed: 'Falhou', outcome_unknown: 'Resultado incerto',
}
const conversationStatusLabels: Record<string, string> = {
    active: 'Ativa', completed: 'Concluída', running: 'Em andamento', failed: 'Falhou', blocked: 'Bloqueado',
}

function conversationState(conversation: AdminConversation): { label: string; tone: string } {
    const status = conversation.last_run?.run_status === 'failed' ? 'failed' : conversation.last_run?.final_action || conversation.last_run?.run_status || conversation.status
    return { label: actionLabels[status] || conversationStatusLabels[status] || status, tone: status === 'failed' || status === 'blocked' ? status : '' }
}

function dateLabel(value: string | null): string {
    return value ? new Date(value).toLocaleString('pt-BR') : '—'
}

function errorLabel(cause: unknown): string {
    const error = cause as Partial<RunError>
    return error?.message || 'Não foi possível carregar os dados. Tente novamente.'
}

export default function AdminConsole() {
    const [metrics, setMetrics] = useState<Metrics | null>(null)
    const [conversations, setConversations] = useState<AdminConversationPage | null>(null)
    const [conversationOffset, setConversationOffset] = useState(0)
    const [tickets, setTickets] = useState<TicketPage | null>(null)
    const [sources, setSources] = useState<KnowledgeSource[] | null>(null)
    const [offset, setOffset] = useState(0)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [sessionInput, setSessionInput] = useState('')
    const [history, setHistory] = useState<AdminConversationDetail | null>(null)
    const [runs, setRuns] = useState<Record<string, AgentRun>>({})
    const [detailLoading, setDetailLoading] = useState(false)
    const [detailError, setDetailError] = useState<string | null>(null)
    const [selectedRun, setSelectedRun] = useState<string | null>(null)

    async function refresh(nextOffset = offset) {
        setLoading(true)
        setError(null)
        const results = await Promise.allSettled([getMetrics(), getTickets(pageSize, nextOffset), getKnowledgeSources(), getAdminConversations(pageSize, conversationOffset)])
        if (results[0].status === 'fulfilled') setMetrics(results[0].value)
        if (results[1].status === 'fulfilled') setTickets(results[1].value)
        if (results[2].status === 'fulfilled') setSources(results[2].value.items)
        if (results[3].status === 'fulfilled') setConversations(results[3].value)
        if (results.some((result) => result.status === 'rejected')) {
            setError('Alguns dados não puderam ser carregados. Atualize para tentar novamente.')
        }
        setLoading(false)
    }

    useEffect(() => { void refresh(0) }, [])

    async function loadConversations(nextOffset: number) {
        setLoading(true)
        setError(null)
        try {
            const page = await getAdminConversations(pageSize, nextOffset)
            setConversations(page)
            setConversationOffset(nextOffset)
        } catch (cause) {
            setError(errorLabel(cause))
        } finally {
            setLoading(false)
        }
    }

    async function openSession(id: string) {
        if (!id.trim()) return
        setDetailLoading(true)
        setDetailError(null)
        setHistory(null)
        setRuns({})
        setSelectedRun(null)
        try {
            const data = await getAdminConversation(id.trim())
            setHistory(data)
            setSessionInput(data.session_id)
        } catch (cause) {
            setDetailError(errorLabel(cause))
        } finally {
            setDetailLoading(false)
        }
    }

    function lookup(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        void openSession(sessionInput)
    }

    async function openRun(id: string) {
        setSelectedRun(id)
        if (runs[id]) return
        setDetailLoading(true)
        setDetailError(null)
        try {
            const run = await getAgentRun(id)
            setRuns((current) => ({ ...current, [id]: run }))
        } catch (cause) {
            setDetailError(errorLabel(cause))
        } finally {
            setDetailLoading(false)
        }
    }

    const run = selectedRun ? runs[selectedRun] : null

    return (
        <div className="app-shell">
            <header className="topbar">
                <div className="brand"><span className="brand-mark" aria-hidden="true">S/</span><span>Suporte TI <small>interno</small></span></div>
                <a className="topbar-link" href="/">Voltar ao chat</a>
                <span className="demo-label">DEMONSTRAÇÃO · DADOS FICTÍCIOS</span>
            </header>
            <main className="admin-workspace">
                <div className="admin-heading">
                    <div><p className="eyebrow">OPERAÇÃO / CONSOLE</p><h1>Visão operacional</h1><p>Atendimentos, incidentes e rastreabilidade da decisão.</p></div>
                    <button type="button" className="admin-command" onClick={() => void refresh()} disabled={loading}>Atualizar dados</button>
                </div>
                {error && <p role="alert" className="admin-error">{error}</p>}
                {loading && <p role="status" className="admin-muted">Carregando dados…</p>}

                <section aria-label="Métricas" className="admin-metrics">
                    {[
                        ['Conversas', metrics?.total_conversations],
                        ['Tickets criados', metrics?.tickets_created],
                        ['Respostas com fonte', metrics?.responses_with_source],
                        ['Pedidos bloqueados', metrics?.blocked_requests],
                    ].map(([label, value]) => <div className="admin-metric" key={label}><span>{label}</span><strong>{value ?? '—'}</strong></div>)}
                </section>

                <div className="admin-layout">
                    <div className="admin-column">
                        <section className="admin-section admin-conversations" aria-labelledby="conversations-heading">
                            <div className="admin-section-heading"><h2 id="conversations-heading">Conversas</h2><span>{conversations ? `${conversations.total} no total` : '—'}</span></div>
                            {conversations?.items.length === 0 && <p className="admin-muted">Nenhuma conversa registrada.</p>}
                            {conversations?.items.map((conversation) => {
                                const state = conversationState(conversation)
                                return <article className="admin-row" key={conversation.session_id}>
                                    <div><strong>Conversa {conversation.session_id.slice(0, 8)}</strong><span className="admin-row-meta">{dateLabel(conversation.last_activity_at)} · <span className={`admin-state ${state.tone}`}>{state.label}</span>{conversation.last_run?.error_code ? ` · ${conversation.last_run.error_code}` : ''}</span></div>
                                    <button type="button" className="admin-text-button" onClick={() => void openSession(conversation.session_id)}>Ver detalhes</button>
                                </article>
                            })}
                            {conversations && conversations.total > pageSize && <div className="admin-pagination">
                                <button type="button" disabled={loading || conversationOffset === 0} onClick={() => void loadConversations(Math.max(0, conversationOffset - pageSize))}>Anterior</button>
                                <span>{conversationOffset + 1}–{Math.min(conversationOffset + pageSize, conversations.total)} de {conversations.total}</span>
                                <button type="button" disabled={loading || conversationOffset + pageSize >= conversations.total} onClick={() => void loadConversations(conversationOffset + pageSize)}>Próxima</button>
                            </div>}
                        </section>
                        <section className="admin-section" aria-labelledby="tickets-heading">
                            <div className="admin-section-heading"><h2 id="tickets-heading">Tickets</h2><span>{tickets ? `${tickets.total} no total` : '—'}</span></div>
                            {tickets?.items.length === 0 && <p className="admin-muted">Nenhum ticket registrado.</p>}
                            {tickets?.items.map((ticket) => <article className="admin-row" key={ticket.ticket_id}>
                                <div><strong>{ticket.servicenow_number || ticket.ticket_id}</strong><span>{ticket.internal_category} · {dateLabel(ticket.created_at)}</span></div>
                                <span className={`admin-state ${ticket.status}`}>{ticketStatusLabels[ticket.status] || ticket.status}</span>
                                <button type="button" className="admin-text-button" onClick={() => void openSession(ticket.session_id)}>Ver conversa</button>
                                <button type="button" className="admin-text-button" onClick={() => void openRun(ticket.agent_run_id)}>Ver eventos</button>
                            </article>)}
                            {tickets && tickets.total > pageSize && <div className="admin-pagination">
                                <button type="button" disabled={loading || offset === 0} onClick={() => { const next = Math.max(0, offset - pageSize); setOffset(next); void refresh(next) }}>Anterior</button>
                                <span>{offset + 1}–{Math.min(offset + pageSize, tickets.total)} de {tickets.total}</span>
                                <button type="button" disabled={loading || offset + pageSize >= tickets.total} onClick={() => { const next = offset + pageSize; setOffset(next); void refresh(next) }}>Próxima</button>
                            </div>}
                        </section>

                        <section className="admin-section" aria-labelledby="sources-heading">
                            <div className="admin-section-heading"><h2 id="sources-heading">Fontes de conhecimento</h2><span>{sources?.length ?? '—'}</span></div>
                            {sources?.length === 0 && <p className="admin-muted">Nenhuma fonte cadastrada.</p>}
                            {sources?.map((source) => <div className="admin-row" key={source.path}>
                                <div><strong>{source.title}</strong><span>{source.path} · {source.internal_category}</span></div>
                                <span className={`admin-state ${source.approved ? 'created' : ''}`}>{source.approved ? 'Aprovada' : 'Pendente'}</span>
                            </div>)}
                        </section>
                    </div>

                    <section className="admin-section admin-detail" aria-labelledby="conversation-heading">
                        <div className="admin-section-heading"><h2 id="conversation-heading">Conversa e decisões</h2></div>
                        <form className="admin-lookup" onSubmit={lookup}>
                            <label htmlFor="session-id">ID da conversa</label>
                            <div><input id="session-id" value={sessionInput} onChange={(event) => setSessionInput(event.target.value)} placeholder="Cole o ID da conversa" /><button type="submit" disabled={!sessionInput.trim() || detailLoading}>Consultar</button></div>
                        </form>
                        {!history && !run && !detailLoading && !detailError && <p className="admin-muted admin-detail-empty">Selecione uma conversa ou um ticket para ver o histórico.</p>}
                        {detailLoading && <p role="status" className="admin-muted">Carregando detalhes…</p>}
                        {detailError && <p role="alert" className="admin-error">{detailError}</p>}
                        {history && <div className="admin-history">
                            <p className="admin-id">Conversa {history.session_id}</p>
                            <p className="admin-muted">{conversationStatusLabels[history.status] || history.status} · Criada em {dateLabel(history.created_at)} · Atualizada em {dateLabel(history.updated_at)}</p>
                            {history.messages.length === 0 && <p className="admin-muted">Ainda não há mensagens.</p>}
                            {history.messages.map((message) => <div className="admin-message" key={message.message_id}>
                                <span>{message.role === 'user' ? 'Solicitante' : 'Suporte'} · {dateLabel(message.created_at)}</span>
                                <p>{message.message_pt_br}</p>
                            </div>)}
                            <h3>Decisões e execuções</h3>
                            {history.runs.length === 0 && <p className="admin-muted">Nenhuma execução registrada.</p>}
                            {history.runs.map((execution) => <div className="admin-turn" key={execution.agent_run_id}>
                                <div><strong className={`admin-state ${execution.status === 'failed' ? 'failed' : execution.final_action === 'blocked' ? 'blocked' : ''}`}>{execution.status === 'failed' ? conversationStatusLabels.failed : execution.final_action ? actionLabels[execution.final_action] : conversationStatusLabels[execution.status] || execution.status}</strong><span>{execution.summary || execution.error_code || execution.status} · {dateLabel(execution.started_at)}</span></div>
                                <button type="button" className="admin-text-button" onClick={() => void openRun(execution.agent_run_id)}>Ver eventos</button>
                                {history.tickets.filter((ticket) => ticket.agent_run_id === execution.agent_run_id).map((ticket) => <p key={ticket.ticket_id}>Ticket: {ticket.servicenow_number || ticket.ticket_id} · {ticketStatusLabels[ticket.status] || ticket.status}{ticket.error_code ? ` · ${ticket.error_code}` : ''}</p>)}
                                {execution.sources.map((source) => <p key={source.path}>Fonte: {source.title} · {source.path}</p>)}
                            </div>)}
                        </div>}
                        {run && <div className="admin-events"><h3>Eventos da execução</h3><p className="admin-id">{run.agent_run_id} · {run.status}{run.error_code ? ` · ${run.error_code}` : ''}</p>
                            {run.events.length === 0 && <p className="admin-muted">Nenhum evento registrado.</p>}
                            {run.events.map((event) => <div className="admin-event" key={event.event_id}>
                                <strong>{event.producer} · {event.task_id}</strong><span>{event.status} · {dateLabel(event.created_at)}</span>
                                {event.payload != null && <pre>{JSON.stringify(event.payload, null, 2)}</pre>}
                                {event.validation_errors != null && <pre>{JSON.stringify(event.validation_errors, null, 2)}</pre>}
                            </div>)}
                        </div>}
                    </section>
                </div>
            </main>
        </div>
    )
}