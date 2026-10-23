export type RunInput = { message_text: string }
export type AuthUser = { user_id: string; email: string; display_name: string; role: 'user' | 'admin'; must_change_password: boolean }
export type ManagedUser = AuthUser & { is_active: boolean; created_at: string; updated_at: string; login_locked: boolean; login_locks: { ip: string; locked_at: string }[] }
export type RunStatus = 'idle' | 'running' | 'done'
export type FinalAction = 'respond' | 'ask_clarification' | 'open_ticket' | 'blocked'
export type RunError = { code: string; message: string; retryable: boolean }
export type RunResult = {
    agent_run_id: string
    final_action: FinalAction
    message_pt_br: string
    summary: string
    sources: { title: string; path: string; snippet: string }[]
    ticket: { status: string; adapter_mode?: string; servicenow_number: string | null } | null
}
export type ChatHistory = {
    session_id: string
    messages: { message_id: string; agent_run_id: string | null; role: 'user' | 'assistant'; message_pt_br: string; created_at: string }[]
    turns: RunResult[]
    outcomes: { agent_run_id: string; code: string; message_pt_br: string }[]
}

export type AdminConversation = {
    session_id: string
    owner?: { display_name: string; email: string }
    status: string
    created_at: string
    updated_at: string
    last_activity_at: string
    last_run: { final_action: FinalAction | null; run_status: string; error_code: string | null } | null
}
export type AdminConversationPage = { items: AdminConversation[]; total: number }
export type AdminConversationDetail = {
    session_id: string
    owner?: { display_name: string; email: string }
    status: string
    created_at: string
    updated_at: string
    messages: { message_id: string; agent_run_id: string | null; role: 'user' | 'assistant'; message_pt_br: string; created_at: string }[]
    runs: {
        agent_run_id: string
        status: string
        started_at: string
        finished_at: string | null
        final_action: FinalAction | null
        error_code: string | null
        summary: string | null
        sources: { title: string; path: string; snippet: string }[]
    }[]
    tickets: { ticket_id: string; agent_run_id: string; status: string; adapter_mode?: string; error_code: string | null; servicenow_number: string | null; created_at: string; updated_at: string }[]
}

export type Ticket = {
    ticket_id: string
    session_id: string
    agent_run_id: string
    status: string
    adapter_mode?: string
    servicenow_number: string | null
    internal_category: string
    resulting_priority: string | null
    created_at: string
}
export type TicketPage = { items: Ticket[]; total: number }
export type SubmissionState = 'prepared' | 'attempted' | 'rejected' | 'uncertain' | 'created' | 'simulated'
export type AdminTicket = Ticket & {
    error_code: string | null
    submission_state: SubmissionState
    submission_started_at: string | null
    redacted_payload: { short_description: string | null; description: string | null; impact: number | null; urgency: number | null; category: string | null }
}
export type Metrics = {
    total_conversations: number
    tickets_created: number
    tickets_simulated?: number
    responses_with_source: number
    blocked_requests: number
}
export type KnowledgeSource = { title: string; path: string; internal_category: string; approved: boolean }
export type AgentEvent = {
    event_id: string
    task_id: string
    producer: string
    status: string
    created_at: string
    payload: unknown
    validation_errors: unknown
}
export type AgentRun = {
    agent_run_id: string
    session_id: string
    status: string
    started_at: string
    finished_at: string | null
    final_action: FinalAction | null
    error_code: string | null
    events: AgentEvent[]
}

export type IaResult = FinalAction | 'failed' | 'running'
export type IaFilters = { start_date: string; end_date: string; model: string; step: string; result: string }
export type IaMeasure = { value: number | null; sample_size: number }
export type IaSummary = {
    executions: number | null
    available_models: string[]
    results: Record<IaResult, number | null>
    terminal_sample_size: number
    result_percentages: Record<'respond' | 'open_ticket' | 'blocked', number | null>
    estimated_cost: IaMeasure & { currency: 'USD' | null; required_rows: number }
    stage_mean_ms: IaMeasure
    stage_p95_ms: IaMeasure
    step_failures: number | null
    observed_model_attempts: number | null
    operational_retries: number | null
    replays: number | null
}
export type IaDetail = {
    agent_run_id: string; session_id: string | null; step_name: string | null; model: string | null; deployment_id?: string | null
    start_time: string | null; end_time: string | null; duration_ms: number | null
    tokens_input: number | null; tokens_output: number | null; tokens_cache: number | null; tokens_cache_write: number | null
    estimated_cost_value: number | null; estimated_cost_currency: 'USD' | null
    estimated_cost_validity_start: string | null; estimated_cost_validity_end: string | null
    attempt_count: number | null; retry_count: number | null; replay_count: number | null
    state: string
}
export type IaDetailsPage = { items: IaDetail[]; total: number }
export type IaTimeseries = {
    executions: { date: string; count: number | null }[]
    results: { result: IaResult; count: number | null }[]
    stages: { step_name: string; mean_ms: number | null; p95_ms: number | null; max_ms: number | null; sample_size: number }[]
}
export type IaPricingConfig = {
    items: { model: string; deployment_id: string; currency: string; token_type: string; rate_per_million: number; valid_from: string; valid_until: string | null; active: boolean }[]
    reference_prices?: { model: string | null; deployment_id: string | null; currency: 'USD'; token_type: string; rate_per_million: string; valid_from: string | null; valid_until: string | null; active: false }[]
}

type Envelope<T> = { data: T | null; error: RunError | null }

type ApiIaSummary = {
    total_runs: number; results: Record<IaResult, { count: number; percentage: number | null }>
    terminal_denominator: number; duration: { sample_size: number; average_ms: number | null; p95_ms: number | null }
    estimated_cost_value: number | null; estimated_cost_currency: 'USD' | null; cost_sample_size: number; cost_required_rows: number
    available_models: string[]; step_failures: number | null; observed_model_attempts: number | null
    operational_retries: number | null; replays: number | null
}
type ApiIaDetail = Omit<IaDetail, 'model'> & { model_used: string | null }
type ApiIaTimeseries = {
    days: { date: string; results: Record<IaResult, number> }[]
    stage_latency: Record<string, { average_ms: number | null; p95_ms: number | null; max_ms: number | null; sample_size: number }>
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
    let response: Response
    try {
        response = await fetch(path, options?.method && options.method !== 'GET' ? {
            ...options, credentials: 'same-origin', headers: { Origin: window.location.origin, ...options.headers },
        } : options ? { ...options, credentials: 'same-origin' } : undefined)
    } catch {
        throw { code: 'NETWORK_ERROR', message: 'Não foi possível conectar ao atendimento.', retryable: true } satisfies RunError
    }

    let envelope: Envelope<T>
    try {
        envelope = await response.json() as Envelope<T>
    } catch {
        throw { code: 'INVALID_RESPONSE', message: 'Resposta inválida do atendimento.', retryable: true } satisfies RunError
    }
    if (response.status === 401 && path !== '/api/auth/login' && path !== '/api/auth/me') window.dispatchEvent(new Event('auth-expired'))
    if (!response.ok || envelope.error || !envelope.data) {
        throw envelope.error ?? { code: 'INVALID_RESPONSE', message: 'Resposta inválida do atendimento.', retryable: true } satisfies RunError
    }
    return envelope.data
}

export const getCurrentUser = () => request<{ user: AuthUser }>('/api/auth/me').then(({ user }) => user)
export const loginUser = (email: string, password: string) => request<{ user: AuthUser }>('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }),
}).then(({ user }) => user)
export const logoutUser = () => request<object>('/api/auth/logout', { method: 'POST' })
export const changePassword = (current_password: string, new_password: string) => request<{ user: AuthUser }>('/api/auth/change-password', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password, new_password }),
}).then(({ user }) => user)
export const listOwnSessions = (limit = 100, offset = 0) => request<{ items: { session_id: string }[]; total: number }>(`/api/chat/sessions?limit=${limit}&offset=${offset}`)
export const listUsers = (query: string) => request<{ items: ManagedUser[]; total: number }>(`/api/admin/users?${query}`)
export const createUser = (input: { email: string; display_name: string; role: 'user' | 'admin'; temporary_password: string }) =>
    request<ManagedUser>('/api/admin/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
export const updateUser = (id: string, input: Partial<Pick<ManagedUser, 'display_name' | 'role' | 'is_active'>>) =>
    request<ManagedUser>(`/api/admin/users/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
export const resetUserPassword = (id: string, temporary_password: string) =>
    request<ManagedUser>(`/api/admin/users/${encodeURIComponent(id)}/reset-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ temporary_password }) })
export const unlockLogin = (email: string, ip: string) =>
    request<object>('/api/admin/login-locks/unlock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, ip }) })

export async function createSession(): Promise<string> {
    const session = await request<{ session_id: string }>('/api/chat/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
    })
    return session.session_id
}

export function getSession(sessionId: string): Promise<ChatHistory> {
    return request<ChatHistory>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`)
}

export function getAdminConversations(limit = 20, offset = 0): Promise<AdminConversationPage> {
    return request<AdminConversationPage>(`/api/admin/conversations?limit=${limit}&offset=${offset}`)
}

export function getAdminConversation(sessionId: string): Promise<AdminConversationDetail> {
    return request<AdminConversationDetail>(`/api/admin/conversations/${encodeURIComponent(sessionId)}`)
}

export function sendMessage(sessionId: string, input: RunInput, key: string): Promise<RunResult> {
    return request<RunResult>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify(input),
    })
}

export function getTickets(limit = 20, offset = 0): Promise<TicketPage> {
    return request<TicketPage>(`/api/tickets?limit=${limit}&offset=${offset}`)
}

export function getMetrics(): Promise<Metrics> {
    return request<Metrics>('/api/metrics/summary')
}

export function getKnowledgeSources(): Promise<{ items: KnowledgeSource[] }> {
    return request<{ items: KnowledgeSource[] }>('/api/knowledge/sources')
}

export function getAdminTicket(ticketId: string): Promise<AdminTicket> {
    return request<AdminTicket>(`/api/admin/tickets/${encodeURIComponent(ticketId)}`)
}

export function getAgentRun(agentRunId: string): Promise<AgentRun> {
    return request<AgentRun>(`/api/agent-runs/${encodeURIComponent(agentRunId)}`)
}

function iaQuery(filters: IaFilters): string {
    const query = new URLSearchParams()
    if (filters.start_date) query.set('start', `${filters.start_date}T00:00:00Z`)
    if (filters.end_date) {
        const nextDay = new Date(`${filters.end_date}T00:00:00Z`)
        nextDay.setUTCDate(nextDay.getUTCDate() + 1)
        query.set('end', nextDay.toISOString())
    }
    for (const key of ['model', 'step', 'result'] as const) {
        if (filters[key]) query.set(key, filters[key])
    }
    return query.toString()
}

export function getIaSummary(filters: IaFilters): Promise<IaSummary> {
    const query = iaQuery(filters)
    return request<ApiIaSummary>(`/api/ia-tab/summary${query ? `?${query}` : ''}`).then((data) => ({
        executions: data.total_runs,
        available_models: data.available_models,
        results: Object.fromEntries(Object.entries(data.results).map(([key, value]) => [key, value.count])) as IaSummary['results'],
        terminal_sample_size: data.terminal_denominator,
        result_percentages: Object.fromEntries(['respond', 'open_ticket', 'blocked'].map((key) => [key, data.results[key as IaResult].percentage])) as IaSummary['result_percentages'],
        estimated_cost: { value: data.estimated_cost_value, currency: data.estimated_cost_currency, sample_size: data.cost_sample_size, required_rows: data.cost_required_rows },
        stage_mean_ms: { value: data.duration.average_ms, sample_size: data.duration.sample_size },
        stage_p95_ms: { value: data.duration.p95_ms, sample_size: data.duration.sample_size },
        step_failures: data.step_failures,
        observed_model_attempts: data.observed_model_attempts,
        operational_retries: data.operational_retries,
        replays: data.replays,
    }))
}

export function getIaDetails(filters: IaFilters, limit = 20, offset = 0): Promise<IaDetailsPage> {
    const query = new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(iaQuery(filters))), limit: String(limit), offset: String(offset) })
    return request<{ items: ApiIaDetail[]; total: number }>(`/api/ia-tab/details?${query}`).then((data) => ({
        total: data.total, items: data.items.map(({ model_used, ...item }) => ({ ...item, model: model_used })),
    }))
}

export function getIaTimeseries(filters: IaFilters): Promise<IaTimeseries> {
    const query = iaQuery(filters)
    return request<ApiIaTimeseries>(`/api/ia-tab/timeseries${query ? `?${query}` : ''}`).then((data) => ({
        executions: data.days.map((day) => ({ date: day.date, count: Object.values(day.results).reduce((total, count) => total + count, 0) })),
        results: [],
        stages: Object.entries(data.stage_latency).map(([step_name, stats]) => ({
            step_name, mean_ms: stats.average_ms, p95_ms: stats.p95_ms, max_ms: stats.max_ms, sample_size: stats.sample_size,
        })).filter((stage) => stage.sample_size > 0),
    }))
}

export function getIaPricingConfig(): Promise<IaPricingConfig> {
    return request<IaPricingConfig>('/api/ia-tab/pricing-config')
}