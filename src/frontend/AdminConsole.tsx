import { useEffect, useState, type FormEvent } from 'react'
import {
    getAdminConversation, getAdminConversations, getAdminTicket, getAgentRun, getKnowledgeSources, getMetrics, getTickets,
    type AdminConversation, type AdminConversationDetail, type AdminConversationPage, type AdminTicket, type AgentRun, type AuthUser, type KnowledgeSource, type Metrics, type RunError, type TicketPage,
} from './chatApi'
import IaPanel from './IaPanel'
import UsersPanel from './UsersPanel'
import { ErrorCodeLabel, formatDate, formatNumber, IdChip, KpiCard, SiteHeader, StatusBadge, type Tone } from './ui'
import './style.css'

const pageSize = 20

const actionLabels: Record<string, string> = {
    respond: 'Resposta', ask_clarification: 'Esclarecimento', open_ticket: 'Ticket', blocked: 'Bloqueado',
}
const ticketStatusLabels: Record<string, string> = {
    pending: 'Pendente', created: 'Criado', failed: 'Falhou', outcome_unknown: 'Resultado incerto',
}
const submissionLabels: Record<AdminTicket['submission_state'], { label: string; tone: Tone }> = {
    prepared: { label: 'Apenas preparado, não enviado', tone: 'neutral' },
    attempted: { label: 'Envio iniciado, sem confirmação', tone: 'warning' },
    rejected: { label: 'Envio rejeitado', tone: 'danger' },
    uncertain: { label: 'Resultado do envio incerto', tone: 'warning' },
    created: { label: 'Enviado e criado', tone: 'success' },
    simulated: { label: 'Simulado (mock), não enviado ao ServiceNow', tone: 'neutral' },
}
const simulatedLabel = 'Simulado (não enviado)'
const conversationStatusLabels: Record<string, string> = {
    active: 'Ativa', completed: 'Concluída', running: 'Em andamento', failed: 'Falhou', blocked: 'Bloqueado',
}
const categoryLabels: Record<string, string> = { password_reset: 'Redefinição de senha', app_access: 'Acesso a aplicativo' }
type Tab = 'overview' | 'conversations' | 'tickets' | 'knowledge' | 'ia' | 'users'
const tabs: { id: Tab; label: string }[] = [{ id: 'overview', label: 'Visão geral' }, { id: 'conversations', label: 'Conversas' }, { id: 'tickets', label: 'Tickets' }, { id: 'knowledge', label: 'Conhecimento' }, { id: 'ia', label: 'IA' }, { id: 'users', label: 'Usuários' }]

function conversationState(conversation: AdminConversation): { label: string; tone: Tone } {
    const status = conversation.last_run?.run_status === 'outcome_unknown' ? 'outcome_unknown' : conversation.last_run?.run_status === 'failed' ? 'failed' : conversation.last_run?.final_action || conversation.last_run?.run_status || conversation.status
    return { label: status === 'outcome_unknown' ? 'Resultado incerto' : actionLabels[status] || conversationStatusLabels[status] || 'Estado desconhecido', tone: status === 'failed' ? 'danger' : status === 'outcome_unknown' || status === 'blocked' ? 'warning' : status === 'respond' || status === 'open_ticket' ? 'success' : status === 'running' || status === 'ask_clarification' ? 'info' : 'neutral' }
}

function dateLabel(value: string | null): string {
    return formatDate(value)
}

function errorLabel(cause: unknown): string {
    const error = cause as Partial<RunError>
    return error?.message || 'Não foi possível carregar os dados. Tente novamente.'
}

export default function AdminConsole({ user, onLogout }: { user?: AuthUser; onLogout?: () => void }) {
    const [tab, setTab] = useState<Tab>('overview')
    const [refreshedAt, setRefreshedAt] = useState<string | null>(null)
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
    const [ticketDetail, setTicketDetail] = useState<AdminTicket | null>(null)
    const [ticketLoading, setTicketLoading] = useState(false)
    const [ticketError, setTicketError] = useState<string | null>(null)
    const [ticketId, setTicketId] = useState<string | null>(null)

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
        setRefreshedAt(new Date().toISOString())
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

    async function openTicket(id: string) {
        setTicketId(id)
        setTicketDetail(null)
        setTicketError(null)
        setTicketLoading(true)
        try {
            setTicketDetail(await getAdminTicket(id))
        } catch (cause) {
            setTicketError(errorLabel(cause))
        } finally {
            setTicketLoading(false)
        }
    }

    const run = selectedRun ? runs[selectedRun] : null

    function inspectConversation(id: string) {
        setTab('conversations')
        void openSession(id)
    }

    function inspectRun(id: string) {
        setTab('conversations')
        void openRun(id)
    }

    return (
        <div className="app-shell">
            <SiteHeader user={user} onLogout={onLogout} admin />
            <main className="admin-workspace">
                <nav className="admin-tabs" aria-label="Visões do console">
                    {tabs.map((item) => <button type="button" key={item.id} aria-current={tab === item.id ? 'page' : undefined} onClick={() => setTab(item.id)}>{item.label}</button>)}
                </nav>
                <div className="admin-heading">
                    <div><p className="eyebrow">SUPORTE / CONSOLE</p><h1>{tabs.find((item) => item.id === tab)?.label}</h1>{tab === 'overview' && refreshedAt && <p>Atualizado em {dateLabel(refreshedAt)}</p>}</div>
                    {tab === 'overview' && <button type="button" className="admin-command" onClick={() => void refresh()} disabled={loading}>Atualizar dados</button>}
                </div>
                {tab === 'users' && user ? <UsersPanel admin={user} /> : tab === 'ia' ? <IaPanel onConversation={inspectConversation} onRun={inspectRun} /> : <>
                    {error && <p role="alert" className="admin-error">{error}</p>}
                    {loading && <p role="status" className="admin-muted">Carregando dados…</p>}

                    {tab === 'overview' && <section aria-label="Métricas" className="admin-metrics overview-metrics">
                        {[
                            ['Conversas', metrics?.total_conversations, 'Total de conversas registrado pelo servidor.'],
                            ['Tickets criados', metrics?.tickets_created, 'Incidentes confirmados pelo ServiceNow; não inclui tickets simulados.'],
                            ['Tickets simulados', metrics?.tickets_simulated, 'Tickets do modo mock; nunca enviados ao ServiceNow.'],
                            ['Respostas com fonte', metrics?.responses_with_source, 'Respostas com fonte conforme a contagem do servidor.'],
                            ['Pedidos bloqueados', metrics?.blocked_requests, 'Pedidos barrados pela política; não são falhas técnicas.'],
                        ].map(([label, value, definition]) => <KpiCard key={label} label={String(label)} value={formatNumber(value as number | undefined)} definition={String(definition)} />)}
                    </section>}

                    {(tab === 'conversations' || tab === 'tickets' || tab === 'knowledge') && <div className="admin-layout">
                        <div className="admin-column">
                            {tab === 'conversations' && <section className="admin-section admin-conversations" aria-labelledby="conversations-heading">
                                <div className="admin-section-heading"><h2 id="conversations-heading">Conversas</h2><span>{conversations ? `${conversations.total} no total` : '—'}</span></div>
                                {conversations?.items.length === 0 && <p className="admin-muted">Nenhuma conversa registrada.</p>}
                                {conversations?.items.map((conversation) => {
                                    const state = conversationState(conversation)
                                    return <article className="admin-row" key={conversation.session_id}>
                                        <div><strong>Conversa <IdChip id={conversation.session_id} /></strong>{conversation.owner && <span className="admin-row-meta">{conversation.owner.display_name} · {conversation.owner.email}</span>}<span className="admin-row-meta">{dateLabel(conversation.last_activity_at)} · <StatusBadge tone={state.tone}>{state.label}</StatusBadge> {<ErrorCodeLabel code={conversation.last_run?.error_code ?? null} />}</span></div>
                                        <button type="button" className="admin-text-button" onClick={() => void openSession(conversation.session_id)}>Ver detalhes</button>
                                    </article>
                                })}
                                {conversations && conversations.total > pageSize && <div className="admin-pagination">
                                    <button type="button" disabled={loading || conversationOffset === 0} onClick={() => void loadConversations(Math.max(0, conversationOffset - pageSize))}>Anterior</button>
                                    <span>{conversationOffset + 1}–{Math.min(conversationOffset + pageSize, conversations.total)} de {conversations.total}</span>
                                    <button type="button" disabled={loading || conversationOffset + pageSize >= conversations.total} onClick={() => void loadConversations(conversationOffset + pageSize)}>Próxima</button>
                                </div>}
                            </section>}
                            {tab === 'tickets' && <section className="admin-section" aria-labelledby="tickets-heading">
                                <div className="admin-section-heading"><h2 id="tickets-heading">Tickets</h2><span>{tickets ? `${tickets.total} no total` : '—'}</span></div>
                                {tickets?.items.length === 0 && <p className="admin-muted">Nenhum ticket registrado.</p>}
                                {tickets?.items.map((ticket) => <article className="admin-row" key={ticket.ticket_id}>
                                    <div><strong><IdChip id={ticket.servicenow_number || ticket.ticket_id} /></strong><span>{categoryLabels[ticket.internal_category] || ticket.internal_category} · Prioridade: {ticket.resulting_priority ?? '—'} · {dateLabel(ticket.created_at)}</span></div>
                                    <StatusBadge tone={ticket.status === 'created' && ticket.adapter_mode === 'mock' ? 'neutral' : ticket.status === 'created' && ticket.servicenow_number ? 'success' : ticket.status === 'outcome_unknown' ? 'warning' : ticket.status === 'failed' ? 'danger' : 'neutral'}>{ticket.status === 'created' && ticket.adapter_mode === 'mock' ? simulatedLabel : ticket.status === 'created' && ticket.servicenow_number ? 'Criado' : ticket.status === 'outcome_unknown' ? 'Resultado incerto' : ticket.status === 'failed' ? 'Falhou' : 'Estado a verificar'}</StatusBadge>
                                    <button type="button" className="admin-text-button" onClick={() => void openTicket(ticket.ticket_id)}>Ver ticket</button>
                                    <button type="button" className="admin-text-button" onClick={() => void openSession(ticket.session_id)}>Ver conversa</button>
                                    <button type="button" className="admin-text-button" onClick={() => void openRun(ticket.agent_run_id)}>Ver eventos</button>
                                </article>)}
                                {tickets && tickets.total > pageSize && <div className="admin-pagination">
                                    <button type="button" disabled={loading || offset === 0} onClick={() => { const next = Math.max(0, offset - pageSize); setOffset(next); void refresh(next) }}>Anterior</button>
                                    <span>{offset + 1}–{Math.min(offset + pageSize, tickets.total)} de {tickets.total}</span>
                                    <button type="button" disabled={loading || offset + pageSize >= tickets.total} onClick={() => { const next = offset + pageSize; setOffset(next); void refresh(next) }}>Próxima</button>
                                </div>}
                            </section>}

                            {tab === 'knowledge' && <section className="admin-section" aria-labelledby="sources-heading">
                                <div className="admin-section-heading"><h2 id="sources-heading">Fontes de conhecimento</h2><span>{sources?.length ?? '—'}</span></div>
                                {sources?.length === 0 && <p className="admin-muted">Nenhuma fonte cadastrada.</p>}
                                {sources?.map((source) => <div className="admin-row" key={source.path}>
                                    <div><strong>{source.title}</strong><span>{source.path} · {categoryLabels[source.internal_category] || source.internal_category}</span></div>
                                    <StatusBadge tone={source.approved ? 'success' : 'neutral'}>{source.approved ? 'Aprovada' : 'Pendente'}</StatusBadge>
                                </div>)}
                            </section>}
                        </div>

                        {(tab === 'conversations' || tab === 'tickets') && <section className="admin-section admin-detail" aria-labelledby="conversation-heading">
                            <div className="admin-section-heading"><h2 id="conversation-heading">Conversa e decisões</h2></div>
                            <form className="admin-lookup" onSubmit={lookup}>
                                <label htmlFor="session-id">ID da conversa</label>
                                <div><input id="session-id" value={sessionInput} onChange={(event) => setSessionInput(event.target.value)} placeholder="Cole o ID da conversa" /><button type="submit" disabled={!sessionInput.trim() || detailLoading}>Consultar</button></div>
                            </form>
                            {!history && !run && !ticketId && !detailLoading && !detailError && <p className="admin-muted admin-detail-empty">Selecione uma conversa ou um ticket para ver o histórico.</p>}
                            {detailLoading && <p role="status" className="admin-muted">Carregando detalhes…</p>}
                            {detailError && <p role="alert" className="admin-error">{detailError}</p>}
                            {ticketLoading && <p role="status" className="admin-muted">Carregando ticket…</p>}
                            {ticketError && <p role="alert" className="admin-error">{ticketError}</p>}
                            {ticketDetail && <section className="admin-history" aria-label="Detalhe do ticket">
                                <h3>Detalhe do ticket</h3>
                                <p>Ticket <IdChip id={ticketDetail.servicenow_number || ticketDetail.ticket_id} /> · <StatusBadge tone={submissionLabels[ticketDetail.submission_state]?.tone ?? 'neutral'}>{submissionLabels[ticketDetail.submission_state]?.label ?? 'Estado a verificar'}</StatusBadge></p>
                                <p>Início do envio: {ticketDetail.submission_started_at ? dateLabel(ticketDetail.submission_started_at) : ticketDetail.submission_state === 'prepared' ? 'não iniciado' : 'não registrado (anterior ao registro de envio)'} <ErrorCodeLabel code={ticketDetail.error_code} /></p>
                                <h4>Payload redigido para ServiceNow</h4>
                                <pre>{JSON.stringify(ticketDetail.redacted_payload, null, 2)}</pre>
                            </section>}
                            {history && <div className="admin-history">
                                <p className="admin-id">Conversa <IdChip id={history.session_id} /></p>
                                {history.owner && <p className="admin-muted">Solicitante: {history.owner.display_name} · {history.owner.email}</p>}
                                <p className="admin-muted">{conversationStatusLabels[history.status] || history.status} · Criada em {dateLabel(history.created_at)} · Atualizada em {dateLabel(history.updated_at)}</p>
                                {history.messages.length === 0 && <p className="admin-muted">Ainda não há mensagens.</p>}
                                {history.messages.map((message) => <div className="admin-message" key={message.message_id}>
                                    <span>{message.role === 'user' ? 'Solicitante' : 'Suporte'} · {dateLabel(message.created_at)}</span>
                                    <p>{message.message_pt_br}</p>
                                </div>)}
                                <h3>Decisões e execuções</h3>
                                {history.runs.length === 0 && <p className="admin-muted">Nenhuma execução registrada.</p>}
                                {history.runs.map((execution) => <div className="admin-turn" key={execution.agent_run_id}>
                                    <div><StatusBadge tone={execution.status === 'failed' ? 'danger' : execution.status === 'outcome_unknown' || execution.final_action === 'blocked' ? 'warning' : execution.final_action === 'respond' || execution.final_action === 'open_ticket' ? 'success' : 'info'}>{execution.status === 'failed' ? 'Falhou' : execution.status === 'outcome_unknown' ? 'Resultado incerto' : execution.final_action ? actionLabels[execution.final_action] : conversationStatusLabels[execution.status] || 'Estado desconhecido'}</StatusBadge><span>{execution.summary || execution.status} · {dateLabel(execution.started_at)} <ErrorCodeLabel code={execution.error_code} /></span></div>
                                    <button type="button" className="admin-text-button" onClick={() => void openRun(execution.agent_run_id)}>Ver eventos</button>
                                    {history.tickets.filter((ticket) => ticket.agent_run_id === execution.agent_run_id).map((ticket) => <p key={ticket.ticket_id}>Ticket: {ticket.servicenow_number || ticket.ticket_id} · {ticket.status === 'created' && ticket.adapter_mode === 'mock' ? simulatedLabel : ticket.status === 'created' && ticket.servicenow_number ? 'Criado' : ticketStatusLabels[ticket.status] || 'Estado a verificar'} <ErrorCodeLabel code={ticket.error_code} /> <button type="button" className="admin-text-button" onClick={() => void openTicket(ticket.ticket_id)}>Ver ticket</button></p>)}
                                    {execution.sources.map((source) => <p key={source.path}>Fonte: {source.title} · {source.path}</p>)}
                                </div>)}
                            </div>}
                            {run && <div className="admin-events"><h3>Eventos da execução</h3><p className="admin-id">{run.agent_run_id} · {run.status}{run.error_code ? ` · ${run.error_code}` : ''}</p>
                                {run.events.length === 0 && <p className="admin-muted">Nenhum evento registrado.</p>}
                                {run.events.map((event) => <div className="admin-event" data-agent={event.task_id} key={event.event_id}>
                                    <strong>{event.producer} · {event.task_id}</strong><span>{event.status} · {dateLabel(event.created_at)}</span>
                                    {event.task_id === 'decision' && event.payload != null && typeof event.payload === 'object' && 'final_action' in event.payload && typeof event.payload.final_action === 'string' && <p>Desfecho: {actionLabels[event.payload.final_action] || event.payload.final_action}</p>}
                                    <details><summary>Ver metadados da etapa</summary>{event.payload == null || (Array.isArray(event.payload) && event.payload.length === 0) || (typeof event.payload === 'object' && !Array.isArray(event.payload) && Object.keys(event.payload).length === 0) ? <p>Esta etapa não registrou detalhes</p> : <pre>{JSON.stringify(event.payload, null, 2)}</pre>}{event.validation_errors != null && (!Array.isArray(event.validation_errors) || event.validation_errors.length > 0) && <><p>Erros de validação</p><pre>{JSON.stringify(event.validation_errors, null, 2)}</pre></>}</details>
                                </div>)}
                            </div>}
                        </section>}
                    </div>}
                </>}
            </main>
        </div>
    )
}