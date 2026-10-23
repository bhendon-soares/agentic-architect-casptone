import { useEffect, useRef, useState, type FormEvent } from 'react'
import { KeyRound, LockKeyholeOpen, Mail, Pencil, Search, Shield, UserCheck, UserPlus, UserRound, UserRoundX, X } from 'lucide-react'
import { createUser, listUsers, resetUserPassword, unlockLogin, updateUser, type AuthUser, type ManagedUser, type RunError } from './chatApi'

type UserAction = { kind: 'rename' | 'role' | 'status' | 'reset' | 'unlock'; user: ManagedUser; ip?: string }

export default function UsersPanel({ admin }: { admin: AuthUser }) {
    const [users, setUsers] = useState<ManagedUser[]>([])
    const [total, setTotal] = useState(0)
    const [offset, setOffset] = useState(0)
    const [search, setSearch] = useState('')
    const [role, setRole] = useState('')
    const [active, setActive] = useState('')
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [newRole, setNewRole] = useState<'user' | 'admin'>('user')
    const [password, setPassword] = useState('')
    const [action, setAction] = useState<UserAction | null>(null)
    const [actionName, setActionName] = useState('')
    const [temporaryPassword, setTemporaryPassword] = useState('')
    const [pending, setPending] = useState(false)
    const dialog = useRef<HTMLDialogElement>(null)

    async function refresh() {
        const params = new URLSearchParams({ limit: '20', offset: String(offset) })
        if (search) params.set('search', search)
        if (role) params.set('role', role)
        if (active) params.set('is_active', active)
        try {
            const result = await listUsers(params.toString())
            setUsers(result.items)
            setTotal(result.total)
            setError('')
        } catch (cause) { setError((cause as RunError).message || 'Não foi possível carregar usuários.') }
    }

    useEffect(() => { void refresh() }, [offset, search, role, active])

    async function run(operation: () => Promise<unknown>, message: string): Promise<boolean> {
        setPending(true)
        try { await operation(); setNotice(message); setError(''); await refresh(); return true }
        catch (cause) { setError((cause as RunError).message || 'A operação não foi concluída.'); return false }
        finally { setPending(false) }
    }

    function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        void run(async () => {
            await createUser({ email, display_name: name, role: newRole, temporary_password: password })
            setName(''); setEmail(''); setPassword('')
        }, 'Usuário criado. Entregue a senha temporária por um canal externo.')
    }

    function openAction(kind: UserAction['kind'], user: ManagedUser, ip?: string) {
        setAction({ kind, user, ip })
        setActionName(user.display_name)
        setTemporaryPassword('')
        setError('')
        dialog.current?.showModal()
    }

    function closeAction() {
        dialog.current?.close()
        setAction(null)
        setTemporaryPassword('')
    }

    async function submitAction(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!action || pending) return
        const { kind, user, ip } = action
        const operations = {
            rename: () => updateUser(user.user_id, { display_name: actionName.trim() }),
            role: () => updateUser(user.user_id, { role: user.role === 'admin' ? 'user' as const : 'admin' as const }),
            status: () => updateUser(user.user_id, { is_active: !user.is_active }),
            reset: () => resetUserPassword(user.user_id, temporaryPassword),
            unlock: () => unlockLogin(user.email, ip!),
        }
        const messages = {
            rename: 'Nome atualizado.', role: 'Perfil atualizado.', status: 'Status atualizado.',
            reset: 'Senha redefinida. Entregue-a por um canal externo.', unlock: 'Login desbloqueado.',
        }
        if (await run(operations[kind], messages[kind])) closeAction()
    }

    const actionTitle = action && {
        rename: 'Editar nome', role: 'Alterar perfil', status: action.user.is_active ? 'Desativar usuário' : 'Reativar usuário',
        reset: 'Redefinir senha', unlock: 'Desbloquear login',
    }[action.kind]

    return <section className="users-panel" aria-label="Gestão de usuários">
        {error && !action && <p className="admin-error" role="alert">{error}</p>}
        {notice && <p className="users-notice" role="status">{notice}</p>}
        <form className="users-create" onSubmit={create}>
            <h2><UserPlus size={20} aria-hidden="true" /> Novo usuário</h2>
            <label><span><UserRound size={15} aria-hidden="true" /> Nome</span><input required value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label><span><Mail size={15} aria-hidden="true" /> Email</span><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label><span><Shield size={15} aria-hidden="true" /> Perfil</span><select value={newRole} onChange={(event) => setNewRole(event.target.value as 'user' | 'admin')}><option value="user">Usuário</option><option value="admin">Admin</option></select></label>
            <label><span><KeyRound size={15} aria-hidden="true" /> Senha temporária</span><input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button type="submit" className="admin-command" disabled={pending}><UserPlus size={16} aria-hidden="true" /> Criar usuário</button>
        </form>
        <div className="users-filters">
            <label><span><Search size={15} aria-hidden="true" /> Buscar</span><input type="search" value={search} onChange={(event) => { setOffset(0); setSearch(event.target.value) }} /></label>
            <label>Perfil<select value={role} onChange={(event) => { setOffset(0); setRole(event.target.value) }}><option value="">Todos</option><option value="user">Usuário</option><option value="admin">Admin</option></select></label>
            <label>Status<select value={active} onChange={(event) => { setOffset(0); setActive(event.target.value) }}><option value="">Todos</option><option value="true">Ativo</option><option value="false">Inativo</option></select></label>
        </div>
        <div className="users-table-wrap"><table className="users-table"><thead><tr><th>Nome</th><th>Email</th><th>Perfil</th><th>Status</th><th>Criado</th><th>Ações</th></tr></thead><tbody>
            {users.map((user) => <tr key={user.user_id}><td>{user.display_name}</td><td>{user.email}</td><td>{user.role}</td><td>{user.is_active ? 'Ativo' : 'Inativo'}{user.must_change_password && <small>Troca pendente</small>}{user.login_locked && <small>Login bloqueado</small>}</td><td>{new Date(user.created_at).toLocaleDateString('pt-BR')}</td><td className="users-actions">
                <button type="button" aria-label={`Editar nome de ${user.email}`} title="Editar nome" onClick={() => openAction('rename', user)}><Pencil size={16} /></button>
                <button type="button" aria-label={`Alterar perfil de ${user.email}`} disabled={user.user_id === admin.user_id} title={user.user_id === admin.user_id ? 'Você não pode alterar seu próprio perfil' : 'Alterar perfil'} onClick={() => openAction('role', user)}><Shield size={16} /></button>
                <button type="button" aria-label={`${user.is_active ? 'Desativar' : 'Reativar'} ${user.email}`} disabled={user.user_id === admin.user_id} title={user.user_id === admin.user_id ? 'Você não pode desativar seu próprio perfil' : user.is_active ? 'Desativar' : 'Reativar'} onClick={() => openAction('status', user)}>{user.is_active ? <UserRoundX size={16} /> : <UserCheck size={16} />}</button>
                <button type="button" aria-label={`Redefinir senha de ${user.email}`} title="Redefinir senha" onClick={() => openAction('reset', user)}><KeyRound size={16} /></button>
                {user.login_locks.map((lock) => <button type="button" key={lock.ip} aria-label={`Desbloquear ${user.email} no IP ${lock.ip}`} title={`Desbloquear ${lock.ip}`} onClick={() => openAction('unlock', user, lock.ip)}><LockKeyholeOpen size={16} /></button>)}
            </td></tr>)}
        </tbody></table></div>
        <div className="users-pagination"><span>{total} usuários</span><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior</button><button type="button" disabled={offset + 20 >= total} onClick={() => setOffset(offset + 20)}>Próximo</button></div>
        <dialog ref={dialog} className="users-dialog" aria-labelledby="users-dialog-title" onClose={() => setAction(null)} onCancel={(event) => { if (pending) event.preventDefault() }}>
            {action && <form onSubmit={(event) => void submitAction(event)}>
                <div className="users-dialog-heading"><h2 id="users-dialog-title">{actionTitle}</h2><button type="button" aria-label="Fechar" title="Fechar" disabled={pending} onClick={closeAction}><X size={18} /></button></div>
                <p className="users-dialog-context">{action.user.display_name} · {action.user.email}</p>
                {action.kind === 'rename' && <label>Nome<input autoFocus required maxLength={255} value={actionName} onChange={(event) => setActionName(event.target.value)} /></label>}
                {action.kind === 'reset' && <label>Nova senha temporária<input autoFocus required type="password" autoComplete="new-password" minLength={12} value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} /></label>}
                {action.kind === 'role' && <p>Alterar o perfil para <strong>{action.user.role === 'admin' ? 'Usuário' : 'Admin'}</strong>?</p>}
                {action.kind === 'status' && <p>{action.user.is_active ? 'Este usuário perderá acesso ao sistema.' : 'Este usuário poderá acessar o sistema novamente.'}</p>}
                {action.kind === 'unlock' && <p>Desbloquear o login no IP <strong>{action.ip}</strong>?</p>}
                {error && <p className="admin-error" role="alert">{error}</p>}
                <div className="users-dialog-actions"><button type="button" disabled={pending} onClick={closeAction}>Cancelar</button><button type="submit" className="admin-command" disabled={pending || (action.kind === 'rename' && !actionName.trim())}>{pending ? 'Salvando…' : actionTitle}</button></div>
            </form>}
        </dialog>
    </section>
}