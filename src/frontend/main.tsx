import { useEffect, useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import AdminConsole from './AdminConsole'
import { changePassword, getCurrentUser, loginUser, logoutUser, type AuthUser, type RunError } from './chatApi'
import { SiteHeader } from './ui'
import './style.css'

export function AuthGate() {
    const [user, setUser] = useState<AuthUser | null>(null)
    const [loading, setLoading] = useState(true)
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [confirmation, setConfirmation] = useState('')
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')

    useEffect(() => {
        void getCurrentUser().then(setUser).catch((cause: RunError) => {
            setUser(null)
            if (cause.code !== 'AUTH_REQUIRED' && cause.code !== 'INVALID_TOKEN') setError('Não foi possível verificar sua sessão.')
        }).finally(() => setLoading(false))
        const expired = () => { setUser(null); setNotice('Sessão expirada. Entre novamente.') }
        window.addEventListener('auth-expired', expired)
        return () => window.removeEventListener('auth-expired', expired)
    }, [])

    useEffect(() => {
        if (user?.role === 'user' && window.location.pathname === '/admin') {
            window.history.replaceState(null, '', '/')
            setNotice('Acesso restrito')
        }
    }, [user])

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError('')
        if (user && newPassword !== confirmation) { setError('A confirmação não coincide com a nova senha.'); return }
        setLoading(true)
        try {
            const current = user ? await changePassword(password, newPassword) : await loginUser(email, password)
            setUser(current)
            setPassword('')
            setNewPassword('')
            setConfirmation('')
            setNotice('')
        } catch (cause) {
            const failure = cause as RunError
            setError(failure.code === 'LOGIN_LOCKED' ? 'Acesso temporariamente bloqueado. Procure um administrador.' : failure.code === 'INVALID_CREDENTIALS' ? 'Email ou senha incorretos.' : failure.message || 'Não foi possível continuar.')
        } finally {
            setLoading(false)
        }
    }

    async function signOut() {
        setError('')
        try {
            await logoutUser()
            setUser(null)
            window.location.assign('/')
        } catch {
            setError('Não foi possível encerrar a sessão. Tente novamente.')
        }
    }

    if (loading && !user) return <div className="auth-page"><p role="status">Carregando…</p></div>
    if (!user || user.must_change_password) return <div className="auth-page"><SiteHeader /><main className="auth-panel">
        <p className="eyebrow">ACESSO / SUPORTE</p><h1>{user ? 'Trocar senha' : 'Iniciar sessão'}</h1>
        {notice && <p role="status">{notice}</p>}{error && <p role="alert" className="auth-error">{error}</p>}
        <form onSubmit={(event) => void submit(event)}>
            {!user && <label>Email<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>}
            <label>{user ? 'Senha atual' : 'Senha'}<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            {user && <label>Nova senha<input type="password" autoComplete="new-password" required minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>}
            {user && <label>Confirmar nova senha<input type="password" autoComplete="new-password" required minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>}
            <button type="submit" className="admin-command" disabled={loading}>{user ? 'Alterar senha' : 'Entrar'}</button>
        </form>
        {!user && <p className="auth-help">Não tem acesso? Procure um administrador.</p>}
        {user && <button type="button" className="topbar-link" onClick={() => void signOut()}>Sair</button>}
    </main></div>

    return <>
        {error && <p role="alert" className="logout-error">{error}</p>}
        {window.location.pathname === '/admin' && user.role === 'admin' ? <AdminConsole user={user} onLogout={signOut} /> : <App user={user} onLogout={signOut} notice={notice} />}
    </>
}

const root = document.getElementById('root')
if (root) createRoot(root).render(<AuthGate />)