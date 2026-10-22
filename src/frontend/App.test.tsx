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

function submitMessage() {
  fireEvent.change(screen.getByRole('textbox', { name: 'Descreva seu problema' }), { target: { value: 'Preciso de ajuda para acessar minha conta.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
}

test('creates a session, posts the message and displays the sourced result', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' })).mockResolvedValueOnce(reply(turn))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  expect(screen.getByRole('link', { name: 'Help Desk TI Multi Agent MVP - voltar ao chat' }).getAttribute('href')).toBe('/')

  const input = screen.getByRole('textbox', { name: 'Descreva seu problema' }) as HTMLTextAreaElement
  expect(input.value).toBe('')
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
  submitMessage()
  const submitted = input.value

  expect(screen.getByText('Atendimento: Em andamento')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Nova conversa' }).hasAttribute('disabled')).toBe(true)
  expect(screen.getByRole('button', { name: 'Em andamento…' }).hasAttribute('disabled')).toBe(true)
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getByText(submitted)).toBeTruthy()

  expect(await screen.findByText('Atendimento: Concluído')).toBeTruthy()
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/chat/sessions', expect.objectContaining({ method: 'POST' }))
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/chat/sessions/session-1/messages', expect.objectContaining({ body: JSON.stringify({ message_text: submitted }) }))
  expect(screen.getByText('Redefinição de senha')).toBeTruthy()
  expect(screen.getByText('Help Desk TI')).toBeTruthy()
  expect(screen.queryByText('Suporte TI · demonstração')).toBeNull()
  expect(screen.queryByText('knowledge/password_reset.md')).toBeNull()
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
  submitMessage()
  expect(await screen.findByText(answer)).toBeTruthy()
  expect(screen.getByText(`Atendimento: ${{ respond: 'Concluído', ask_clarification: 'Aguardando você', open_ticket: 'Ticket aberto', blocked: 'Bloqueado' }[finalAction]}`)).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  if (ticket) expect(screen.getByText('Ticket aberto: INC0010001')).toBeTruthy()
  if (finalAction === 'respond') expect(screen.getByRole('complementary', { name: 'Fonte da orientação' })).toBeTruthy()
})

test('mock ticket is shown as simulated and never as opened or sent', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ ...turn, final_action: 'open_ticket', message_pt_br: 'Registrei um incidente simulado (modo de teste); ele nao foi enviado ao ServiceNow. Referencia: MOCK-1.', ticket: { servicenow_number: 'MOCK-1', status: 'created', adapter_mode: 'mock' }, sources: [] }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
  expect(await screen.findByText('Ticket simulado, não enviado ao ServiceNow: MOCK-1')).toBeTruthy()
  expect(screen.getByText('Atendimento: Ticket simulado (não enviado)')).toBeTruthy()
  expect(screen.queryByText(/Ticket aberto/)).toBeNull()
})

test('shows progress without a lost-key warning while a message is in flight', async () => {
  let resolveTurn!: (response: Response) => void
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveTurn = resolve }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
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
  submitMessage()
  expect(await screen.findByText('Atendimento: Concluído')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Nova conversa' }))
  expect(await screen.findByRole('button', { name: 'session-' })).toBeTruthy()
  expect((screen.getByRole('textbox', { name: 'Descreva seu problema' }) as HTMLTextAreaElement).value).toBe('')
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
  expect(screen.queryByText('Redefinição de senha')).toBeNull()
  fireEvent.click(screen.getAllByRole('button', { name: 'session-' })[1])
  expect(await within(screen.getByRole('region', { name: 'Histórico da conversa' })).findByText('Mensagem anterior')).toBeTruthy()
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
  expect(await within(screen.getByRole('region', { name: 'Histórico da conversa' })).findByText('Mensagem salva')).toBeTruthy()
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
  submitMessage()
  expect(await screen.findByText(notice)).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  cleanup()
  render(<App />)
  expect(await screen.findByText(notice)).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getByText('Ainda não sei')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('retries a failed ticket with the same idempotency key and without a second user message', async () => {
  const failed = { code: 'TICKET_OUTCOME_UNKNOWN', message: 'Consulte o suporte.', retryable: false }
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply(failed, 504)).mockResolvedValueOnce(reply(failed, 504))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
  const firstOptions = fetchMock.mock.calls[1][1] as RequestInit
  fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeTruthy()
  const secondOptions = fetchMock.mock.calls[2][1] as RequestInit
  expect(secondOptions.headers).toEqual(firstOptions.headers)
  expect(secondOptions.body).toEqual(firstOptions.body)
  expect(within(screen.getByRole('region', { name: 'Histórico da conversa' })).getAllByText(/Preciso de ajuda para acessar minha conta/)).toHaveLength(1)
})

test.each(['TICKET_CREATE_FAILED', 'TICKET_OUTCOME_UNKNOWN'])('prevents a new POST after %s even if the draft is edited', async (code) => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code, message: 'Consulte o suporte.', retryable: false }, 502))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  expect(screen.getByText(`Atendimento: ${code === 'TICKET_CREATE_FAILED' ? 'Falhou' : 'Resultado do ticket incerto'}`).classList.contains(code === 'TICKET_CREATE_FAILED' ? 'danger' : 'warning')).toBe(true)
  fireEvent.change(screen.getByRole('textbox', { name: 'Descreva seu problema' }), { target: { value: 'Outro texto' } })
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test('does not offer a fresh POST or retry after reloading an uncertain ticket', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'TICKET_OUTCOME_UNKNOWN', message: 'Resultado incerto.', retryable: false }, 504))
    .mockResolvedValueOnce(reply({ session_id: 'session-1', turns: [], messages: [] }))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Resultado incerto'))
  cleanup()
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Consulte o suporte'))
  expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('allows a new message after a non-ticket API failure', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'INVALID_INPUT', message: 'Revise a mensagem.', retryable: true }, 400))
    .mockResolvedValueOnce(reply(turn))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  submitMessage()
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Revise a mensagem'))
  fireEvent.change(screen.getByRole('textbox', { name: 'Descreva seu problema' }), { target: { value: 'Mensagem revisada' } })
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
  expect(await screen.findByText(turn.message_pt_br)).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

test('requires an explicit warning acknowledgment before restarting an uncertain ticket', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(reply({ session_id: 'session-1' }))
    .mockResolvedValueOnce(reply({ code: 'TICKET_OUTCOME_UNKNOWN', message: 'Resultado incerto.', retryable: false }, 504))
  vi.stubGlobal('fetch', fetchMock)
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  submitMessage()
  expect(await screen.findByRole('alert')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Nova conversa' }))
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Consulte o suporte'))
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button', { name: 'Enviar' }).hasAttribute('disabled')).toBe(true)
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

  expect(await screen.findByRole('region', { name: 'Métricas' })).toBeTruthy()
  const metrics = screen.getByRole('region', { name: 'Métricas' })
  for (const [label, value] of [['Conversas', '4'], ['Tickets criados', '1'], ['Respostas com fonte', '2'], ['Pedidos bloqueados', '1']]) {
    expect(within(metrics).getByText(label).parentElement?.textContent).toContain(value)
  }
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getAllByRole('button', { name: /Copiar ID session-/ })).toHaveLength(2)
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getByText('Bloqueado').classList.contains('warning')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Conhecimento' }))
  expect(screen.getByText('Redefinição de senha')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Tickets' }))
  expect(await screen.findByRole('button', { name: 'Copiar ID INC-123' })).toBeTruthy()
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
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  const list = screen.getByRole('region', { name: 'Conversas' })
  expect(await within(list).findByRole('button', { name: 'Copiar ID session-1' })).toBeTruthy()
  fireEvent.click(within(list).getByRole('button', { name: 'Próxima' }))
  expect(await within(list).findByText('21–21 de 21')).toBeTruthy()
  expect(within(list).getByRole('button', { name: 'Copiar ID session-21' })).toBeTruthy()
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
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  expect(await screen.findByRole('button', { name: 'Copiar ID session-1' })).toBeTruthy()
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
  fireEvent.click(screen.getByRole('button', { name: 'Tickets' }))
  expect(await screen.findByRole('button', { name: 'Copiar ID ticket-2' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  expect(within(screen.getByRole('region', { name: 'Conversas' })).getByText('Falhou').classList.contains('danger')).toBe(true)
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
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  expect(screen.getByText('Nenhuma conversa registrada.')).toBeTruthy()
})

const iaSummary = {
  total_runs: 21,
  available_models: ['model-a', 'model-b'],
  results: { respond: { count: 2, percentage: 66.67 }, open_ticket: { count: 1, percentage: 33.33 }, blocked: { count: 0, percentage: 0 }, ask_clarification: { count: 1, percentage: null }, failed: { count: 1, percentage: null }, running: { count: 1, percentage: null } },
  terminal_denominator: 3,
  estimated_cost_value: null, estimated_cost_currency: null, cost_sample_size: 0, cost_required_rows: 1,
  duration: { average_ms: 120, p95_ms: null, sample_size: 2 },
  step_failures: 1, observed_model_attempts: null, operational_retries: 1, replays: 0,
}
const iaRow = {
  agent_run_id: 'run-ia', session_id: 'session-ia', step_name: 'triage', model_used: 'model-a',
  start_time: '2026-10-15T10:00:00Z', end_time: null, duration_ms: null,
  tokens_input: null, tokens_output: 0, tokens_cache: null, estimated_cost_value: null,
  estimated_cost_currency: null, estimated_cost_validity_start: null, estimated_cost_validity_end: null,
  attempt_count: null, retry_count: 1, replay_count: 0, state: 'failed',
}

function iaFetch(url: string): Promise<Response> {
  if (url.startsWith('/api/ia-tab/summary')) return Promise.resolve(reply(iaSummary))
  if (url.startsWith('/api/ia-tab/details?')) return Promise.resolve(reply({ items: [iaRow], total: 21 }))
  if (url.startsWith('/api/ia-tab/timeseries')) return Promise.resolve(reply({ days: [{ date: '2026-10-15', results: { respond: 2, open_ticket: 1, blocked: 0, ask_clarification: 0, failed: 0, running: 0 } }], stage_latency: { triage: { average_ms: 120, p95_ms: null, max_ms: 160, sample_size: 2 } } }))
  if (url === '/api/ia-tab/pricing-config') return Promise.resolve(reply({
    items: [], reference_prices: [
      { model: 'gpt-6-sol', token_type: 'input', rate_per_million: 2 },
      { model: 'gpt-6-sol', token_type: 'cache', rate_per_million: 0.2 },
      { model: 'gpt-6-sol', token_type: 'cache_write', rate_per_million: 2.5 },
      { model: 'gpt-6-sol', token_type: 'output', rate_per_million: 10 },
    ]
  }))
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
  const prices = screen.getByText('Tarifas de referência (não são custo medido)').parentElement!
  expect(prices.textContent).toContain('US$ 0,20')
  expect(prices.textContent).toContain('US$ 2,50')
  expect(prices.textContent).not.toContain('Exemplos sem cache')
  expect(within(screen.getByRole('region', { name: 'Indicadores IA' })).getByText('Custo estimado').parentElement?.textContent).toContain('não disponível')
  for (const [label, definition] of [
    ['Execuções', 'Quantidade de atendimentos da IA'],
    ['Custo estimado', 'Soma dos custos estimados'],
    ['Latência média de etapa', 'Tempo médio de execução'],
    ['p95 de etapa (nearest-rank)', 'Duração que 95% das etapas'],
  ]) {
    const card = within(screen.getByRole('region', { name: 'Indicadores IA' })).getByText(label).parentElement!
    expect(within(card).getByRole('img').getAttribute('title')).toContain(definition)
  }
  expect(screen.getByText('Tentativas reais observadas').parentElement?.parentElement?.textContent).toContain('não disponível')
  expect(screen.getByText('Replays').parentElement?.parentElement?.textContent).toContain('0')
  const filters = screen.getByLabelText('Filtros IA')
  fireEvent.change(within(filters).getByLabelText('Início'), { target: { value: '2026-10-01' } })
  fireEvent.change(within(filters).getByLabelText('Modelo'), { target: { value: 'model-a' } })
  fireEvent.change(within(filters).getByLabelText('Etapa'), { target: { value: 'triage' } })
  fireEvent.change(within(filters).getByLabelText('Resultado'), { target: { value: 'failed' } })
  expect(await screen.findByText('1–20 de 21')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('start=2026-10-01T00%3A00%3A00Z&model=model-a&step=triage&result=failed'), undefined)
  fireEvent.change(within(filters).getByLabelText('Fim'), { target: { value: '2026-10-15' } })
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('end=2026-10-16T00%3A00%3A00.000Z'), undefined)
  fireEvent.click(within(await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })).getByRole('button', { name: 'Próxima' }))
  expect(await screen.findByText('21–21 de 21')).toBeTruthy()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/ia-tab/details?start=2026-10-01T00%3A00%3A00Z&end=2026-10-16T00%3A00%3A00.000Z&model=model-a&step=triage&result=failed&limit=20&offset=20'), undefined)
})

test('IA details return to the existing conversation and execution views', async () => {
  vi.stubGlobal('fetch', vi.fn(iaFetch))
  render(<AdminConsole />)
  expect(screen.getByRole('link', { name: 'Help Desk TI Multi Agent MVP - voltar ao chat' }).getAttribute('href')).toBe('/')
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  const table = await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })
  fireEvent.click(within(table).getByRole('button', { name: 'Ver conversa' }))
  expect(await screen.findByRole('button', { name: 'Copiar ID session-ia' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  fireEvent.click(within(await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })).getByRole('button', { name: 'Ver execução' }))
  expect(await screen.findByText('Eventos da execução')).toBeTruthy()
})

test('IA distinguishes loading, API failure with retry, empty results and missing telemetry', async () => {
  let resolveSummary!: (response: Response) => void
  const fetchMock = vi.fn((url: string) => {
    if (url.startsWith('/api/ia-tab/summary') && fetchMock.mock.calls.filter(([path]) => String(path).startsWith('/api/ia-tab/summary')).length === 1) return new Promise<Response>((resolve) => { resolveSummary = resolve })
    if (url.startsWith('/api/ia-tab/summary')) return Promise.resolve(reply({ ...iaSummary, total_runs: 0 }))
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
    ? Promise.resolve(reply({ ...iaSummary, duration: { average_ms: null, p95_ms: null, sample_size: 0 } })) : iaFetch(url)))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  expect(await screen.findByText(/Existem execuções, mas não há telemetria/)).toBeTruthy()
  expect(screen.queryByText('Nenhuma execução no período selecionado.')).toBeNull()
  expect(within(screen.getByRole('region', { name: 'Indicadores IA' })).getByText('p95 de etapa (nearest-rank)').parentElement?.textContent).toContain('não disponível')
  expect(within(screen.getByRole('region', { name: 'Detalhes por execução e etapa' })).getByText('run-ia')).toBeTruthy()
})

test('theme selection persists and applies to the page', () => {
  vi.stubGlobal('fetch', vi.fn(iaFetch))
  render(<AdminConsole />)
  fireEvent.change(screen.getByRole('combobox', { name: 'Tema' }), { target: { value: 'dark' } })
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem('support-theme')).toBe('dark')
})

test('IA masks p95 and maximum for a small sample without hiding its mean', async () => {
  vi.stubGlobal('fetch', vi.fn(iaFetch))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  const metrics = await screen.findByRole('region', { name: 'Indicadores IA' })
  expect(within(metrics).getByText('p95 de etapa (nearest-rank)').parentElement?.textContent).toContain('amostra insuficiente')
  expect(within(metrics).getByText('Latência média de etapa').parentElement?.textContent).toContain('120 ms')
  expect(screen.getByRole('region', { name: 'Latência por etapa' }).textContent).toContain('120 ms · amostra insuficiente · amostra insuficiente')
})

test('IA shows server-estimated cost and sample separately from reference prices', async () => {
  const row = { ...iaRow, state: 'complete', deployment_id: 'deployment-a', tokens_input: 40, tokens_output: 0, tokens_cache: 0, tokens_cache_write: 0, estimated_cost_value: 0.00008, estimated_cost_currency: 'USD', estimated_cost_validity_start: '2026-10-01T00:00:00Z' }
  vi.stubGlobal('fetch', vi.fn((url: string) => url.startsWith('/api/ia-tab/summary')
    ? Promise.resolve(reply({ ...iaSummary, estimated_cost_value: 0.00008, estimated_cost_currency: 'USD', cost_sample_size: 1 }))
    : url.startsWith('/api/ia-tab/details?') ? Promise.resolve(reply({ items: [row], total: 1 })) : iaFetch(url)))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  const table = await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })
  expect(table.textContent).toContain('USD 0,00008 (estimativa)')
  expect(table.textContent).toContain('Etapa · amostra 1 · USD')
  expect(screen.getByText(/Amostras: custo 1 de 1 etapas/)).toBeTruthy()
  expect(screen.getByText('Tarifas de referência (não são custo medido)')).toBeTruthy()
})

test('IA explains missing cost and uses dashes for null without erasing measured zero', async () => {
  vi.stubGlobal('fetch', vi.fn(iaFetch))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'IA' }))
  const table = await screen.findByRole('region', { name: 'Detalhes por execução e etapa' })
  expect(table.textContent).toContain('— / 0 / — / —')
  expect(table.textContent).toContain('— / 1 / 0')
  expect(table.textContent).toContain('Etapa não concluída')
  expect(screen.getByText(/Cobertura incompleta: 0 de 1 etapas/)).toBeTruthy()
})

test('event timeline shows a decision only from its recorded payload', async () => {
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/agent-runs/run-1') return Promise.resolve(reply({
      agent_run_id: 'run-1', session_id: 'session-1', status: 'completed', error_code: null, events: [
        { event_id: 'one', task_id: 'triage', producer: 'backend', status: 'completed', created_at: null, payload: { final_action: 'blocked' }, validation_errors: null },
        { event_id: 'two', task_id: 'decision', producer: 'backend', status: 'completed', created_at: null, payload: { final_action: 'respond' }, validation_errors: null },
      ]
    }))
    if (url === '/api/admin/conversations/session-1') return Promise.resolve(reply({ session_id: 'session-1', messages: [], runs: [{ agent_run_id: 'run-1', status: 'completed', started_at: null, final_action: 'respond', error_code: null, summary: null, sources: [] }], tickets: [] }))
    if (url === '/api/admin/conversations?limit=20&offset=0') return Promise.resolve(reply({ items: [{ session_id: 'session-1', status: 'active', last_activity_at: null, last_run: null }], total: 1 }))
    return iaFetch(url)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Ver detalhes' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Ver eventos' }))
  const events = await screen.findByText('backend · triage')
  expect(events.parentElement?.textContent).not.toContain('Desfecho:')
  expect(screen.getByText('Desfecho: Resposta')).toBeTruthy()
  expect(screen.getAllByText('Ver metadados da etapa')).toHaveLength(2)
})

test.each([
  ['prepared', null, 'Apenas preparado, não enviado'],
  ['uncertain', '2026-10-15T10:00:00Z', 'Resultado do envio incerto'],
  ['created', '2026-10-15T10:00:00Z', 'Enviado e criado'],
  ['created', null, 'Enviado e criado'],
  ['rejected', '2026-10-15T10:00:00Z', 'Envio rejeitado'],
  ['simulated', '2026-10-15T10:00:00Z', 'Simulado (mock), não enviado ao ServiceNow'],
])('admin ticket detail renders redacted payload and %s submission separately from events', async (submission_state, submission_started_at, label) => {
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/tickets?limit=20&offset=0') return Promise.resolve(reply({ items: [{ ticket_id: 'ticket-1', session_id: 'session-1', agent_run_id: 'run-1', status: submission_state === 'uncertain' ? 'outcome_unknown' : submission_state === 'rejected' ? 'failed' : ['created', 'simulated'].includes(submission_state) ? 'created' : 'pending', adapter_mode: submission_state === 'simulated' ? 'mock' : 'servicenow', servicenow_number: submission_state === 'simulated' ? 'MOCK-1' : null, internal_category: 'password_reset', resulting_priority: null, created_at: null }], total: 1 }))
    if (url === '/api/admin/tickets/ticket-1') return Promise.resolve(reply({ ticket_id: 'ticket-1', servicenow_number: null, submission_state, submission_started_at, error_code: null, redacted_payload: { short_description: 'Incidente redigido', description: '[REDACTED]', impact: 3, urgency: 2, category: 'inquiry' } }))
    if (url === '/api/agent-runs/run-1') return Promise.resolve(reply({ agent_run_id: 'run-1', status: submission_state, events: [{ event_id: 'decision-1', producer: 'backend', task_id: 'decision', status: 'completed', created_at: null, payload: { final_action: 'open_ticket' }, validation_errors: [] }] }))
    return iaFetch(url)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'Tickets' }))
  if (submission_state === 'simulated') expect(await screen.findByText('Simulado (não enviado)')).toBeTruthy()
  fireEvent.click(await screen.findByRole('button', { name: 'Ver ticket' }))
  const ticket = await screen.findByRole('region', { name: 'Detalhe do ticket' })
  expect(within(ticket).getByText(label)).toBeTruthy()
  expect(ticket.textContent).toContain(submission_started_at ? 'Início do envio:' : submission_state === 'prepared' ? 'Início do envio: não iniciado' : 'Início do envio: não registrado')
  expect(ticket.textContent).toContain('[REDACTED]')
  expect(ticket.textContent).not.toContain('final_action')
  expect(screen.queryByText('Selecione uma conversa ou um ticket para ver o histórico.')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Ver eventos' }))
  const event = (await screen.findByText('backend · decision')).parentElement!
  fireEvent.click(within(event).getByText('Ver metadados da etapa'))
  expect(event.textContent).toContain('final_action')
  expect(event.textContent).not.toContain('validation_errors')
  expect(event.textContent).not.toContain('[]')
  expect(fetchMock).toHaveBeenCalledWith('/api/admin/tickets/ticket-1', undefined)
  expect(ticket.textContent).not.toContain(submission_state === 'simulated' ? 'Enviado e criado' : 'Simulado')
})

test('admin conversation and execution keep an unknown ticket out of success states', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url === '/api/admin/conversations?limit=20&offset=0') return Promise.resolve(reply({ items: [{ session_id: 'session-1', last_activity_at: null, status: 'active', last_run: { run_status: 'outcome_unknown', final_action: 'open_ticket', error_code: 'TICKET_OUTCOME_UNKNOWN' } }], total: 1 }))
    if (url === '/api/admin/conversations/session-1') return Promise.resolve(reply({ session_id: 'session-1', status: 'active', created_at: null, updated_at: null, messages: [], runs: [{ agent_run_id: 'run-1', status: 'outcome_unknown', final_action: 'open_ticket', started_at: null, summary: null, error_code: 'TICKET_OUTCOME_UNKNOWN', sources: [] }], tickets: [] }))
    return iaFetch(url)
  }))
  render(<AdminConsole />)
  fireEvent.click(screen.getByRole('button', { name: 'Conversas' }))
  const list = await screen.findByRole('region', { name: 'Conversas' })
  expect(within(list).getByText('Resultado incerto').classList.contains('warning')).toBe(true)
  fireEvent.click(within(list).getByRole('button', { name: 'Ver detalhes' }))
  const detail = screen.getByRole('region', { name: 'Conversa e decisões' })
  expect((await within(detail).findByText('Resultado incerto')).classList.contains('warning')).toBe(true)
  expect(within(detail).queryByText('Ticket')).toBeNull()
})