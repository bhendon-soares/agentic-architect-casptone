# Product Requirements Document (PRD): Multi-Agent Customer Support Crew - MVP Slim

## 1. Executive Summary

### Problem Statement

Equipes internas de IT Help Desk recebem solicitacoes repetitivas que frequentemente chegam com contexto incompleto, categoria incerta e ausencia de `impact`/`urgency`. Colaboradores precisam de um canal simples em portugues brasileiro para descrever problemas, receber orientacao segura com base em conhecimento local e abrir um incidente ServiceNow qualificado quando o autoatendimento nao for suficiente.

### Solution Overview

O MVP e um chat web autenticado para suporte interno de IT Help Desk em portugues brasileiro. Ele usa um workflow sequencial simples em `crewai` para classificar o problema, buscar fontes locais em markdown/FAQ/runbook, responder com fonte quando possivel e criar incidente no ServiceNow PDI quando necessario. Usuarios `user` acessam o chat e o proprio historico; usuarios `admin` acessam tambem um console protegido com tickets, conversas somente leitura, fontes, decisoes finais, eventos dos agentes, metricas e gestao de usuarios.

### Strategic Rationale

O produto deve provar a fatia vertical `login -> chat -> agentes -> conhecimento local -> decisao -> resposta ou ticket -> console admin`. O plano original de 5 semanas deve ser reestimado para incluir autenticacao, migracao, UI e testes de seguranca; nao deve virar uma plataforma enterprise de ITSM. Papeis multiagente sao uteis aqui porque intake, busca de conhecimento, redacao de resposta, QA/politica e ticketing possuem responsabilidades distintas e outputs observaveis.

## 2. Market Context & User Analysis

### Target Market / Users

Usuario principal: colaborador interno solicitando suporte de TI em portugues brasileiro.

Usuario operacional: operador/admin da demo que revisa conversas, tickets, fontes, decisoes dos agentes e metricas basicas.

O MVP e single-tenant e distingue apenas `user` e `admin` para acesso a rotas e telas; nao inclui status VIP, segmentacao por cargo ou prioridade baseada em atributo pessoal. Nao ha chat anonimo nem autocadastro. O primeiro admin e provisionado pelo operador; os demais usuarios sao cadastrados por admin.

### User Needs Analysis

- Colaborador precisa de orientacao rapida ou criacao de ticket sem aprender campos do ServiceNow.
- Help Desk precisa receber tickets com contexto suficiente para agir.
- Usuario admin/demo precisa de visibilidade sobre `internal_category`, `servicenow_category`, `impact`, `urgency`, `resulting_priority`, `final_action`, fontes locais e resultado no ServiceNow.
- Colaborador precisa acessar somente suas conversas e retomar seu historico; admin precisa ler conversas de terceiros sem poder interagir nelas e administrar contas e bloqueios de login.
- Revisor de seguranca precisa de garantia de que secrets, credentials, tokens, passwords e dados pessoais de terceiros sejam bloqueados ou mascarados.

### Competitive Landscape

Suites enterprise como ServiceNow ITSM, Zendesk AI e Salesforce Service Cloud validam a demanda por atendimento assistido por IA, mas excedem o escopo deste capstone. Chatbots RAG genericos podem responder a partir de documentos, mas frequentemente nao possuem estados explicitos de decisao nem contrato de ticketing. Este MVP se diferencia ao combinar workflow multiagente pequeno, respostas com fonte visivel e criacao de incidente ServiceNow.

## 3. Technical Requirements & Architecture

### Runtime & Agent Specifications

Runtime selecionado: `crewai`.

Modo de processo do MVP: sequencial.  
Delegacao padrao: `allow_delegation=false`.  
Memoria: sem memoria global opaca; o estado da conversa e persistido pelo backend.  
Outputs estruturados: cada fase retorna objetos validaveis consumidos pelo backend. `ResponseAgent` propoe `candidate_action`; `QAPolicyAgent` aprova ou veta por seguranca; o backend valida o contrato e grava `final_action` como autoridade final auditavel.

Papeis principais:

| Agente | Papel | Objetivo | Ferramentas | Notas de runtime |
| :-- | :-- | :-- | :-- | :-- |
| `IntakeTriageAgent` | Classificar solicitacao e decidir rota inicial | Produzir categoria, impacto, urgencia, confianca e flags de risco | regras de taxonomia, estado da conversa | task sequencial; output estruturado obrigatorio |
| `KnowledgeAgent` | Buscar na base local de conhecimento | Retornar trechos de fontes locais correspondentes | busca local em markdown/FAQ/runbook | sem vector DB obrigatorio em P0 |
| `ResponseAgent` | Redigir resposta ao usuario | Preparar resposta em pt-BR, pergunta de esclarecimento ou resumo de ticket | estado da conversa, trechos de fonte | sem afirmacoes nao suportadas por fonte |
| `QAPolicyAgent` | Validar seguranca e politica | Aprovar acao final ou bloquear pedido inseguro | detector de secrets/PII, regras de politica | pode vetar output inseguro |
| `TicketingEscalationAgent` | Criar incidente ServiceNow | Montar e enviar payload obrigatorio de incidente | adapter ServiceNow, adapter mock | unica acao externa mutating em P0 |

### Integration Requirements

Integracoes P0:

- API de chat web para sessoes e mensagens de conversa.
- ServiceNow Table API `POST /api/now/table/incident` para criacao de incidente.
- Adapter ServiceNow mock/local para desenvolvimento e testes.
- Repositorio local de conhecimento com arquivos markdown, FAQ ou runbook.
- PostgreSQL local via Docker para dados do app, tickets, conversas, eventos de agentes e logs.
- Usuarios locais e tentativas de login no PostgreSQL; sessao JWT em cookie `httpOnly` com verificacao de identidade e perfil em cada requisicao.
- Environment variables / `.env` para secrets.

Integracoes adiadas:

- Slack/Teams, omnichannel, conectores externos de conhecimento, sincronizacao incremental ServiceNow, OIDC/SSO, MFA, vector DB, APM/SIEM.

### Infrastructure Specifications

- Backend: Python/FastAPI.
- Frontend: React/TypeScript.
- Database: PostgreSQL local via Docker; SQLite nao faz parte do scaffold P0.
- Runtime: configuracao CrewAI deve externalizar definicoes de agents/tasks conforme as regras do adapter ativo.
- Observabilidade: logs estruturados simples e eventos de agentes; sem OpenTelemetry/APM/SIEM completos em P0.

## 4. Functional Requirements

### Core Features (Priority P0)

#### FR-001 Web Chat

Historia de usuario: Como colaborador, quero relatar um problema de TI em pt-BR para receber orientacao ou abrir ticket.

Criterios de aceite:

- Criar e manter uma conversa.
- Enviar e receber mensagens em portugues brasileiro.
- Exibir resultados `respond`, `ask_clarification`, `open_ticket` ou `blocked`.
- Persistir historico da conversa no banco relacional.
- Exigir login e vincular cada sessao ao usuario autenticado; listar e retomar apenas o proprio historico (FR-012).

#### FR-002 Intake & Triage

Historia de usuario: Como operador/admin da demo, quero ver a classificacao do caso para entender a decisao da crew.

Criterios de aceite:

- Gerar `internal_category`, `servicenow_category`, `impact`, `urgency`, `resulting_priority`, `confidence`, `risk_flags` e `initial_action`.
- `internal_category` deve ser uma de: `password_reset`, `network_wifi`, `app_access`, `printer_label`, `critical_incident`, `applications_issues`, `unknown`.
- `servicenow_category` deve ser uma de: `inquiry`, `software`, `hardware`, `network`, `database`.
- `impact` e `urgency` devem ser `1`, `2` ou `3`.
- `confidence >= 0.70` permite seguir sem esclarecimento quando demais criterios forem satisfeitos; `confidence < 0.70` exige uma pergunta de esclarecimento se nenhuma pergunta anterior foi feita; `confidence < 0.70` apos uma pergunta deve resultar em `open_ticket` quando o pedido for legitimo.
- Classificacao, prioridade e decisao dos agentes nunca devem depender de tipo de usuario, status VIP, cargo, perfil ou atributo pessoal. Perfil e identidade nao entram no runtime CrewAI.

#### FR-003 Local Knowledge Search

Historia de usuario: Como colaborador, quero uma resposta baseada em fonte local quando existir orientacao confiavel.

Criterios de aceite:

- Buscar fontes locais em markdown, FAQ ou runbook.
- Retornar titulo/caminho/trecho da fonte quando uma fonte for usada.
- Considerar fonte suficiente quando houver pelo menos um trecho de fonte aprovada com correspondencia clara da categoria interna e instrucao operacional aplicavel ao problema relatado.
- Se a fonte nao atender esse criterio, escolher `ask_clarification` ou `open_ticket`.
- Nao exigir vector DB ou pgvector em P0.

#### FR-004 Response Generation

Historia de usuario: Como colaborador, quero uma resposta clara em portugues brasileiro.

Criterios de aceite:

- Responder em portugues brasileiro.
- Mostrar a fonte local quando a resposta usar material de fonte.
- Fazer no maximo uma pergunta de esclarecimento antes de responder ou abrir ticket.
- Nao inventar procedimento quando a evidencia de fonte for insuficiente.

#### FR-005 QA & Policy Gate

Historia de usuario: Como revisor de seguranca/QA, quero bloquear pedidos inseguros e evitar vazamento de secrets.

Criterios de aceite:

- Detectar e mascarar secrets, credentials, tokens, passwords e keys antes de logar ou criar ticket.
- Bloquear pedidos para revelar secrets, credentials ou dados pessoais de terceiros.
- Evitar PII desnecessaria em logs e tickets.
- A acao final deve ser uma de `respond`, `ask_clarification`, `open_ticket`, `blocked`.

#### FR-006 ServiceNow Ticketing

Historia de usuario: Como colaborador, quero que o sistema abra um incidente quando eu pedir ticket ou quando o caso nao puder ser resolvido pelo chat.

Criterios de aceite:

- Criar incidente no ServiceNow PDI quando `final_action=open_ticket` e houver dados minimos.
- Dados minimos para abrir ticket: descricao do problema, entendimento de `impact` e entendimento de `urgency`.
- Persistir o identificador retornado pelo ServiceNow quando disponivel.
- Usar adapter mock/local para desenvolvimento e testes automatizados.
- Nao exigir `priority` no payload ServiceNow.
- Nao incluir perfil nem identidade do solicitante no payload ServiceNow.

#### FR-007 Basic Admin Console

Historia de usuario: Como operador/admin da demo, quero revisar tickets, conversas, fontes e decisoes.

Criterios de aceite:

- Listar tickets.
- Mostrar detalhe de conversa/ticket.
- Mostrar fontes usadas.
- Mostrar decisao final e eventos dos agentes.
- Mostrar metricas basicas: total de conversas, tickets criados, respostas com fonte e pedidos bloqueados.
- Exigir `admin`; leitura de conversas de terceiros ocorre somente no console, sem envio de mensagens.

#### FR-008 QA And Basic Observability

Historia de usuario: Como QA Engineer, quero validar as regras essenciais com testes pequenos.

Criterios de aceite:

- Testes unitarios cobrem categorias, impacto, urgencia, prioridade, payload ServiceNow e bloqueio basico de secrets.
- Teste de integracao cobre `chat -> agents -> ticket`.
- Dataset inclui 8-12 casos representativos.
- Logs estruturados e eventos dos agentes ficam visiveis sem persistir secrets intencionais.
- Testes de autenticacao, autorizacao, CSRF, revogacao, bloqueio, migracao e regressao de decisao para ambos os perfis cobrem os criterios de FR-010 a FR-015.

#### FR-010 Identidade local e provisionamento (P0; RBAC-01 a RBAC-03)

Historia de usuario: Como operador, quero criar o primeiro admin e permitir que admins cadastrem colaboradores sem autocadastro.

Criterios de aceite:

- Persistir `users` com `user_id` UUID, `email` unico normalizado em minusculas, `display_name` obrigatorio, `password_hash` argon2id, `role` (`user`/`admin`), `is_active` (default true), `must_change_password` (default true), `password_changed_at`, `created_at`, `updated_at` e `created_by` FK nullable somente para o seed.
- `python -m app.cli create-admin` e idempotente, le `ADMIN_SEED_EMAIL` e `ADMIN_SEED_PASSWORD` do ambiente e cria o primeiro admin com `must_change_password=false`; a API nao cria usuarios no startup.
- Admin define senha temporaria na criacao ou redefinicao, marca troca obrigatoria e entrega a senha por canal externo; nao ha envio de email. Seed e senhas temporarias exigem no minimo 12 caracteres. Senha temporaria nao expira no MVP; a troca continua obrigatoria ate ser realizada.

#### FR-011 Login, sessao e protecao de requisicoes (P0; RBAC-04 a RBAC-11)

Historia de usuario: Como colaborador, quero entrar com email e senha, manter minha sessao ao recarregar o app e trocar minha senha quando necessario.

Criterios de aceite:

- `POST /api/auth/login` recebe email e senha; sucesso responde 200 com `{user: {user_id, email, display_name, role, must_change_password}}` e cookie; credencial invalida ou usuario inativo retorna 401 `INVALID_CREDENTIALS` generico.
- JWT HS256 com `sub`, `role`, `iat`, `exp` (8h) e `jti` usa `JWT_SECRET` de no minimo 32 bytes; a API falha no startup sem segredo valido. Nao ha refresh token.
- Token trafega somente no cookie `session`, `HttpOnly`, `Secure` (desligavel somente em dev com `COOKIE_SECURE=false`), `SameSite=Strict`, `Path=/`, `Max-Age=28800`; o frontend nao o le nem armazena. Recarregar ou abrir outra aba preserva a sessao ate expirar.
- Todo `POST`, `PATCH`, `PUT` ou `DELETE`, inclusive login, exige `Origin` presente em `APP_ALLOWED_ORIGINS`, senao retorna 403 `CSRF_REJECTED`; frontend e API em producao compartilham origem HTTPS.
- A cada requisicao autenticada validar assinatura e expiracao, carregar usuario do banco e rejeitar com 401 `INVALID_TOKEN` se estiver inativo, se role divergir ou se `iat < password_changed_at`. Sem cookie retornar 401 `AUTH_REQUIRED`.
- Registrar falhas inclusive para email inexistente por par IP + email normalizado em `login_attempts` (`ip`, `email_normalized`, `failed_count`, `last_failed_at`, `locked_at`, `unlocked_at`, `unlocked_by`). Na quinta falha consecutiva bloquear o par ate desbloqueio manual; durante o bloqueio responder 429 `LOGIN_LOCKED` sem verificar senha, inclusive na sexta tentativa correta; sucesso zera contador. Outro IP para o mesmo email ou outro email no mesmo IP permanece acessivel.
- Usar IP do socket; considerar `X-Forwarded-For` somente quando o socket for um IP em `TRUSTED_PROXY_IPS`. Admin desbloqueia pela UI e operador pela CLI `python -m app.cli unlock-login --email <email> [--ip <ip>]`.
- Com `must_change_password=true`, permitir apenas `GET /api/auth/me`, `POST /api/auth/change-password` e `POST /api/auth/logout`; demais rotas retornam 403 `PASSWORD_CHANGE_REQUIRED`. Troca exige senha atual, nova senha diferente e com 12 ou mais caracteres, atualiza `password_changed_at`, remove a obrigacao e emite novo cookie; serve tambem para troca voluntaria.
- `GET /api/auth/me` retorna usuario atual; `POST /api/auth/logout` apaga cookie com `Max-Age=0`. Logout nao revoga o JWT fora do navegador antes de `exp`; desativacao, troca de role ou senha revogam a sessao na proxima requisicao.

#### FR-012 Conversas proprias e leitura administrativa (P0; RBAC-12 e RBAC-13)

Historia de usuario: Como colaborador, quero ver e retomar apenas minhas conversas; como admin, quero consultar as demais sem alteracao.

Criterios de aceite:

- `chat_sessions.user_id` e FK obrigatoria para `users`; criacao de sessao grava o usuario autenticado.
- `GET /api/chat/sessions/{id}` e `POST /api/chat/sessions/{id}/messages` permitem apenas o dono; sessao alheia retorna 404 `SESSION_NOT_FOUND`, inclusive para admin.
- `GET /api/chat/sessions` lista somente sessoes proprias em ordem da mais recente, paginadas por `limit` e `offset`, permitindo retomada.
- Admin consulta sessoes alheias exclusivamente em `/api/admin/conversations*`, somente leitura e com nome/email do dono; nao pode responder nem continuar conversa de terceiro.

#### FR-013 Gestao administrativa de usuarios (P0; RBAC-14)

Historia de usuario: Como admin, quero cadastrar, alterar, desativar, redefinir senha e desbloquear acessos sem apagar historico.

Criterios de aceite:

- `GET /api/admin/users` e paginado, com filtros por `role`, `is_active` e busca por nome/email. Retorna `user_id`, `email`, `display_name`, `role`, `is_active`, `must_change_password`, `created_at`, `updated_at` e indicador de bloqueio; nunca retorna hash. `GET /api/admin/users/{user_id}` inclui bloqueios ativos (IP e data). A UI mostra bloqueios apenas de emails cadastrados; tentativas para emails inexistentes permanecem no log de auditoria.
- `POST /api/admin/users` recebe email, nome, role e `temporary_password` (12+ caracteres); email duplicado retorna 409 `EMAIL_TAKEN`. `PATCH /api/admin/users/{user_id}` edita nome, role e status, inclusive reativacao. `POST /api/admin/users/{user_id}/reset-password` define senha temporaria e exige troca no proximo login.
- `POST /api/admin/login-locks/unlock` recebe email e IP e registra `unlocked_by`; tambem pode ser executado via CLI no caso de unico admin bloqueado.
- Nao ha `DELETE`; desativar preserva conversas e auditoria. Autodesativacao retorna 409 `SELF_DEACTIVATION`, mudanca da propria role 409 `SELF_ROLE_CHANGE`; desativar ou rebaixar ultimo admin ativo retorna 409 `LAST_ADMIN`.

#### FR-014 Migracao explicita e protecao de rotas (P0; RBAC-15 e RBAC-16)

Historia de usuario: Como operador, quero migrar os dados de demo conscientemente e proteger a API sem dependencia de IP loopback.

Criterios de aceite:

- Antes da migration de `chat_sessions.user_id NOT NULL`, operador executa `python -m app.cli purge-legacy --confirm`, apos backup recomendado com `pg_dump`; o comando mostra contagem e apaga em ordem `agent_events`, `agent_run_attempts`, `agent_run_telemetry`, `agent_run_results_summary`, `chat_messages`, `tickets`, `agent_runs`, `chat_sessions`. A migration falha com mensagem clara se restarem sessoes sem dono e nao apaga dados automaticamente.
- `pricing_config_versions` e `knowledge_sources` sao preservadas; registros locais dos tickets sao apagados, mas incidentes ja criados no ServiceNow nao sao afetados.
- Substituir `local_admin` por verificacao de role em todas as rotas admin; `GET /api/tickets` e `GET /api/tickets/{id}` deixam de ser publicas. Protecao funciona atras de proxy reverso, sem depender de loopback.

Matriz de acesso P0:

| Rotas | Acesso |
| :-- | :-- |
| `GET /health`, `POST /api/auth/login` | Publico; login sujeito a bloqueio e Origin |
| `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/change-password` | Autenticado; permitido durante troca pendente |
| `POST /api/chat/sessions`, `GET /api/chat/sessions` | Autenticado |
| `GET /api/chat/sessions/{id}`, `POST /api/chat/sessions/{id}/messages` | Autenticado e dono |
| `GET /api/tickets`, `GET /api/tickets/{id}`, `/api/admin/conversations*`, `/api/admin/tickets/*`, `/api/admin/users*`, `/api/admin/login-locks/unlock`, `/api/ia-tab/*` | Admin; conversas de terceiros somente leitura |

Erros mantem o envelope `{data, error, meta}`: 401 `AUTH_REQUIRED` (sem cookie), `INVALID_TOKEN` (token ou usuario invalido), `INVALID_CREDENTIALS` (login); 403 `FORBIDDEN_ROLE` (perfil insuficiente), `PASSWORD_CHANGE_REQUIRED`, `CSRF_REJECTED`; 404 `SESSION_NOT_FOUND` (conversa alheia ou ausente); 409 `EMAIL_TAKEN`, `SELF_DEACTIVATION`, `SELF_ROLE_CHANGE`, `LAST_ADMIN`; 429 `LOGIN_LOCKED` (par IP + email). Qualquer rota nao publica sem cookie retorna 401; `user` em `/api/admin/*`, `/api/ia-tab/*` ou `/api/tickets*` retorna 403 `FORBIDDEN_ROLE`.

#### FR-015 Experiencia autenticada e regressao (P0; frontend e aceite RBAC)

Historia de usuario: Como colaborador ou admin, quero navegar com indicacoes claras de acesso e sessao, sem mudar a decisao de suporte por causa do meu perfil.

Criterios de aceite:

- Ao abrir o app, consultar `/api/auth/me`; 401 apresenta login com email, senha, botao "Entrar" e texto "Nao tem acesso? Procure um administrador.", sem cadastro/recuperacao. Credencial invalida mostra "Email ou senha invalidos."; bloqueio mostra "Acesso temporariamente bloqueado. Procure um administrador."; rede mostra erro generico.
- Se troca obrigatoria, exibir tela exclusiva de senha atual, nova e confirmacao. Topbar mostra nome e botao "Sair". `/admin` e link "Console admin" aparecem apenas para admin; `user` em `/admin` volta ao chat com "Acesso restrito". Frontend usa `credentials: 'same-origin'`; 401 apos login redireciona com "Sessao expirada. Entre novamente.", 403 `PASSWORD_CHANGE_REQUIRED` abre troca, demais 403 mostram "Acesso restrito".
- Chat lista e retoma historico proprio ou inicia conversa. Aba "Usuarios" lista nome, email, perfil, status, troca pendente, login bloqueado e criacao, com paginacao, filtros e busca; permite novo usuario, editar nome/role, redefinir senha, confirmar desativacao/reativacao e desbloquear IPs. Autodesativacao fica oculta/desabilitada com dica "Voce nao pode desativar o proprio perfil"; nao ha exclusao. Console mostra nome/email do dono e nao oferece envio em conversa de terceiro. Textos em pt-BR, visual da UI existente.
- A suite `support-cases.json` produz as mesmas classificacoes, prioridades e decisoes para `user` e `admin`; perfil e identidade nao entram no prompt da crew nem no ticket ServiceNow.

### Enhanced Features (Priority P1)

- FR-009 Aba IA no console admin existente (detalhada abaixo).
- Adicionar `handoff_required` como acao separada se stakeholders precisarem distinguir criacao automatica de ticket de revisao humana.
- SSO/OIDC e MFA para evolucao de identidade apos o MVP; autenticacao local ja e P0.
- Busca/ranking local melhorado.
- Sincronizacao de status de incidentes ServiceNow.
- Golden dataset com 20-30 casos.

#### FR-009 Aba IA: consumo, custo, latencia e resultados (P1)

Historia de usuario: Como operador/admin, quero visualizar em uma aba IA do console existente o consumo, o custo estimado, o tempo e o resultado de cada execucao para entender operacao e gastos sem confundir falta de telemetria com valor zero.

Criterios de aceite:

- A aba IA reutiliza o console admin, seus filtros e navegacao para o detalhe da conversa e da execucao; nao cria produto ou console separado. Oferece filtros por periodo, modelo, etapa e resultado, graficos de evolucao e distribuicao, indicadores resumidos e tabela/painel de detalhe por `agent_run_id` e etapa. Exibe unidade, moeda, periodo e tamanho da amostra nas agregacoes; estados vazios distinguem ausencia de execucoes e ausencia de telemetria.
- Para cada etapa, registrar `agent_run_id`, identificador da etapa, modelo efetivamente utilizado, inicio e fim, estado e consumo reportado pela `Crew` executada nessa etapa. Em sucesso, CrewAI oferece consumo agregado por `Crew`/etapa (entrada, saida, total e cache quando informados pelo provider), mas seus normalizadores podem preencher campos ausentes com zero e derivar total de entrada + saida: a presenca do campo em `CrewOutput` nao comprova medicao. Registrar cada campo como medido somente com evidencia confiavel do provider/adapter; caso contrario, exibir **"nao disponivel"**, sem inferir cache ou total. Somar por `agent_run_id` apenas campos medidos, indicando cobertura parcial; total agregado so e exibido quando todos os totais das etapas incluidas tem evidencia. Quando `kickoff()` falha, o runtime atual nao recebe `CrewOutput` nem persiste consumo parcial: exibir consumo **"nao disponivel"** nessa etapa, sem presumir zero.
- Calcular custo por modelo e etapa somente a partir dos tokens medidos e de tabela de precos configurada com identificador exato de modelo/deployment, moeda, vigencia (inicio/fim) e tarifa por tipo de token aplicavel (entrada, saida e cache quando cobrado). Quando tokens em cache forem subconjunto dos de entrada, precificar entrada nao armazenada e cache separadamente, sem dupla contagem; se essa relacao nao puder ser confirmada, o custo fica indisponivel. Usar a tarifa vigente na data da execucao, preservando a versao do preco para auditoria historica. Identificar todo custo como **"estimativa"**; sem tarifa aplicavel, moeda compativel ou consumo suficiente, mostrar **"nao disponivel"**, jamais custo zero ficticio. A aba IA usa apenas USD, sem conversao cambial. Os precos de referencia informados para GPT-6 Sol nao comprovam equivalencia com o deployment contratado no Azure Foundry.
- Medir duracao de cada etapa do inicio ao fim, inclusive etapas com falha, com detalhe por execucao/tentativa. Apresentar media e p95 de duracoes concluidas no periodo filtrado, com amostra e metodo de p95 (nearest-rank); execucoes em andamento aparecem separadamente, sem duracao final ficticia. Distinguir latencia de etapa de latencia total do `agent_run_id`.
- Contar separadamente (a) falha de etapa, (b) tentativa real do modelo, (c) nova tentativa operacional do fluxo e (d) replay de resposta por idempotencia. Tentativa real exige telemetria observada do runtime/provider; `successful_requests` nao conta necessariamente falhas nem retries internos e nao e proxy para tentativas reais. Sem evidencia do numero de chamadas/tentativas internas, mostrar **"nao disponivel"**, nao inferir uma tentativa a partir de `kickoff()` bem-sucedido. Nova tentativa operacional possui execucao propria e referencia a original; replay reutiliza resposta persistida e nao incrementa execucoes, tokens, custo ou falhas de etapa. Exibir os quatro contadores com definicoes no painel.
- Classificar o resultado de cada `agent_run_id` terminal como `respond` (resolvido pelo chat), `open_ticket` (escalonado) ou `blocked` (bloqueado). Exibir `ask_clarification`, falha sem acao final e execucao em andamento como grupos separados. Percentuais de resolucao/escalonamento/bloqueio usam apenas execucoes terminais dessas tres classes como denominador, exibido ao lado da contagem dos grupos inconclusivos; sem casos terminais, exibir **"nao disponivel"** em vez de 0%. Replays nao entram no denominador. Bloqueios antes da crew aparecem com consumo **"nao disponivel"**, sem atribuir tokens zero.
- Dados de telemetria nao podem conter prompts, respostas brutas, secrets ou PII; a aba respeita a redacao dos eventos existente. Registros anteriores ao incremento permanecem visiveis com metricas ausentes como **"nao disponivel"**. Testes cobrem dados parciais/ausentes, vigencia e falta de preco, moedas distintas, falha, tentativa observada vs. desconhecida, retry operacional, replay idempotente, p95 e denominadores de resultado.

Precos de referencia informados pelo operador para GPT-6 Sol, USD por 1 milhao de tokens: entrada 2,00; entrada em cache 0,20; escrita de cache 2,50; saida 10,00. Exemplos sem cache: 2.000 tokens de entrada + 500 de saida = USD 0,009; 10.000 + 2.000 = USD 0,040; 1.000 interacoes simples (2 milhoes + 500 mil) = USD 9,00. Sao exemplos calculados com esses precos, nao medicoes de uso nem previsao de fatura; o custo do benchmark ("Estimated cost: 54.63") nao e tarifa. Os valores de referencia devem ser exibidos separadamente dos custos medidos, mesmo antes da ativacao da tarifa do deployment.

Dependencia para habilitar estimativas por execucao na aba IA: confirmar no Azure Foundry o SKU efetivo de `azure/gpt-6-sol`, tipo e regiao do deployment, faixa de contexto, aplicabilidade dos precos informados e inicio/fim de vigencia; cadastrar a tarifa aplicavel e dispor de consumo confiavel. O nome configurado nao comprova esses dados; sem acesso ao deployment, a confirmacao permanece pendente. A data de publicacao da fonte nao define inicio de vigencia contratual. Ate a confirmacao e cadastro de tarifa aplicavel e consumo suficiente, mostrar custo por execucao **"nao disponivel"**, nunca custo zero ficticio; os precos de referencia continuam visiveis.

### Future Features (Priority P2)

- Suporte a espanhol e alternancia de idioma.
- Slack/Teams e suporte omnichannel.
- Multi-tenant, perfis alem de `user`/`admin` e permissoes granulares.
- Vector DB/pgvector obrigatorio.
- Sincronizacao incremental da base de conhecimento.
- OpenTelemetry, APM e SIEM completos (alem da telemetria de custo P1).
- LLM-as-judge e evals sofisticados.
- Acoes externas mutating alem da criacao de incidente ServiceNow.

### Decision Rules, Taxonomy & Priority

#### Allowed Actions

- `respond`
- `ask_clarification`
- `open_ticket`
- `blocked`

Regras:

- Usar `respond` quando a categoria for compreendida, a fonte for suficiente quando necessaria e nao houver risco de seguranca.
- Usar `ask_clarification` quando um detalhe essencial estiver ausente e nenhuma pergunta de esclarecimento ja tiver sido feita.
- Usar `open_ticket` quando o usuario pedir ticket explicitamente e houver dados minimos, a confianca continuar baixa apos uma pergunta, a fonte for insuficiente ou suporte humano for necessario.
- Usar `blocked` para pedidos inseguros envolvendo secrets, credentials, tokens, passwords, keys ou dados pessoais de terceiros.
- `QAPolicyAgent` pode vetar qualquer `candidate_action` insegura para `blocked`; o backend e a autoridade final para persistir `final_action` depois de validar schema, dados minimos e contrato de seguranca.
- `handoff_required` nao e P0; fica em P1.

#### Internal Categories

- `password_reset`
- `network_wifi`
- `app_access`
- `printer_label`
- `critical_incident`
- `applications_issues`
- `unknown`

#### ServiceNow Categories

- `inquiry`
- `software`
- `hardware`
- `network`
- `database`

#### Category Mapping

| `internal_category` | `servicenow_category` |
| :-- | :-- |
| `password_reset` | `inquiry` |
| `network_wifi` | `network` |
| `app_access` | `software` |
| `printer_label` | `hardware` |
| `critical_incident` | `software` |
| `applications_issues` | `software` |
| `unknown` | `inquiry` |

#### Impact & Urgency

- `1 = high`
- `2 = medium`
- `3 = low`

#### Resulting Priority

- `P1 critical`: `internal_category=critical_incident` ou `impact=1` e `urgency=1`.
- `P2 high`: `impact=1` ou `urgency=1`, quando nao for P1.
- `P3 normal`: `impact=2` ou `urgency=2`, quando nao for P1/P2.
- `P4 low`: `impact=3` e `urgency=3`.

A prioridade deve ser derivada somente de categoria, impacto e urgencia.

### ServiceNow Ticketing Contract

Endpoint: `POST /api/now/table/incident`.

O contrato do MVP esta confirmado: o payload outbound exige somente os campos abaixo.

Campos obrigatorios do payload:

```json
{
  "short_description": "Short issue summary",
  "description": "Relevant redacted context",
  "impact": "2",
  "urgency": "2",
  "category": "software"
}
```

Regras do contrato:

- `short_description`, `description`, `impact`, `urgency` e `category` sao obrigatorios.
- `category` deve usar uma categoria ServiceNow permitida.
- `priority` nao deve ser obrigatorio no payload de saida.
- `resulting_priority` e calculada pela aplicacao para exibicao, auditoria e testes.
- Secrets e PII desnecessaria devem ser mascarados ou removidos antes da persistencia e de chamadas externas.
- Identidade e perfil do usuario nao sao enviados ao ServiceNow.

## 5. Non-Functional Requirements

### Performance Requirements

- O MVP deve parecer responsivo em condicoes de demo; nenhuma meta p95 rigida e prometida.
- O processamento de mensagens do chat deve completar dentro de uma janela pratica de demo para 8-12 casos.
- Timeout e erro em chamada ServiceNow devem produzir evento de falha visivel no admin.

### Security & Compliance

- Sem secrets em codigo, logs, Prompt Trace, datasets ou tickets.
- Secrets carregados por environment variables.
- Redacao/mascara basica para tokens, passwords, keys e credentials.
- Bloquear pedidos inseguros envolvendo secrets ou dados pessoais de terceiros.
- Hash de senha com argon2id; senhas, hashes, tokens e cookies nunca entram em logs. Politica de 12+ caracteres no seed, senhas temporarias e trocas. Variaveis apenas por nome em `.env.example`: `JWT_SECRET`, `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD`, `APP_ALLOWED_ORIGINS`, `TRUSTED_PROXY_IPS`, `COOKIE_SECURE`.
- Producao exige HTTPS, cookie `Secure` e origem permitida em toda mutacao. Registrar auditoria sem segredos com ator (`user_id` quando houver), alvo, IP e timestamp para login com sucesso/falha/bloqueio, desbloqueio, criacao/alteracao/desativacao/reativacao/reset de usuario e troca de senha.
- Compliance enterprise formal esta fora do escopo do MVP.

### Scalability & Reliability

- MVP single-tenant.
- MVP single-tenant com autenticacao local e controle de acesso `user`/`admin` por requisicao; sem fila distribuida ou Kubernetes.
- Adapter mock/local suporta confiabilidade de desenvolvimento/teste.
- Escala futura fica adiada ate validacao da fatia vertical.

## 6. User Experience Design

### Interface Requirements

- Tela de chat com historico de mensagens, resposta/pergunta/ticket/bloqueio e exibicao de fonte.
- Tela de lista de tickets.
- Tela de detalhe de conversa/ticket.
- Detalhes admin para fontes, decisao final e eventos dos agentes.
- Visao de metricas basicas.
- Em P1, aba IA no console atual com graficos e paineis de consumo, custo estimado, latencia, falhas/tentativas e resultados, com acesso ao detalhe de cada execucao.
- Tela inicial de login e troca obrigatoria de senha; topbar com nome e logout. Chat com historico proprio paginado, retomada e nova conversa. Console admin exclusivo de `admin`, aba Usuarios e conversas de terceiros em modo leitura. Manter paleta, componentes e textos em pt-BR da UI atual.

### Agent Interaction Design

- Mostrar justificativa curta e estruturada da decisao final.
- Nao expor raciocinio oculto ou chain-of-thought.
- Mostrar metadados da fonte quando usados.
- Mostrar resultado do ticket com ServiceNow ID quando disponivel.

## 7. Success Metrics & KPIs

### Business / Operational Metrics

- Chat consegue abrir e manter uma conversa.
- Pelo menos 5 categorias principais classificadas no dataset de demo.
- Ticket ServiceNow criado com campos obrigatorios.
- Console admin mostra ticket, conversa, fonte e decisao final.
- Colaborador acessa somente conversas proprias; admin pode ler as de outros usuarios no console, sem interagir nelas.

### Technical Metrics

- 8-12 casos de teste representativos.
- Testes unitarios para regras de decisao e ticketing.
- Um teste de integracao para `chat -> agents -> ticket`.
- Criterios RBAC-01 a RBAC-16 e aceite 1-15 do change request cobertos por testes de auth, CSRF, ownership, bloqueio, revogacao, migracao e rotas sob proxy; regressao da decisao identica para ambos os perfis.
- 0 secrets intencionais persistidos em logs de testes planejados.
- Em P1, cobertura de telemetria por etapa e amostra exibidas com as metricas; ausencia de tokens, preco ou tentativas observadas nao e tratada como zero.

### User Experience Metrics

- Resposta mostra fonte local quando fonte for usada.
- No maximo uma pergunta de esclarecimento antes de resposta ou ticket.
- Pedidos inseguros bloqueados recebem recusa segura e orientada a suporte.
- Sessao sobrevive a reload/nova aba ate expiracao; logout retorna ao login; troca obrigatoria impede acesso ao chat ate concluir.

## 8. Implementation Strategy

| Semana | Foco | Entregas esperadas |
| :-- | :-- | :-- |
| 1 | Frontend + Auth | Chat UI, login, troca de senha, historico e console admin exclusivo por perfil |
| 2 | Backend + migracao | FastAPI/PostgreSQL, purge explicito e migration, seed/CLI, JWT/cookie, CSRF, bloqueio e autorizacao por dono/role |
| 3 | Integracao | Workflow sequencial CrewAI, conhecimento local, decisao final, fluxo chat-para-ticket; UI Usuarios e conversas somente leitura |
| 4 | QA / Seguranca | Testes unitarios e de integracao, matriz RBAC, regressao de decisao por perfil, auditoria, proxy e revisao de seguranca |
| 5 | Deploy / Docs / Ajustes Finais | `.env.example`, HTTPS/proxy confiavel, runbook de backup/purge/seed, user guide e demo end-to-end |

O cronograma acima mostra frentes de trabalho, nao uma nova promessa de cinco semanas: `@project.mgr` deve reestimar prazo, dependencias e capacidade apos revisao do SAD/SFS por `@system.arch`, antes do Build. A aba IA continua P1; proteger suas rotas e P0.

## 9. Launch & Go-to-Market Strategy

N/A para lancamento comercial. Este e um MVP interno/capstone, nao um produto monetizado. O foco de entrega e prontidao de demo, handoff para SAD/SFS, evidencias de QA e documentacao de deploy.

## Sources

- `project-context/1.define/rbac-change-request.md`, revisado pelo operador em 2026-10-22: RBAC-01 a RBAC-16, matriz de acesso, frontend, seguranca e 15 criterios de aceite; fonte da mudanca P0.
- Microsoft Azure, "GPT-6 Astra, Sol, and Luna: For production agents in Microsoft Foundry", tabela "GPT-6 pricing and deployment options", acessado em 2026-10-19: https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/ (precos publicos de referencia; nao contrato do deployment).
- Solicitacao do usuario, 2026-10-19: conclusoes de pesquisa sobre normalizacao da telemetria CrewAI, limites de `successful_requests` e de `kickoff()` com falha, hipoteses de consumo para planejamento e ausencia de acesso ao deployment Azure.
- Solicitacao do usuario, 2026-10-19: incremento P1 de observabilidade e aba IA no console existente; runtime executa uma crew por etapa; Azure Foundry `gpt-6-sol`.
- `project-context/1.define/mrd.md`: pesquisa de mercado, riscos, fontes e recomendacao de MVP.
- Solicitacao do usuario, 2026-09-26: escopo MVP Slim e plano de 5 semanas.
- `AGENTS.md`: workflow AAMAD e sequencia de handoff.
- `.github/instructions/aamad-core.instructions.md`: regras de artefatos e idioma do AAMAD.
- `.cursor/templates/prd-template.md`: estrutura do PRD.
- `aamad.config.yml`: runtime selecionado `crewai`, linguagem primaria Python e preferencias de teste/seguranca.
- Documentacao ServiceNow Developer Table API, acessado em 2026-09-26, https://developer.servicenow.com/dev.do#!/reference/api/yokohama/rest/c_TableAPI
- Documentacao CrewAI, acessado em 2026-09-26, https://docs.crewai.com/
- Documentacao FastAPI, acessado em 2026-09-26, https://fastapi.tiangolo.com/
- OWASP Top 10 for LLM Applications 2025, acessado em 2026-09-26, https://genai.owasp.org/llm-top-10/

## Assumptions

- Exemplos de referencia de FR-009 usam os precos informados pelo operador em USD e volumes ilustrativos sem cache (2.000/500, 10.000/2.000 e 1.000 vezes 2.000/500); nao representam consumo medido nem confirmacao da tarifa contratada.
- FR-009 permanece incremento P1; este change request altera o escopo P0 e exige reestimativa do prazo original. Precos continuam cadastrados, nao inferidos do provider.
- Credenciais e instancia ServiceNow PDI estao disponiveis por environment variables, e o payload outbound confirmado exige somente `short_description`, `description`, `impact`, `urgency` e `category`.
- O MVP permanece single-tenant e em portugues brasileiro, com identidade local, perfis `user`/`admin` e console autenticado.
- O frontend web e o unico cliente HTTP previsto para a API; o backend atende essas requisicoes e usa PostgreSQL via porta 5432, que nao e cliente HTTP da API. Frontend e API de producao compartilham origem atras de proxy reverso HTTPS; em dev com Vite `:5173`, essa origem deve constar de `APP_ALLOWED_ORIGINS`. Volume pequeno permite consulta ao banco por requisicao. Email e login sem verificacao; dados existentes sao de demo e podem ser descartados pelo operador apos backup. Bloquear propria troca de role evita perda acidental de acesso.
- PostgreSQL local via Docker sera o banco do MVP.
- Fontes locais aprovadas somente para a demo: `knowledge/password_reset.md`, `knowledge/app_access.md`, `knowledge/applications_issues.md`, `knowledge/network_wifi.md`, `knowledge/printer_label.md`, `knowledge/critical_incident.md` e `knowledge/unknown.md`; `unknown` serve apenas para esclarecimento/escalonamento, nao para resolucao operacional.
- `handoff_required` foi adiado intencionalmente para P1 para manter pequenos os estados de decisao P0.
- Normalizacao fina de tipos entre aplicacao e ServiceNow, como `impact`/`urgency` numericos ou string no payload, sera resolvida na fase de Build.
- Os 12 casos representativos foram definidos em `project-context/1.define/support-cases.json` para uso no teste de integracao.

## Open Questions

- Reestimar cronograma de entrega com `@project.mgr` apos atualizar SAD/SFS: o plano anterior de 5 semanas nao inclui a nova superficie P0.
- As duas perguntas de pesquisa de FR-009 foram encerradas com as conclusoes acima; os quatro precos de referencia foram informados pelo operador. A confirmacao de aplicabilidade ao deployment, contrato e vigencia no Azure permanece dependencia de habilitacao do custo por execucao.
- Nenhuma em aberto para as fontes de conhecimento do MVP P0.

## Audit

- 2026-10-22: `product-mgr`, acao `resolve-rbac-open-questions`: operador esclareceu que frontend web e o unico cliente HTTP previsto para a API; backend e PostgreSQL nao sao clientes HTTP. Decidiu nao mostrar bloqueios de emails inexistentes na UI e manter troca obrigatoria sem prazo de expiracao da senha temporaria. Runtime: `crewai` conforme `aamad.config.yml`; leitura local e edicao via `apply_patch`. Prompt Trace omitido: decisao de escopo documental sem execucao do runtime.
- 2026-10-22: `product-mgr`, acao `update-prd`: incorporou `rbac-change-request.md` ao P0 (FR-010 a FR-015), substituiu console aberto por autenticacao local/RBAC, preservou independencia das decisoes da crew e manteve aba IA P1; SAD/SFS e plano do Build exigem revisao posterior. Runtime: `crewai` conforme `aamad.config.yml`; ferramentas: leitura local de PRD, change request, template, regras e configuracao, edicao via `apply_patch`, verificacao textual/diff. Prompt Trace omitido: artefato de planejamento sem execucao de modelo no runtime da aplicacao.
- 2026-10-19: `product-mgr`, acao `update-prd`: encerrou as duas perguntas de pesquisa da FR-009. Fontes: conclusoes fornecidas pelo usuario sobre CrewAI/runtime e tabela publica da Microsoft Azure (Sources); hipotese ilustrativa sem cache de 1.000 tokens de entrada + 500 de saida por etapa, cinco etapas e 1.000 execucoes, resultando em USD 0,007/etapa, USD 0,035/execucao e USD 35/1.000 execucoes. Decisoes: exigir evidencia de uso bruto para superar zeros/totais normalizados, nao usar `successful_requests` como tentativas nem benchmark como tarifa, nao presumir consumo em falha, nao inferir SKU/preco/vigencia de `azure/gpt-6-sol` ou da data de publicacao; confirmacao no Foundry permanece dependencia antes de estimar custos na aba IA. P1 mantido, P0 inalterado.
- 2026-10-19: `product-mgr`, acao `update-prd`: adicionou FR-009 como incremento P1; custo saiu de P2, preservando OpenTelemetry/APM/SIEM completos em P2. Base: solicitacao do usuario e contrato de execucao observado no runtime; precos e contagem de tentativas internas nao foram presumidos. Validacao: `git diff --check`; `aamad validate` indisponivel (comando nao instalado).
- Data/hora: 2026-09-26
- Persona id: `product-mgr`
- Acao: `create-prd`
- Runtime resolvido: `crewai` a partir de `aamad.config.yml`
- Uso de ferramentas: leitura local de regras/templates/config AAMAD; consultas web para fundamentacao do MRD; edicoes localizadas via `apply_patch`
- Prompt Trace: omitido porque este PRD e um artefato de planejamento, nao um prompt de runtime de producao; instrucoes e inputs principais estao listados em Sources.