import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import AdminConsole from './AdminConsole'

afterEach(() => {
  cleanup()
  localStorage.clear()
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
  expect(within(screen.getByRole('region', { name: 'Métricas' })).getByText('4')).toBeTruthy()
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