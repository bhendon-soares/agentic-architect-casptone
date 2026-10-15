import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createSession, getSession, sendMessage, type ChatHistory, type RunError, type RunInput, type RunResult, type RunStatus } from './chatApi'
import './style.css'

const example = 'Esqueci a senha da minha conta corporativa de demonstração. Consigo acessar o método oficial de verificação de identidade.'

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
  const [draft, setDraft] = useState(example)
  const [messages, setMessages] = useState<Message[]>([])
  const [status, setStatus] = useState<RunStatus>('idle')
  const [error, setError] = useState<RunError | null>(null)
  const [failedTurn, setFailedTurn] = useState<FailedTurn | null>(null)
  const [sessions, setSessions] = useState<string[]>(storedSessions)
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
    if (running.current || !input.message_text.trim() || (!isRetry && activeSession.current && reviewSessions.includes(activeSession.current))) return
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
      updateStatus('done')
    } catch (cause) {
      const failure = cause as RunError
      if (activeSession.current && failure?.code && !['TICKET_CREATE_FAILED', 'TICKET_OUTCOME_UNKNOWN'].includes(failure.code)) markForReview(activeSession.current, false)
      if (failure?.code === 'MINIMUM_TICKET_DATA_MISSING') {
        setMessages((current) => [...current, { id: ++nextId.current, role: 'notice', text: failure.message }])
        setDraft('')
        updateStatus('done')
        return
      }
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
      setDraft(example)
      setError(null)
      setFailedTurn(null)
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
      nextId.current = history.messages.length
      setDraft('')
      setError(null)
      setFailedTurn(null)
      updateStatus(history.turns.length ? 'done' : 'idle')
    } catch (cause) {
      const failure = cause as RunError
      setError(failure?.code && failure?.message ? failure : { code: 'RUN_FAILED', message: 'Não foi possível carregar o histórico.', retryable: true })
      updateStatus('idle')
    } finally {
      running.current = false
    }
  }

  const statusLabel = status === 'running' ? 'em andamento' : status === 'done' ? 'concluído' : 'ocioso'
  const needsReview = sessionId !== null && reviewSessions.includes(sessionId)

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark" aria-hidden="true">S/</span><span>Suporte TI <small>interno</small></span></div>
        <a className="topbar-link" href="/admin">Console admin</a>
        <span className="demo-label">DEMONSTRAÇÃO · DADOS FICTÍCIOS</span>
      </header>

      <main className="workspace">
        {sessions.length > 0 && <nav className="session-nav" aria-label="Conversas anteriores">
          <span>Conversas</span>
          {sessions.map((id, index) => <button type="button" key={id} aria-current={sessionId === id ? 'page' : undefined} disabled={status === 'running'} onClick={() => void selectSession(id)}>Conversa {sessions.length - index}</button>)}
        </nav>}
        <div className="page-heading">
          <div><p className="eyebrow">ATENDIMENTO / 01</p><h1>Como podemos ajudar?</h1></div>
          <div className="run-status" role="status" aria-live="polite">
            <span className={`status-dot ${error ? 'failed' : status}`} aria-hidden="true" />
            <div><strong>Atendimento: {statusLabel}</strong><small>Atualizado às {updatedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small></div>
          </div>
        </div>

        <section className="conversation" aria-label="Histórico da conversa" aria-live="polite">
          {messages.length === 0 && <div className="empty-state"><span className="empty-glyph" aria-hidden="true">↗</span><h2>Seu atendimento começa aqui.</h2><p>Descreva o problema para receber uma orientação baseada na fonte local.</p></div>}
          {messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
            <span className="message-avatar" aria-hidden="true">{message.role === 'user' ? 'EU' : 'TI'}</span>
            <div className="message-content">
              <span className="message-author">{message.role === 'user' ? 'Você' : 'Suporte TI · demonstração'}</span>
              {message.role === 'user' || message.role === 'notice' ? <p>{message.text}</p> : <>
                <p className="result-summary">{message.result.summary}</p>
                <p>{message.result.message_pt_br}</p>
                {message.result.ticket && <p className="ticket-number">Incidente: {message.result.ticket.servicenow_number ?? 'Número pendente'} · {message.result.ticket.status === 'created' ? 'Criado' : message.result.ticket.status}</p>}
                {message.result.sources.map((source) => <aside className="source" key={source.path} aria-label="Fonte da orientação">
                  <span className="source-kicker">FONTE LOCAL</span>
                  <strong>{source.title}</strong>
                  <span className="source-path">{source.path}</span>
                  <blockquote>{source.snippet}</blockquote>
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
            <textarea id="problem" value={draft} onChange={(event) => setDraft(event.target.value)} disabled={status === 'running'} rows={3} maxLength={2000} placeholder="Descreva o que está acontecendo…" />
            <div className="composer-footer"><span>Cenário de demonstração: redefinição de senha</span><div className="actions"><button className="reset-button" type="button" onClick={() => void reset()} disabled={status === 'running'}>Reiniciar</button><button className="execute-button" type="submit" disabled={status === 'running' || !draft.trim() || needsReview || (!!failedTurn && draft.trim() === failedTurn.input.message_text.trim())}>{status === 'running' ? 'Em andamento…' : 'Executar'}</button></div></div>
          </form>
          <p className="privacy-note">Não informe senhas, tokens ou credenciais neste chat.</p>
        </div>
      </main>
    </div>
  )
}