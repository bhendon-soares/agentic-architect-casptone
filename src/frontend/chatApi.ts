export type RunInput = { message_text: string }
export type RunStatus = 'idle' | 'running' | 'done'
export type FinalAction = 'respond' | 'ask_clarification' | 'open_ticket' | 'blocked'
export type RunError = { code: string; message: string; retryable: boolean }
export type RunResult = {
    agent_run_id: string
    final_action: FinalAction
    message_pt_br: string
    summary: string
    sources: { title: string; path: string; snippet: string }[]
    ticket: { status: string; servicenow_number: string | null } | null
}
export type ChatHistory = {
    session_id: string
    messages: { message_id: string; agent_run_id: string | null; role: 'user' | 'assistant'; message_pt_br: string; created_at: string }[]
    turns: RunResult[]
    outcomes: { agent_run_id: string; code: string; message_pt_br: string }[]
}

export type AdminConversation = {
    session_id: string
    status: string
    created_at: string
    updated_at: string
    last_activity_at: string
    last_run: { final_action: FinalAction | null; run_status: string; error_code: string | null } | null
}
export type AdminConversationPage = { items: AdminConversation[]; total: number }
export type AdminConversationDetail = {
    session_id: string
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
    tickets: { ticket_id: string; agent_run_id: string; status: string; error_code: string | null; servicenow_number: string | null; created_at: string; updated_at: string }[]
}

export type Ticket = {
    ticket_id: string
    session_id: string
    agent_run_id: string
    status: string
    servicenow_number: string | null
    internal_category: string
    created_at: string
}
export type TicketPage = { items: Ticket[]; total: number }
export type Metrics = {
    total_conversations: number
    tickets_created: number
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

type Envelope<T> = { data: T | null; error: RunError | null }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
    let response: Response
    try {
        response = await fetch(path, options)
    } catch {
        throw { code: 'NETWORK_ERROR', message: 'Não foi possível conectar ao atendimento.', retryable: true } satisfies RunError
    }

    let envelope: Envelope<T>
    try {
        envelope = await response.json() as Envelope<T>
    } catch {
        throw { code: 'INVALID_RESPONSE', message: 'Resposta inválida do atendimento.', retryable: true } satisfies RunError
    }
    if (!response.ok || envelope.error || !envelope.data) {
        throw envelope.error ?? { code: 'INVALID_RESPONSE', message: 'Resposta inválida do atendimento.', retryable: true } satisfies RunError
    }
    return envelope.data
}

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

export function getAgentRun(agentRunId: string): Promise<AgentRun> {
    return request<AgentRun>(`/api/agent-runs/${encodeURIComponent(agentRunId)}`)
}