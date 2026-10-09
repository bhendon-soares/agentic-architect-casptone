import { useRef, useState, type FormEvent } from 'react'
import { getRunStatus, startRun, type RunError, type RunInput, type RunResult, type RunStatus } from './mockRuns'
import './style.css'

const example = 'Esqueci a senha da minha conta corporativa de demonstração. Consigo acessar o método oficial de verificação de identidade.'

type Message = { id: number; role: 'user'; text: string } | { id: number; role: 'assistant'; result: RunResult }

export default function App() {
  const [draft, setDraft] = useState(example)
  const [messages, setMessages] = useState<Message[]>([])
  const [status, setStatus] = useState<RunStatus>('idle')
  const [error, setError] = useState<RunError | null>(null)
  const [failedInput, setFailedInput] = useState<RunInput | null>(null)
  const [updatedAt, setUpdatedAt] = useState(new Date())
  const running = useRef(false)
  const nextId = useRef(0)

  const updateStatus = (next: RunStatus) => {
    setStatus(next)
    setUpdatedAt(new Date())
  }

  async function execute(input: RunInput, isRetry = false) {
    if (running.current || !input.message_text.trim()) return
    running.current = true
    setError(null)
    setFailedInput(null)
    if (!isRetry) {
      setMessages((current) => [...current, { id: ++nextId.current, role: 'user', text: input.message_text }])
    }
    updateStatus('running')
    try {
      const runId = await startRun(input)
      const snapshot = await getRunStatus(runId)
      if (snapshot.status !== 'done') throw { code: 'RUN_PENDING', message: 'O atendimento ainda não foi concluído.', retryable: true } satisfies RunError
      setMessages((current) => [...current, { id: ++nextId.current, role: 'assistant', result: snapshot.result }])
      setDraft('')
      updateStatus('done')
    } catch {
      setError({ code: 'RUN_FAILED', message: 'Não foi possível concluir o atendimento. Tente novamente.', retryable: true })
      setFailedInput(input)
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

  function reset() {
    if (running.current) return
    setMessages([])
    setDraft(example)
    setError(null)
    setFailedInput(null)
    updateStatus('idle')
  }

  const statusLabel = status === 'running' ? 'em andamento' : status === 'done' ? 'concluído' : 'ocioso'

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark" aria-hidden="true">S/</span><span>Suporte TI <small>interno</small></span></div>
        <span className="demo-label">DEMONSTRAÇÃO · DADOS FICTÍCIOS</span>
      </header>

      <main className="workspace">
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
              {message.role === 'user' ? <p>{message.text}</p> : <>
                <p className="result-summary">{message.result.summary}</p>
                <p>{message.result.message_pt_br}</p>
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
          {error && <div className="error-banner" role="alert"><strong>Falha técnica</strong><span>{error.message}</span><button type="button" onClick={() => failedInput && void execute(failedInput, true)} disabled={!failedInput || status === 'running'}>Tentar novamente</button></div>}
          <form className="composer" onSubmit={submit}>
            <label htmlFor="problem">Descreva seu problema</label>
            <textarea id="problem" value={draft} onChange={(event) => setDraft(event.target.value)} disabled={status === 'running'} rows={3} maxLength={2000} placeholder="Descreva o que está acontecendo…" />
            <div className="composer-footer"><span>Cenário de demonstração: redefinição de senha</span><div className="actions"><button className="reset-button" type="button" onClick={reset} disabled={status === 'running'}>Reiniciar</button><button className="execute-button" type="submit" disabled={status === 'running' || !draft.trim()}>{status === 'running' ? 'Em andamento…' : 'Executar'}</button></div></div>
          </form>
          <p className="privacy-note">Não informe senhas, tokens ou credenciais neste chat.</p>
        </div>
      </main>
    </div>
  )
}