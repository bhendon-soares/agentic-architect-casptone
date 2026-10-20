import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import AdminConsole from './AdminConsole'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const turn = {
  session_id: 'session-1', agent_run_id: 'run-1', final_action: 'respond',
  summary: 'Orientação disponível na fonte local.',
  message_pt_br: 'Use o fluxo oficial de redefinição de senha.',
  sources: [{ title: 'Redefinição de senha', path: 'knowledge/password_reset.md', snippet: 'Use o fluxo oficial.' }],
  ticket: null,
}

function reply(data: unknown, status = 200) {
  return { ok: status < 400, json: async () => ({ data: status < 400 ? data : null, error: status < 400 ? null : data }) } as Response
}

test('creates a session, posts the message and displays the sourced result', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' })).mockResolvedValueOnce(reply(turn))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)

  const input = screen.getByRole('textbox', { name: 'Descreva seu problema' }) as HTMLTextAreaElement
  const submitted = input.value
  expect(submitted).toContain('Esqueci a senha')
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))

  expect(screen.getByText('Atendimento: em andamento')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Reiniciar' }).hasAttribute('disabled')).toBe(true)
  expect(screen.getByRole('button', { name: 'Em andamento…' }).hasAttribute('disabled')).toBe(true)
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getByText(submitted)).toBeTruthy()

  expect(await screen.findByText('Atendimento: concluído')).toBeTruthy()
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/chat/sessions', expect.objectContaining({ method: 'POST' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/chat/sessions/session-1/messages', expect.objectContaining({ body: JSON.stringify({ message_text: submitted }) }))
  expect(screen.getByText('Redefinição de senha')).toBeTruthy()
  expect(screen.getByText('knowledge/password_reset.md')).toBeTruthy()
  expect(screen.getByText(/Use o fluxo oficial de redefinição de senha/)).toBeTruthy()
  expect(JSON.parse(localStorage.getItem('support-chat-sessions')!)).toEqual(['session-1'])
})

test.each([
  ['respond', 'Orientação disponível.', null],
  ['ask_clarification', 'Qual conta apresenta o problema?', null],
  ['open_ticket', 'Incidente criado.', { servicenow_number: 'INC0010001', status: 'created' }],
  ['blocked', 'Não posso ajudar com esse pedido.', null],
])('renders the %s result without treating it as an error', async (finalAction, answer, ticket) => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ ...turn, final_action: finalAction, message_pt_br: answer, ticket, sources: finalAction === 'respond' ? turn.sources : [] }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByText(answer)).toBeTruthy()
  expect(screen.getByText('Atendimento: concluído')).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  if (ticket) expect(screen.getByText(/INC0010001.*Criado/)).toBeTruthy()
  if (finalAction === 'respond') expect(screen.getByRole('complementary', { name: 'Fonte da orientação' })).toBeTruthy()
})

test('shows progress without a lost-key warning while a message is in flight', async () => {
  let resolveTurn!: (response: Response) => void
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveTurn = resolve }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByText('Consultando a orientação local…')).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  resolveTurn(reply(turn))
  expect(await screen.findByText(turn.message_pt_br)).toBeTruthy()
})

test('restarts in a new session and restores the old conversation from the server', async () => {
  const history = {
    session_id: 'session-1', turns: [turn],
    messages: [
      { message_id: 'user-1', role: 'user', message_pt_br: 'Mensagem anterior', created_at: '2026-10-15T10:00:00Z' },
      { message_id: 'assistant-1', role: 'assistant', message_pt_br: turn.message_pt_br, created_at: '2026-10-15T10:00:01Z' },
    ],
  }
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply(turn)).mockResolvedValueOnce(reply({ session_id: 'session-2' }))
    .mockResolvedValueOnce(reply(history))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByText('Atendimento: concluído')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Reiniciar' }))
  expect(await screen.findByRole('button', { name: 'Conversa 2' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Conversa 2' }).getAttribute('aria-current')).toBe('page')
  expect(screen.queryByText('Redefinição de senha')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Conversa 1' }))
  expect(await screen.findByText('Mensagem anterior')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Conversa 1' }).getAttribute('aria-current')).toBe('page')
  expect(fetchMock).toHaveBeenLastCalledWith('/api/chat/sessions/session-1', undefined)
  expect(JSON.parse(localStorage.getItem('support-chat-sessions')!)).toEqual(['session-2', 'session-1'])
})

test('loads a saved conversation after reopening the page', async () => {
  localStorage.setItem('support-chat-sessions', JSON.stringify(['session-1']))
  const fetchMock = vi.fn().mockResolvedValue(reply({
    session_id: 'session-1', turns: [turn],
    messages: [
      { message_id: 'user-1', role: 'user', message_pt_br: 'Mensagem salva', created_at: '2026-10-15T10:00:00Z' },
      { message_id: 'assistant-1', role: 'assistant', message_pt_br: turn.message_pt_br, created_at: '2026-10-15T10:00:01Z' },
    ],
  }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  expect(await screen.findByText('Mensagem salva')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/chat/sessions/session-1', undefined)
})

test('keeps the missing-data outcome visible after reload without technical retry', async () => {
  const notice = 'Ainda faltam dados. Procure o suporte pelo canal oficial.'
  const history = {
    session_id: 'session-1', turns: [],
    messages: [{ message_id: 'user-1', agent_run_id: 'run-1', role: 'user', message_pt_br: 'Ainda não sei', created_at: '2026-10-15T10:00:00Z' }],
    outcomes: [{ agent_run_id: 'run-1', code: 'MINIMUM_TICKET_DATA_MISSING', message_pt_br: notice }],
  }
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'MINIMUM_TICKET_DATA_MISSING', message: notice, retryable: false }, 422))
    .mockResolvedValueOnce(reply(history))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByText(notice)).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  cleanup()
  render(<App />)
  expect(await screen.findByText(notice)).toBeTruthy()
  expect(screen.getByText('Ainda não sei')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('retries a failed ticket with the same idempotency key and without a second user message', async () => {
  const failed = { code: 'TICKET_OUTCOME_UNKNOWN', message: 'Consulte o suporte.', retryable: false }
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply(failed, 504)).mockResolvedValueOnce(reply(failed, 504))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  expect(screen.getByRole('button', { name: 'Executar' }).hasAttribute('disabled')).toBe(true)
  const firstOptions = fetchMock.mock.calls[1][1] as RequestInit
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeTruthy()
  const secondOptions = fetchMock.mock.calls[2][1] as RequestInit
  expect(secondOptions.headers).toEqual(firstOptions.headers)
  expect(secondOptions.body).toEqual(firstOptions.body)
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getAllByText(/Esqueci a senha/)).toHaveLength(1)
})

test.each(['TICKET_CREATE_FAILED', 'TICKET_OUTCOME_UNKNOWN'])('prevents a new POST after %s even if the draft is edited', async (code) => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code, message: 'Consulte o suporte.', retryable: false }, 502))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  fireEvent.change(screen.getByRole('textbox', { name: 'Descreva seu problema' }), { target: { value: 'Outro texto' } })
  expect(screen.getByRole('button', { name: 'Executar' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('does not offer a fresh POST or retry after reloading an uncertain ticket', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'TICKET_OUTCOME_UNKNOWN', message: 'Resultado incerto.', retryable: false }, 504))
    .mockResolvedValueOnce(reply({ session_id: 'session-1', turns: [], messages: [] }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Resultado incerto'))
  cleanup()
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Executar' }).hasAttribute('disabled')).toBe(true)
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('allows a new message after a non-ticket API failure', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'INVALID_INPUT', message: 'Revise a mensagem.', retryable: true }, 400))
    .mockResolvedValueOnce(reply(turn))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Revise a mensagem'))
  fireEvent.change(screen.getByRole('textbox', { name: 'Descreva seu problema' }), { target: { value: 'Mensagem revisada' } })
  expect(screen.getByRole('button', { name: 'Executar' }).hasAttribute('disabled')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByText(turn.message_pt_br)).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('requires an explicit warning acknowledgment before restarting an uncertain ticket', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'TICKET_OUTCOME_UNKNOWN', message: 'Resultado incerto.', retryable: false }, 504))
  vi.stubGlobal('fetch', fetchMock)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Executar' }))
  expect(await screen.findByRole('alert')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Reiniciar' }))
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Consulte o suporte'))
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button', { name: 'Executar' }).hasAttribute('disabled')).toBe(true)
})

test('admin console loads live metrics, tickets and sources and pages through tickets', async () => {
  const ticket = { ticket_id: 'ticket-1', session_id: 'session-1', agent_run_id: 'run-1', status: 'created', servicenow_number: 'INC-123', internal_category: 'password_reset', created_at: '2026-10-15T10:00:00Z' }
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/metrics/summary') return Promise.resolve(reply({ total_conversations: 4, tickets_created: 1, responses_with_source: 2, blocked_requests: 1 }))
    if (url.includes('/api/admin/conversations?')) return Promise.resolve(reply({ items: [{ session_id: 'session-1', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', last_activity_at: '2026-10-15T10:00:00Z', last_run: { final_action: 'respond', run_status: 'completed', error_code: null } }, { session_id: 'session-2', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', last_activity_at: '2026-10-15T10:00:00Z', last_run: { final_action: 'blocked', run_status: 'completed', error_code: null } }], total: 2 }))
    if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [{ title: 'Redefinição de senha', path: 'knowledge/password_reset.md', internal_category: 'password_reset', approved: true }] }))
    if (url.includes('offset=20')) return Promise.resolve(reply({ items: [], total: 21 }))
    if (url.includes('/api/tickets?')) return Promise.resolve(reply({ items: [ticket], total: 21 }))
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)

  expect(await screen.findByText('INC-123')).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getAllByText('Conversa session-')).toHaveLength(2)
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getByText('Bloqueado').classList.contains('blocked')).toBe(true)
  const metrics = screen.getByRole('region', { name: 'Métricas' })
  for (const [label, value] of [['Conversas', '4'], ['Tickets criados', '1'], ['Respostas com fonte', '2'], ['Pedidos bloqueados', '1']]) {
    expect(within(metrics).getByText(label).parentElement?.textContent).toContain(value)
  }
  expect(screen.getByText('Redefinição de senha')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Próxima' }))
  expect(await screen.findByText('21–21 de 21')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/tickets?limit=20&offset=20', undefined)
})

test('admin console pages through server conversations', async () => {
  const conversation = (id: string) => ({ session_id: id, status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', last_activity_at: '2026-10-15T10:00:00Z', last_run: null })
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/metrics/summary') return Promise.resolve(reply({ total_conversations: 21, tickets_created: 0, responses_with_source: 0, blocked_requests: 0 }))
    if (url === '/api/admin/conversations?limit=20&offset=0') return Promise.resolve(reply({ items: [conversation('session-1')], total: 21 }))
    if (url === '/api/admin/conversations?limit=20&offset=20') return Promise.resolve(reply({ items: [conversation('session-21')], total: 21 }))
    if (url.includes('/api/tickets?')) return Promise.resolve(reply({ items: [], total: 0 }))
    if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [] }))
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  const list = screen.getByRole('region', { name: 'Conversas' })
  expect(await within(list).findByText('Conversa session-')).toBeTruthy()
  fireEvent.click(within(list).getByRole('button', { name: 'Próxima' }))
  expect(await within(list).findByText('21–21 de 21')).toBeTruthy()
  expect(within(list).getByText('Conversa session-')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/admin/conversations?limit=20&offset=20', undefined)
  expect(within(list).getByRole('button', { name: 'Próxima' }).hasAttribute('disabled')).toBe(true)
})

test('admin console shows a conversation, decision and agent events', async () => {
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/metrics/summary') return Promise.resolve(reply({ total_conversations: 1, tickets_created: 0, responses_with_source: 1, blocked_requests: 0 }))
    if (url.includes('/api/admin/conversations?')) return Promise.resolve(reply({ items: [{ session_id: 'session-1', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', last_activity_at: '2026-10-15T10:00:00Z', last_run: { final_action: 'respond', run_status: 'completed', error_code: null } }], total: 1 }))
    if (url.includes('/api/tickets?')) return Promise.resolve(reply({ items: [], total: 0 }))
    if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [] }))
    if (url === '/api/admin/conversations/session-1') return Promise.resolve(reply({ session_id: 'session-1', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', messages: [{ message_id: 'msg-1', role: 'user', message_pt_br: 'Preciso de ajuda', created_at: '2026-10-15T10:00:00Z' }], runs: [{ agent_run_id: 'run-1', status: 'completed', started_at: '2026-10-15T10:00:00Z', finished_at: null, final_action: 'respond', error_code: null, summary: turn.summary, sources: turn.sources }], tickets: [] }))
    if (url === '/api/agent-runs/run-1') return Promise.resolve(reply({ agent_run_id: 'run-1', session_id: 'session-1', status: 'completed', error_code: null, events: [{ event_id: 'event-1', task_id: 'triage', producer: 'backend', status: 'completed', created_at: '2026-10-15T10:00:00Z', payload: { category: 'password_reset' }, validation_errors: null }] }))
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  expect(await screen.findByText('Conversa session-')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ver detalhes' }))
  expect(await screen.findByText('Preciso de ajuda')).toBeTruthy()
  expect(screen.getByText(/Orientação disponível na fonte local\./)).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/admin/conversations/session-1', undefined)
  fireEvent.click(screen.getByRole('button', { name: 'Ver eventos' }))
  expect(await screen.findByText('backend · triage')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith('/api/agent-runs/run-1', undefined)
})

test('admin console can inspect a failed ticket run without a completed turn', async () => {
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/metrics/summary') return Promise.resolve(reply({ total_conversations: 1, tickets_created: 0, responses_with_source: 0, blocked_requests: 0 }))
    if (url.includes('/api/admin/conversations?')) return Promise.resolve(reply({ items: [{ session_id: 'session-2', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', last_activity_at: '2026-10-15T10:00:00Z', last_run: { final_action: null, run_status: 'failed', error_code: 'TICKET_OUTCOME_UNKNOWN' } }], total: 1 }))
    if (url.includes('/api/tickets?')) return Promise.resolve(reply({ items: [{ ticket_id: 'ticket-2', session_id: 'session-2', agent_run_id: 'run-2', status: 'outcome_unknown', servicenow_number: null, internal_category: 'password_reset', created_at: '2026-10-15T10:00:00Z' }], total: 1 }))
    if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [] }))
    if (url === '/api/admin/conversations/session-2') return Promise.resolve(reply({ session_id: 'session-2', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', messages: [], runs: [{ agent_run_id: 'run-2', status: 'failed', started_at: '2026-10-15T10:00:00Z', finished_at: null, final_action: null, error_code: 'TICKET_OUTCOME_UNKNOWN', summary: null, sources: [] }], tickets: [{ ticket_id: 'ticket-2', agent_run_id: 'run-2', status: 'outcome_unknown', error_code: 'TICKET_OUTCOME_UNKNOWN', servicenow_number: null, created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z' }] }))
    if (url === '/api/agent-runs/run-2') return Promise.resolve(reply({ agent_run_id: 'run-2', session_id: 'session-2', status: 'failed', error_code: 'TICKET_OUTCOME_UNKNOWN', events: [{ event_id: 'event-2', task_id: 'ticket', producer: 'backend', status: 'outcome_unknown', created_at: '2026-10-15T10:00:00Z', payload: null, validation_errors: null }] }))
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  expect(await screen.findByText('ticket-2')).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getByText('Falhou').classList.contains('failed')).toBe(true)
  fireEvent.click(within(screen.getByRole('region', { name: 'Conversas' })).getByRole('button', { name: 'Ver detalhes' }))
  expect(await screen.findByText('Ainda não há mensagens.')).toBeTruthy()
  fireEvent.click(within(screen.getByRole('region', { name: 'Conversa e decisões' })).getByRole('button', { name: 'Ver eventos' }))
  expect(await screen.findByText('backend · ticket')).toBeTruthy()
  expect(screen.getAllByText(/TICKET_OUTCOME_UNKNOWN/).length).toBeGreaterThan(0)
})

test('admin console keeps available data visible when another request fails', async () => {
  let resolveMetrics!: (response: Response) => void
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/metrics/summary') return new Promise<Response>((resolve) => { resolveMetrics = resolve })
    if (url.includes('/api/tickets?')) return Promise.resolve(reply({ code: 'UNAVAILABLE', message: 'Temporariamente indisponível.', retryable: true }, 503))
    if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [] }))
    if (url.includes('/api/admin/conversations?')) return Promise.resolve(reply({ items: [], total: 0 }))
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  expect(screen.getByRole('status').textContent).toContain('Carregando dados')
  resolveMetrics(reply({ total_conversations: 3, tickets_created: 0, responses_with_source: 1, blocked_requests: 0 }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Alguns dados'))
  expect(within(screen.getByRole('region', { name: 'Métricas' })).getByText('3')).toBeTruthy()
  expect(screen.getByText('Nenhuma conversa registrada.')).toBeTruthy()
})

const iaSummary = {
  executions: 21,
  available_models: ['model-a', 'model-b'],
  results: { respond: 2, open_ticket: 1, blocked: 0, ask_clarification: 1, failed: 1, running: 1 },
  terminal_sample_size: 3,
  result_percentages: { respond: 66.67, open_ticket: 33.33, blocked: 0 },
  estimated_cost: { value: null, currency: null, sample_size: 0 },
  stage_mean_ms: { value: 120, sample_size: 2 },
  stage_p95_ms: { value: null, sample_size: 0 },
  step_failures: 1, observed_model_attempts: null, operational_retries: 1, replays: 0,
}
const iaRow = {
  agent_run_id: 'run-ia', session_id: 'session-ia', step_name: 'triage', model: 'model-a',
  start_time: '2026-10-15T10:00:00Z', end_time: null, duration_ms: null,
  tokens_input: null, tokens_output: 0, tokens_cache: null, estimated_cost_value: null,
  estimated_cost_currency: null, estimated_cost_validity_start: null, estimated_cost_validity_end: null,
  attempt_count: null, retry_count: 1, replay_count: 0, state: 'failed',
}

function iaFetch(url: string): Promise<Response> {
  if (url.startsWith('/api/ia-tab/summary')) return Promise.resolve(reply(iaSummary))
  if (url.startsWith('/api/ia-tab/details?')) return Promise.resolve(reply({ items: [iaRow], total: 21 }))
  if (url.startsWith('/api/ia-tab/timeseries')) return Promise.resolve(reply({ executions: [{ date: '2026-10-15', count: 3 }], results: [], stages: [{ step_name: 'triage', mean_ms: 120, p95_ms: null, max_ms: 160, sample_size: 2 }] }))
  if (url === '/api/ia-tab/pricing-config') return Promise.resolve(reply({ items: [{ model: 'model-a', deployment_id: 'deploy-a', currency: 'USD', token_type: 'input', rate_per_million: 2, valid_from: '2026-10-01', valid_until: null }] }))
  if (url === '/api/admin/conversations/session-ia') return Promise.resolve(reply({ session_id: 'session-ia', status: 'active', created_at: '2026-10-15T10:00:00Z', updated_at: '2026-10-15T10:00:00Z', messages: [], runs: [], tickets: [] }))
  if (url === '/api/agent-runs/run-ia') return Promise.resolve(reply({ agent_run_id: 'run-ia', session_id: 'session-ia', status: 'failed', error_code: null, events: [] }))
  if (url === '/api/metrics/summary') return Promise.resolve(reply({ total_conversations: 0, tickets_created: 0, responses_with_source: 0, blocked_requests: 0 }))
  if (url.startsWith('/api/admin/conversations?') || url.startsWith('/api/tickets?')) return Promise.resolve(reply({ items: [], total: 0 }))
  if (url === '/api/knowledge/sources') return Promise.resolve(reply({ items: [] }))
  return Promise.reject(new Error(`Unexpected URL: ${url}`))
}

test('IA filters and pagination query the server and preserve null versus zero', async () => {
  const fetchMock = vi.fn(iaFetch)
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  expect(await screen.findByRole('region', { name: 'Indicadores IA' })).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Indicadores IA' })).getByText('Custo estimado').parentElement?.textContent).toContain('não disponível')
  expect(screen.getByText('Tentativas reais observadas').parentElement?.parentElement?.textContent).toContain('não disponível')
  expect(screen.getByText('Replays').parentElement?.parentElement?.textContent).toContain('0')
  const filters = screen.getByLabelText('Filtros IA')
  fireEvent.change(within(filters).getByLabelText('Início'), { target: { value: '2026-10-01' } })
  fireEvent.change(within(filters).getByLabelText('Modelo'), { target: { value: 'model-a' } })
  fireEvent.change(within(filters).getByLabelText('Etapa'), { target: { value: 'triage' } })
  fireEvent.change(within(filters).getByLabelText('Resultado'), { target: { value: 'failed' } })
  expect(await screen.findByText('1–20 de 21')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('start_date=2026-10-01&model=model-a&step=triage&result=failed'), undefined)
  fireEvent.click(within(screen.getByRole('region', { name: 'Detalhes por execução e etapa' })).getByRole('button', { name: 'Próxima' }))
  expect(await screen.findByText('21–21 de 21')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/ia-tab/details?start_date=2026-10-01&model=model-a&step=triage&result=failed&limit=20&offset=20'), undefined)
})

test('IA details return to the existing conversation and execution views', async () => {
  vi.stubGlobal('fetch', vi.fn(iaFetch))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  const table = await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })
  fireEvent.click(within(table).getByRole('button', { name: 'Ver conversa' }))
  expect(await screen.findByText('Conversa session-ia')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  fireEvent.click(within(await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })).getByRole('button', { name: 'Ver execução' }))
  expect(await screen.findByText('Eventos da execução')).toBeTruthy()
})

test('IA distinguishes loading, API failure with retry, empty results and missing telemetry', async () => {
  let resolveSummary!: (response: Response) => void
  const fetchMock = vi.fn((url: string) => {
    if (url.startsWith('/api/ia-tab/summary') && fetchMock.mock.calls.filter(([path]) => String(path).startsWith('/api/ia-tab/summary')).length === 1) return new Promise<Response>((resolve) => { resolveSummary = resolve })
    if (url.startsWith('/api/ia-tab/summary')) return Promise.resolve(reply({ ...iaSummary, executions: 0 }))
    return iaFetch(url)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  expect(screen.getByText('Carregando telemetria…')).toBeTruthy()
  resolveSummary(reply({ code: 'UNAVAILABLE', message: 'Indisponível', retryable: true }, 503))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Não foi possível'))
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByText('Nenhuma execução no período selecionado.')).toBeTruthy()
})

test('IA marks existing runs without cost and latency telemetry as unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => url.startsWith('/api/ia-tab/summary')
    ? Promise.resolve(reply({ ...iaSummary, stage_mean_ms: { value: null, sample_size: 0 } })) : iaFetch(url)))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  expect(await screen.findByText(/Existem execuções, mas não há telemetria/)).toBeTruthy()
  expect(screen.queryByText('Nenhuma execução no período selecionado.')).toBeNull()
  expect(within(screen.getByRole('region', { name: 'Detalhes por execução e etapa' })).getByText('run-ia')).toBeTruthy()
})