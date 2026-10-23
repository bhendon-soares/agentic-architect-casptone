# Change Request: Autenticacao e RBAC (user/admin)

Status: rascunho revisado pelo operador em 2026-10-22. Ainda nao incorporado ao PRD/SAD.

## Contexto

O MVP atual nao tem autenticacao. O console admin e as rotas `/api/admin/*` e `/api/ia-tab/*` sao protegidos apenas por `local_admin` (IP loopback). Isso:

- quebra o console atras de proxy/load balancer em outro host (403 `ADMIN_LOCAL_ONLY`);
- expoe o console sem login quando o proxy roda no mesmo host, pois todo trafego chega como loopback;
- deixa `GET /api/tickets` e `GET /api/tickets/{ticket_id}` publicos;
- permite ler qualquer conversa via `GET /api/chat/sessions/{session_id}` conhecendo o UUID, pois `chat_sessions` nao tem dono.

Este change request substitui a protecao por IP por autenticacao com JWT em cookie `httpOnly` e dois perfis de acesso.

## Conflito com o PRD vigente

O PRD declara o MVP sem RBAC, niveis de acesso ou autenticacao P0 (linhas ~25, ~325 e ~406) e lista autenticacao basica/OIDC como fora de escopo. Aprovar este change request exige atualizar o PRD (`@product-mgr`) e o SAD (`@system.arch`) antes do Build.

Invariante preservada: **prioridade, classificacao e decisao dos agentes nunca dependem do perfil ou de atributo do usuario**. O perfil controla apenas acesso a rotas e telas. Ele nao e enviado ao runtime CrewAI nem ao payload do ticket ServiceNow, e a identidade do solicitante tambem nao entra no ticket.

## Perfis

| Perfil | Chat (suporte help desk) | Proprio historico | Console admin, aba IA, tickets | Aba Usuarios (cadastro) | Conversas de outros usuarios |
|--------|--------------------------|-------------------|--------------------------------|-------------------------|------------------------------|
| `user` | sim | sim | nao | nao | nao |
| `admin` | sim | sim | sim | sim | somente leitura |

Nao ha acesso anonimo nem autocadastro: todo usuario e criado por um admin.

## Requisitos funcionais

### Identidade e provisionamento

**RBAC-01 Usuarios locais.** Nova tabela `users` no PostgreSQL:

| Campo | Regra |
|-------|-------|
| `user_id` | UUID, PK |
| `email` | unico, normalizado em minusculas, usado como login |
| `display_name` | obrigatorio |
| `password_hash` | argon2id |
| `role` | `user` ou `admin` |
| `is_active` | default `true` |
| `must_change_password` | default `true` |
| `password_changed_at` | timestamp |
| `created_at`, `updated_at` | timestamps |
| `created_by` | FK `users`, nullable (somente o seed) |

**RBAC-02 Seed do admin inicial.** O primeiro admin e o operador. Ele e criado por um comando CLI idempotente (`python -m app.cli create-admin`) que le `ADMIN_SEED_EMAIL` e `ADMIN_SEED_PASSWORD` do ambiente. O seed nasce com `must_change_password = false`, pois a senha e definida pelo proprio operador. A API nao cria usuarios no startup.

**RBAC-03 Senha temporaria.** Ao criar um usuario, ou ao redefinir a senha pela aba Usuarios, o admin informa uma senha temporaria e o sistema marca `must_change_password = true`. O admin entrega a senha ao usuario por canal externo; o sistema nao envia email.
Nao ha prazo de expiracao para a senha temporaria no MVP; a troca permanece obrigatoria ate ser concluida.

### Sessao autenticada

**RBAC-04 Login.** `POST /api/auth/login` recebe `{email, password}`. Em caso de sucesso:

- responde 200 com `{user: {user_id, email, display_name, role, must_change_password}}`;
- define o cookie de sessao (RBAC-06);
- zera o contador de falhas do par IP + email (RBAC-09).

Credencial invalida ou usuario inativo responde 401 `INVALID_CREDENTIALS` com mensagem generica, sem revelar se o email existe.

**RBAC-05 JWT.** Assinado em HS256 com `JWT_SECRET` (env, minimo 32 bytes). A API falha no startup se o segredo estiver ausente ou curto. Claims: `sub` (user_id), `role`, `iat`, `exp` (8h) e `jti`. Nao ha refresh token: ao expirar, o usuario faz login novamente.

**RBAC-06 Cookie `httpOnly`.** O token trafega somente no cookie `session`, com os atributos `HttpOnly`, `Secure` (desligavel apenas em dev via `COOKIE_SECURE=false`), `SameSite=Strict`, `Path=/` e `Max-Age=28800`. O frontend nunca le nem armazena o token. Recarregar a pagina ou abrir nova aba mantem a sessao.

**RBAC-07 Protecao CSRF.** Toda requisicao com metodo nao seguro (`POST`, `PATCH`, `PUT`, `DELETE`) precisa ter header `Origin` igual a uma origem de `APP_ALLOWED_ORIGINS`; caso contrario, responde 403 `CSRF_REJECTED`. Junto com `SameSite=Strict`, isso dispensa um token CSRF separado no MVP. Frontend e API sao servidos na mesma origem.

**RBAC-08 Validacao por requisicao.** A dependency FastAPI `current_user` executa estas verificacoes, nesta ordem:

1. Le o cookie e valida assinatura e `exp`.
2. Carrega o usuario do banco.
3. Rejeita com 401 `INVALID_TOKEN` se:
   - `is_active = false`;
   - a role do banco divergir do claim;
   - `iat < password_changed_at`, ou seja, o token foi emitido antes de uma troca ou redefinicao de senha.

Com isso, desativar um usuario, mudar sua role ou redefinir sua senha revoga a sessao dele na proxima requisicao, sem precisar de uma lista de tokens. `require_role("admin")` e composta sobre `current_user`.

**RBAC-09 Bloqueio por tentativas.** Nova tabela `login_attempts` (`ip`, `email_normalized`, `failed_count`, `last_failed_at`, `locked_at`, `unlocked_at`, `unlocked_by`):

- **Contagem:** toda falha de login incrementa o contador do par IP + email, inclusive para email inexistente, para nao revelar existencia.
- **Bloqueio:** na 5a falha consecutiva o par fica bloqueado ate desbloqueio manual. Durante o bloqueio, qualquer tentativa desse par responde 429 `LOGIN_LOCKED` sem validar a senha. A mensagem diz apenas "Acesso temporariamente bloqueado. Procure um administrador."
- **Escopo:** o bloqueio afeta apenas aquele IP para aquele email. O mesmo usuario continua entrando de outro IP, e o mesmo IP continua entrando com outros emails. Isso impede que um atacante trave a conta da vitima de forma global.
- **Desbloqueio pela UI:** um admin desbloqueia o par na aba Usuarios (RBAC-14).
- **Desbloqueio pela CLI:** `python -m app.cli unlock-login --email <email> [--ip <ip>]` cobre o caso de o unico admin estar bloqueado.
- **Login com sucesso:** zera o contador do par.
- **IP do cliente:** e o IP do socket. `X-Forwarded-For` so e considerado quando o socket vem de um IP listado em `TRUSTED_PROXY_IPS`; sem isso, todos os usuarios atras do proxy compartilhariam um unico IP.

**RBAC-10 Troca obrigatoria de senha.** Enquanto `must_change_password = true`, a sessao so acessa `GET /api/auth/me`, `POST /api/auth/change-password` e `POST /api/auth/logout`. Qualquer outra rota responde 403 `PASSWORD_CHANGE_REQUIRED`.

`POST /api/auth/change-password` recebe `{current_password, new_password}`. A nova senha deve ter 12 ou mais caracteres e ser diferente da atual. Ao trocar, o sistema:

- atualiza `password_changed_at` e zera `must_change_password`;
- emite um novo cookie, pois o token antigo fica invalido pela RBAC-08.

O mesmo endpoint serve para troca voluntaria de senha.

**RBAC-11 Sessao atual e logout.**

- **`GET /api/auth/me`:** retorna o usuario da sessao. O frontend chama essa rota ao abrir o app para decidir entre a tela de login e o app.
- **`POST /api/auth/logout`:** remove o cookie com `Max-Age=0`. O JWT continua tecnicamente valido ate expirar, mas o navegador nao o tem mais. Revogacao efetiva ocorre via RBAC-08.

### Conversas

**RBAC-12 Dono da conversa.** `chat_sessions` ganha `user_id` (FK `users`, `NOT NULL`).

- `POST /api/chat/sessions` grava o usuario autenticado.
- `GET /api/chat/sessions/{id}` e `POST /api/chat/sessions/{id}/messages` exigem que o usuario autenticado seja o dono. Sessao de outro usuario responde 404 `SESSION_NOT_FOUND`, sem revelar existencia. A regra vale tambem para admin.
- O admin le conversas de qualquer usuario somente pelas rotas `/api/admin/conversations*`. Essas rotas sao exclusivamente de leitura: o admin nao envia mensagens nem continua a conversa de outro usuario.

**RBAC-13 Historico proprio.** Novo `GET /api/chat/sessions`, paginado (`limit`, `offset`), lista apenas as sessoes do usuario autenticado, da mais recente para a mais antiga. O usuario pode retomar uma sessao propria.

### Gestao de usuarios (admin)

**RBAC-14 CRUD de usuarios (sem exclusao).**

| Operacao | Rota | Regras |
|----------|------|--------|
| Listar | `GET /api/admin/users` | Paginado. Filtros opcionais: `role`, `is_active`, busca por email/nome. Retorna `user_id`, `email`, `display_name`, `role`, `is_active`, `must_change_password`, `created_at`, `updated_at` e um indicador de bloqueio de login ativo. Nunca retorna hash. |
| Detalhar | `GET /api/admin/users/{user_id}` | Inclui os bloqueios de login ativos (IP + data) do email. |
| Criar | `POST /api/admin/users` | Recebe `{email, display_name, role, temporary_password}`. Email duplicado responde 409 `EMAIL_TAKEN`. Senha com 12 ou mais caracteres. |
| Atualizar | `PATCH /api/admin/users/{user_id}` | Campos: `display_name`, `role`, `is_active`. Desativar e `is_active=false`, e reativar e permitido. |
| Redefinir senha | `POST /api/admin/users/{user_id}/reset-password` | Recebe `{temporary_password}`. Marca `must_change_password = true` e invalida as sessoes do usuario (RBAC-08). |
| Desbloquear login | `POST /api/admin/login-locks/unlock` | Recebe `{email, ip}`. Registra `unlocked_by`. |

Regras de protecao:

- Nao existe `DELETE`; desativar preserva as conversas e a auditoria.
- O admin nao pode desativar o proprio perfil (409 `SELF_DEACTIVATION`).
- O admin nao pode alterar a propria role (409 `SELF_ROLE_CHANGE`), para evitar perder o acesso por engano.
- O sistema impede desativar ou rebaixar o ultimo admin ativo (409 `LAST_ADMIN`).

### Limpeza e protecao das rotas

**RBAC-15 Limpeza dos dados sem dono.** Os registros atuais sao de demo e nao tem dono. Eles sao removidos antes de `chat_sessions.user_id` virar `NOT NULL`:

- **Execucao:** a limpeza roda pelo comando explicito `python -m app.cli purge-legacy --confirm`, executado pelo operador antes do `alembic upgrade` da migration de RBAC. A migration falha com mensagem clara se ainda existirem sessoes sem dono, e nunca apaga dados sozinha.
- **Ordem de exclusao (respeitando FKs):** `agent_events`, `agent_run_attempts`, `agent_run_telemetry`, `agent_run_results_summary`, `chat_messages`, `tickets`, `agent_runs`, `chat_sessions`.
- **Preservadas:** `pricing_config_versions` e `knowledge_sources`.
- **Backup:** recomenda-se um backup (`pg_dump`) antes da limpeza; o comando exibe a contagem por tabela antes de apagar.
- **Efeito externo:** tickets reais ja criados no ServiceNow nao sao afetados; somente o registro local e removido.

**RBAC-16 Remocao do `local_admin`.** A checagem por loopback e substituida por `require_role("admin")` em todas as rotas admin.

## Matriz de rotas

| Rota | Acesso |
|------|--------|
| `GET /health` | publico |
| `POST /api/auth/login` | publico (com bloqueio RBAC-09) |
| `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/change-password` | autenticado (permitido com troca de senha pendente) |
| `POST /api/chat/sessions`, `GET /api/chat/sessions` | autenticado |
| `GET /api/chat/sessions/{id}`, `POST /api/chat/sessions/{id}/messages` | autenticado + dono |
| `GET /api/tickets`, `GET /api/tickets/{id}` | admin (hoje publicos) |
| `/api/admin/conversations*`, `/api/admin/tickets/*` | admin, somente leitura |
| `/api/admin/users*`, `/api/admin/login-locks/unlock` | admin |
| `/api/ia-tab/*` | admin |

Codigos de erro (envelope padrao `{data, error, meta}`):

| Status | Codigo | Quando |
|--------|--------|--------|
| 401 | `AUTH_REQUIRED` | sem cookie |
| 401 | `INVALID_TOKEN` | assinatura invalida, token expirado, usuario inativo, role divergente ou senha trocada depois da emissao |
| 401 | `INVALID_CREDENTIALS` | login com credencial invalida |
| 403 | `FORBIDDEN_ROLE` | perfil insuficiente |
| 403 | `PASSWORD_CHANGE_REQUIRED` | troca de senha pendente |
| 403 | `CSRF_REJECTED` | `Origin` ausente ou nao permitido |
| 409 | `EMAIL_TAKEN`, `SELF_DEACTIVATION`, `SELF_ROLE_CHANGE`, `LAST_ADMIN` | violacao das regras da RBAC-14 |
| 429 | `LOGIN_LOCKED` | par IP + email bloqueado |

## Requisitos de frontend

Os textos ficam em pt-BR e seguem a UI atual (`style.css`, componentes de `ui.tsx`, mesma topbar e paleta).

**Tela de login**

- E a tela inicial do app: ao abrir, o app consulta `GET /api/auth/me` e mostra o login quando a resposta e 401.
- Pede somente email e senha, com o botao "Entrar".
- Nao tem link de cadastro nem de recuperacao de senha; exibe apenas o texto "Nao tem acesso? Procure um administrador."
- Mensagens de erro:
  - credencial invalida: "Email ou senha invalidos.";
  - bloqueio: "Acesso temporariamente bloqueado. Procure um administrador.";
  - falha de rede: mensagem generica.

**Troca obrigatoria de senha**

- Aparece quando `must_change_password = true`. Pede senha atual, nova senha e confirmacao, e bloqueia o resto do app ate a troca.

**Navegacao**

- O link "Console admin" na topbar e a rota `/admin` aparecem somente para `admin`. Para `user`, `/admin` redireciona ao chat com o aviso "Acesso restrito"; a protecao real e o backend.
- A topbar mostra o nome do usuario e o botao "Sair".
- `chatApi.ts` usa `credentials: 'same-origin'` e para de manipular token.
- Respostas da API:
  - 401: volta ao login com o aviso "Sessao expirada. Entre novamente.";
  - 403 `PASSWORD_CHANGE_REQUIRED`: abre a tela de troca de senha;
  - outros 403: mostra "Acesso restrito".

**Chat**

- Lista o historico proprio (RBAC-13) e permite retomar uma conversa ou iniciar uma nova.

**Aba "Usuarios" no console admin**

- Tabela com nome, email, perfil, status (Ativo/Inativo), indicadores "Troca de senha pendente" e "Login bloqueado", e data de criacao. Tem paginacao, filtro por perfil e status, e busca.
- Botao "Novo usuario" abre um formulario com nome, email, perfil e senha temporaria.
- Acao "Editar" altera nome e perfil.
- Acao "Redefinir senha" gera uma nova senha temporaria.
- Acao "Desativar"/"Reativar" pede confirmacao. A acao fica oculta ou desabilitada na linha do proprio admin, com a dica "Voce nao pode desativar o proprio perfil".
- Acao "Desbloquear login" aparece quando houver bloqueio e lista os IPs bloqueados daquele email.
- A aba Usuarios mostra bloqueios somente de emails cadastrados; tentativas contra emails inexistentes continuam no log de auditoria.
- Nao ha acao de excluir.

**Visualizacao de conversas**

- As conversas de outros usuarios no console sao apenas leitura, sem campo de envio, e mostram o nome/email do dono.

## Requisitos nao funcionais e seguranca

- Senhas com argon2id. Senha, token, hash e cookie nunca sao registrados em log.
- Politica minima de senha: 12 ou mais caracteres, aplicada a senha temporaria, a troca e ao seed.
- Variaveis documentadas apenas por nome em `.env.example`: `JWT_SECRET`, `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD`, `APP_ALLOWED_ORIGINS`, `TRUSTED_PROXY_IPS` e `COOKIE_SECURE`.
- Producao exige HTTPS, pois o cookie e `Secure`.
- Perfil e identidade nao entram no prompt dos agentes, na priorizacao nem no payload ServiceNow.
- Auditoria sem segredos, registrando `user_id` do ator, alvo, IP e timestamp para:
  - login com sucesso, login com falha e bloqueio;
  - desbloqueio;
  - criacao, alteracao, desativacao/reativacao e redefinicao de senha de usuario;
  - troca de senha.

## Criterios de aceite

1. Sem cookie, qualquer rota exceto `/health` e `/api/auth/login` responde 401.
2. Sessao `user` em `/api/admin/*`, `/api/ia-tab/*` ou `/api/tickets*` responde 403 `FORBIDDEN_ROLE`.
3. O user A nao le nem escreve na sessao do user B (404). O admin le a sessao do user B via `/api/admin/conversations/{id}`, mas `POST /api/chat/sessions/{id}/messages` do admin nessa sessao responde 404.
4. Token expirado ou adulterado responde 401 `INVALID_TOKEN`.
5. Desativar um usuario, mudar sua role ou redefinir sua senha invalida a sessao ativa dele na proxima requisicao.
6. A 5a falha consecutiva de login do mesmo IP + email bloqueia o par. A 6a tentativa, mesmo com senha correta, responde 429. O mesmo email de outro IP continua conseguindo entrar. Apos o desbloqueio pelo admin ou pela CLI, o login volta a funcionar.
7. Um usuario criado com senha temporaria e barrado com 403 `PASSWORD_CHANGE_REQUIRED` ate trocar a senha, e depois acessa o chat normalmente.
8. O admin nao consegue desativar o proprio perfil nem alterar a propria role. O ultimo admin ativo nao pode ser desativado nem rebaixado.
9. Nao existe rota de exclusao de usuario.
10. Um `POST` com `Origin` de outro dominio responde 403 `CSRF_REJECTED`.
11. Recarregar a pagina ou abrir nova aba mantem a sessao ate o `exp`. "Sair" retorna ao login.
12. O console admin funciona atras de proxy reverso, sem dependencia de loopback.
13. Apos `purge-legacy --confirm` e a migration, nao restam sessoes, runs, eventos, telemetria, mensagens ou tickets sem dono, e a configuracao de pricing e as fontes de conhecimento continuam intactas.
14. A suite de regressao de decisao (`support-cases.json`) produz o mesmo resultado para `user` e `admin`.
15. A API nao sobe sem `JWT_SECRET` valido.

## Fora de escopo

- OIDC/SSO (Entra ID), MFA, refresh token e revogacao por `jti`.
- Autocadastro, recuperacao de senha por email e envio de email.
- Perfis alem de `user`/`admin` e permissoes granulares.
- Exclusao fisica de usuarios.
- Admin interagir ou responder em conversa de outro usuario.
- Multi-tenant.

## Sources

- `project-context/1.define/prd.md` (escopo sem RBAC e invariante de prioridade)
- `project-context/1.define/sad.md` (console admin restrito a local/demo)
- `project-context/2.build/backend.md` e `project-context/2.build/integration.md` (`ADMIN_LOCAL_ONLY` e remocao de `ADMIN_API_TOKEN`)
- `src/backend/app/main.py` (`local_admin` e rotas `/api/tickets` publicas)
- `src/backend/app/persistence/models.py` (`ChatSession` sem dono e grafo de FKs usado na RBAC-15)
- Decisoes do operador em 2026-10-22:
  - identidade local;
  - admin seed pelo operador e cadastro posterior pelo admin;
  - JWT de 8h sem refresh, em cookie `httpOnly`;
  - sem chat anonimo e com historico proprio;
  - sem solicitante no ticket;
  - bloqueio do par IP + email apos 5 falhas, com desbloqueio manual;
  - senha temporaria com troca obrigatoria no primeiro login;
  - limpeza dos registros sem dono;
  - admin somente le conversas de outros usuarios;
  - CRUD de usuarios sem exclusao e sem autodesativacao;
  - login somente com email e senha, sem registro.

## Assumptions

- Deploy em host unico: frontend (build Vite) e API na mesma origem, atras de proxy reverso com HTTPS. Isso viabiliza `SameSite=Strict` e a checagem de `Origin`.
- O frontend web e o unico cliente HTTP previsto para a API. Backend e PostgreSQL (porta 5432) nao sao outros clientes HTTP da API; em dev com Vite `:5173`, incluir `http://localhost:5173` em `APP_ALLOWED_ORIGINS`.
- Volume pequeno de usuarios, o que torna aceitavel a consulta ao banco por requisicao (RBAC-08).
- O email serve como login e nao e verificado.
- Os dados atuais do banco sao de demo e podem ser descartados (decisao do operador).
- O bloqueio de alteracao da propria role (`SELF_ROLE_CHANGE`) estende a regra de autodesativacao pedida pelo operador, para evitar perda acidental de acesso.

## Open Questions

- Nenhuma pendencia de produto para RBAC no escopo do MVP; a arquitetura ainda deve ser atualizada no SAD/SFS.

## Audit

- 2026-10-22 | persona: product-mgr | action: resolve-open-questions | runtime: crewai | Operador esclareceu cliente HTTP unico (frontend web), decidiu ocultar bloqueios de emails inexistentes na UI e manter troca obrigatoria sem expiracao de senha temporaria. Prompt Trace omitido: decisao documental sem execucao de modelo no runtime da aplicacao.
- 2026-10-22T21:32-03:00 | persona: assistant (pre-@product-mgr) | action: draft-change-request | runtime: crewai (sem alteracao de runtime) | Prompt Trace omitido: rascunho de requisito sem execucao de modelo em runtime.
- 2026-10-22T21:45-03:00 | persona: assistant (pre-@product-mgr) | action: revise-change-request | runtime: crewai | Incorporadas as decisoes do operador: cookie httpOnly, bloqueio IP + email com desbloqueio manual, senha temporaria, limpeza de dados legados, admin somente leitura, CRUD sem exclusao, tela de login. Prompt Trace omitido: rascunho de requisito sem execucao de modelo em runtime.
