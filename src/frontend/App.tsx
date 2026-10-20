import { useEffect, useRef, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { createSession, getSession, sendMessage, type ChatHistory, type RunError, type RunInput, type RunResult, type RunStatus } from './chatApi'
import { formatDate, StatusBadge, ThemeToggle } from './ui'
import './style.css'

type Message = { id: number; role: 'user'; text: string } | { id: number; role: 'assistant'; result: RunResult } | { id: number; role: 'notice'; text: string }
type FailedTurn = { input: RunInput; key: string }
const sessionsKey = 'support-chat-sessions'
const reviewKey = 'support-chat-ticket-review'

function storedReviewSessions(): string[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(reviewKey) || '[]')
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

function storedSessions(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(sessionsKey) || '[]')
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

function historyMessages(history: ChatHistory): Message[] {
  const turns = [...history.turns]
  const outcomes = new Map((history.outcomes ?? []).map((outcome) => [outcome.agent_run_id, outcome]))
  return history.messages.flatMap((message, index): Message[] => {
    if (message.role === 'user') {
      const outcome = message.agent_run_id ? outcomes.get(message.agent_run_id) : undefined
      return [{ id: index * 2, role: 'user', text: message.message_pt_br }, ...(outcome ? [{ id: index * 2 + 1, role: 'notice' as const, text: outcome.message_pt_br }] : [])]
    }
    const result = turns.shift()
    return result ? [{ id: index * 2, role: 'assistant', result }] : []
  })
}

export default function App() {
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [status, setStatus] = useState<RunStatus>('idle')
  const [outcomeLabel, setOutcomeLabel] = useState<string | null>(null)
  const [error, setError] = useState<RunError | null>(null)
  const [failedTurn, setFailedTurn] = useState<FailedTurn | null>(null)
  const [sessions, setSessions] = useState<string[]>(storedSessions)
  const [sessionTitles, setSessionTitles] = useState<Record<string, string>>({})
  const [navOpen, setNavOpen] = useState(true)
  const [reviewSessions, setReviewSessions] = useState<string[]>(storedReviewSessions)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState(new Date())
  const running = useRef(false)
  const nextId = useRef(0)
  const activeSession = useRef<string | null>(null)

  useEffect(() => {
    if (sessions.length) void selectSession(sessions[0])
  }, [])

  function rememberSession(id: string) {
    setSessions((current) => {
      const updated = [id, ...current.filter((entry) => entry !== id)]
      localStorage.setItem(sessionsKey, JSON.stringify(updated))
      return updated
    })
  }

  function markForReview(id: string, required: boolean) {
    const updated = required ? [id, ...reviewSessions.filter((entry) => entry !== id)] : reviewSessions.filter((entry) => entry !== id)
    setReviewSessions(updated)
    sessionStorage.setItem(reviewKey, JSON.stringify(updated))
  }

  const updateStatus = (next: RunStatus) => {
    setStatus(next)
    setUpdatedAt(new Date())
  }

  async function execute(input: RunInput, isRetry = false, key: string = crypto.randomUUID()) {
    if (running.current || !input.message_text.trim() || input.message_text.length > 2000 || (!isRetry && activeSession.current && reviewSessions.includes(activeSession.current))) return
    running.current = true
    setError(null)
    setFailedTurn(null)
    if (!isRetry) {
      setMessages((current) => [...current, { id: ++nextId.current, role: 'user', text: input.message_text }])
    }
    updateStatus('running')
    try {
      let id = activeSession.current
      if (!id) {
        id = await createSession()
        activeSession.current = id
        setSessionId(id)
        rememberSession(id)
      }
      markForReview(id, true)
      const result = await sendMessage(id, input, key)
      markForReview(id, false)
      setMessages((current) => [...current, { id: ++nextId.current, role: 'assistant', result }])
      setDraft('')
      setOutcomeLabel(result.final_action === 'ask_clarification' ? 'Aguardando você' : result.final_action === 'blocked' ? 'Bloqueado' : result.final_action === 'open_ticket' ? (result.ticket?.status === 'created' && result.ticket.servicenow_number ? 'Ticket aberto' : 'Estado a verificar') : 'Concluído')
      updateStatus('done')
    } catch (cause) {
      const failure = cause as RunError
      if (activeSession.current && failure?.code && !['TICKET_CREATE_FAILED', 'TICKET_OUTCOME_UNKNOWN'].includes(failure.code)) markForReview(activeSession.current, false)
      if (failure?.code === 'MINIMUM_TICKET_DATA_MISSING') {
        setMessages((current) => [...current, { id: ++nextId.current, role: 'notice', text: failure.message }])
        setDraft('')
        setOutcomeLabel('Faltam dados mínimos para abrir o ticket')
        updateStatus('done')
        return
      }
      setOutcomeLabel(['TICKET_CREATE_FAILED', 'TICKET_OUTCOME_UNKNOWN'].includes(failure?.code) ? 'Resultado do ticket incerto' : 'Falhou')
      setError(failure?.code && failure?.message ? failure : { code: 'RUN_FAILED', message: 'Não foi possível concluir o atendimento.', retryable: true })
      setFailedTurn({ input, key })
      setDraft(input.message_text)
      updateStatus('idle')
    } finally {
      running.current = false
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void execute({ message_text: draft })
  }

  async function reset() {
    if (running.current) return
    if (activeSession.current && reviewSessions.includes(activeSession.current) && !window.confirm('A tentativa anterior pode ter criado um incidente. Consulte o suporte antes de solicitar outro. Iniciar uma nova conversa?')) return
    running.current = true
    updateStatus('running')
    try {
      const id = await createSession()
      activeSession.current = id
      setSessionId(id)
      rememberSession(id)
      setMessages([])
      setDraft('')
      setError(null)
      setFailedTurn(null)
      setOutcomeLabel(null)
      updateStatus('idle')
    } catch (cause) {
      const failure = cause as RunError
      setError(failure?.code && failure?.message ? failure : { code: 'RUN_FAILED', message: 'Não foi possível criar uma sessão.', retryable: true })
      updateStatus('idle')
    } finally {
      running.current = false
    }
  }

  async function selectSession(id: string) {
    if (running.current) return
    running.current = true
    updateStatus('running')
    try {
      const history = await getSession(id)
      activeSession.current = id
      setSessionId(id)
      setMessages(historyMessages(history))
      const firstMessage = history.messages.find((message) => message.role === 'user')
      setSessionTitles((current) => ({ ...current, [id]: firstMessage?.message_pt_br?.trim().slice(0, 56) || `${formatDate(history.messages[0]?.created_at)} · ${id.slice(0, 8)}` }))
      nextId.current = history.messages.length
      setDraft('')
      setError(null)
      setFailedTurn(null)
      const lastMessage = history.messages.at(-1)
      const lastOutcome = history.outcomes?.find((outcome) => outcome.agent_run_id === lastMessage?.agent_run_id)
      const lastTurn = lastMessage?.role === 'assistant' ? history.turns.at(-1) : null
      setOutcomeLabel(lastOutcome?.code === 'MINIMUM_TICKET_DATA_MISSING' ? 'Faltam dados mínimos para abrir o ticket' : lastTurn?.final_action === 'ask_clarification' ? 'Aguardando você' : lastTurn?.final_action === 'blocked' ? 'Bloqueado' : lastTurn?.final_action === 'open_ticket' ? (lastTurn.ticket?.status === 'created' && lastTurn.ticket.servicenow_number ? 'Ticket aberto' : 'Estado a verificar') : lastTurn?.final_action === 'respond' ? 'Concluído' : null)
      updateStatus(lastTurn || lastOutcome ? 'done' : 'idle')
    } catch (cause) {
      const failure = cause as RunError
      setError(failure?.code && failure?.message ? failure : { code: 'RUN_FAILED', message: 'Não foi possível carregar o histórico.', retryable: true })
      updateStatus('idle')
    } finally {
      running.current = false
    }
  }

  const needsReview = sessionId !== null && reviewSessions.includes(sessionId)
  const statusLabel = status === 'running' ? 'Em andamento' : needsReview && !error ? 'Estado a verificar' : outcomeLabel ?? (error ? 'Falhou' : 'Aguardando mensagem')
  const statusTone = status === 'running' || statusLabel === 'Aguardando você' ? 'info' : statusLabel === 'Concluído' || statusLabel === 'Ticket aberto' ? 'success' : statusLabel === 'Bloqueado' || statusLabel.includes('incerto') ? 'warning' : statusLabel === 'Falhou' || statusLabel.startsWith('Faltam') ? 'danger' : 'neutral'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Help Desk TI Multi Agent MVP - voltar ao chat"><span className="brand-mark" aria-hidden="true">S/</span><span>Help Desk TI Multi Agent MVP</span></a>
        <a className="topbar-link" href="/admin">Console admin</a>
        <ThemeToggle />
        <span className="demo-label">DEMONSTRAÇÃO · DADOS FICTÍCIOS</span>
      </header>

      <main className="workspace">
        {sessions.length > 0 && <nav className={`session-nav ${navOpen ? '' : 'collapsed'}`} aria-label="Conversas anteriores">
          <button type="button" className="nav-toggle" aria-expanded={navOpen} aria-label={navOpen ? 'Recolher conversas' : 'Mostrar conversas'} onClick={() => setNavOpen(!navOpen)}>{navOpen ? '‹' : '›'}<span>Conversas</span></button>
          {navOpen && sessions.map((id) => <button type="button" key={id} title={sessionTitles[id] || id} aria-current={sessionId === id ? 'page' : undefined} disabled={status === 'running'} onClick={() => void selectSession(id)}>{sessionTitles[id] || id.slice(0, 8)}</button>)}
        </nav>}
        <div className="page-heading">
          <div><p className="eyebrow">ATENDIMENTO / 01</p><h1>Como podemos ajudar?</h1></div>
          <div className="run-status" role="status" aria-live="polite">
            <StatusBadge tone={statusTone}>Atendimento: {statusLabel}</StatusBadge><small>Atualizado às {updatedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small>
          </div>
        </div>

        <section className="conversation" aria-label="Histórico da conversa" aria-live="polite">
          {messages.length === 0 && <div className="empty-state"><span className="empty-glyph" aria-hidden="true">↗</span><h2>Seu atendimento começa aqui.</h2><p>Descreva o problema para receber uma orientação baseada na fonte local.</p></div>}
          {messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
            <span className="message-avatar" aria-hidden="true">{message.role === 'user' ? 'EU' : 'TI'}</span>
            <div className="message-content">
              <span className="message-author">{message.role === 'user' ? 'Você' : 'Suporte TI · demonstração'}</span>
              {message.role === 'user' || message.role === 'notice' ? <p>{message.text}</p> : <>
                <div className="answer-text"><ReactMarkdown skipHtml allowedElements={['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'br']}>{message.result.message_pt_br}</ReactMarkdown></div>
                {message.result.ticket && <p className="ticket-number">{message.result.ticket.status === 'created' && message.result.ticket.servicenow_number ? `Ticket aberto: ${message.result.ticket.servicenow_number}` : message.result.ticket.status === 'outcome_unknown' ? 'Resultado do ticket incerto' : message.result.ticket.status === 'failed' ? 'Abertura do ticket falhou' : 'Estado do ticket a verificar'}</p>}
                {message.result.sources.map((source) => <aside className="source" key={source.path} aria-label="Fonte da orientação">
                  <span className="source-kicker">FONTE LOCAL</span>
                  <strong>{source.title}</strong>
                </aside>)}
              </>}
            </div>
          </article>)}
          {status === 'running' && <div className="progress" role="status"><span className="progress-pulse" aria-hidden="true" />Consultando a orientação local…</div>}
        </section>

        <div className="composer-wrap">
          {(error || (needsReview && status !== 'running')) && <div className="error-banner" role="alert"><strong>{error ? 'Falha técnica' : 'Atendimento requer verificação'}</strong><span>{error ? error.message : 'A chave da tentativa anterior não está mais disponível nesta aba.'}{needsReview && ' Consulte o suporte antes de solicitar outro incidente; esta conversa não fará um novo envio.'}</span>{error && <button type="button" onClick={() => failedTurn && void execute(failedTurn.input, true, failedTurn.key)} disabled={!failedTurn || status === 'running'}>Tentar novamente</button>}</div>}
          <form className="composer" onSubmit={submit}>
            <label htmlFor="problem">Descreva seu problema</label>
            <textarea id="problem" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); if (draft.trim() && !needsReview && status !== 'running') event.currentTarget.form?.requestSubmit() } }} disabled={status === 'running'} rows={3} maxLength={2000} placeholder="Descreva o que está acontecendo…" />
            <div className="composer-footer"><span>{draft.length} / 2.000 caracteres</span><div className="actions"><button className="reset-button" type="button" onClick={() => void reset()} disabled={status === 'running'}>Nova conversa</button><button className="execute-button" type="submit" disabled={status === 'running' || !draft.trim() || draft.length > 2000 || needsReview || (!!failedTurn && draft.trim() === failedTurn.input.message_text.trim())}>{status === 'running' ? 'Em andamento…' : 'Enviar'}</button></div></div>
          </form>
          <p className="privacy-note">Não informe senhas, tokens ou credenciais neste chat.</p>
        </div>
      </main>
    </div>
  )
}