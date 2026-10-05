# System Functional Specification (SFS): Multi-Agent Support Flow - MVP Slim

## Context & Instructions

Esta SFS especifica apenas o fluxo funcional P0 integrado do MVP Slim:

`chat -> agents -> conhecimento local -> decisao -> resposta ou ticket -> console admin`

Ela complementa o PRD e o SAD sem expandir escopo. Qualquer item de RBAC, multi-tenant, OIDC, Slack/Teams, vector DB obrigatorio, `handoff_required`, evals sofisticados ou sincronizacoes incrementais fica fora desta SFS.

## Input Requirements

**PRD Document**: `project-context/1.define/prd.md`  
**SAD Document**: `project-context/1.define/sad.md`  
**Feature ID**: `multi-agent-support-flow`  
**Selected Runtime**: `crewai`

## 1. Purpose and Scope

### Purpose

Permitir que um colaborador interno descreva um problema de TI em portugues brasileiro, receba uma resposta com fonte local quando houver evidencia suficiente ou tenha um incidente ServiceNow criado quando as regras do MVP exigirem ticket.

### In Scope

- Criar e continuar sessao de chat.
- Classificar categoria interna, categoria ServiceNow, `impact`, `urgency`, `resulting_priority`, `confidence` e `risk_flags`.
- Buscar fonte aprovada em markdown/FAQ/runbook local.
- Propor `candidate_action` entre `respond`, `ask_clarification`, `open_ticket` e `blocked`.
- Validar seguranca, redacao e fonte suficiente antes da resposta final.
- Persistir `final_action`, conversas, tickets, eventos de agentes e logs redigidos.
- Criar incidente via ServiceNow Table API ou adapter mock/local.
- Exibir conversa, ticket, fonte, decisao e eventos no console admin basico.

### Out of Scope

- `handoff_required` como acao P0.
- Respostas em idioma diferente de portugues brasileiro.
- Vector DB/pgvector obrigatorio.
- RBAC, autenticacao, OIDC, multi-tenant e niveis de acesso.
- Slack/Teams, omnichannel e mobile completo.
- Sincronizacao incremental ServiceNow ou base de conhecimento.
- Acoes externas mutating alem de criar incidente ServiceNow.

## 2. Traceability

| PRD Anchor | SFS Coverage |
| :-- | :-- |
| FR-001 Web Chat | Criacao/continuidade de sessao, envio de mensagem e historico |
| FR-002 Intake & Triage | Taxonomia, impacto, urgencia, confianca e prioridade resultante |
| FR-003 Local Knowledge Search | Fonte local aprovada e criterio de suficiencia |
| FR-004 Response Generation | Resposta pt-BR, fonte exibida e maximo uma pergunta |
| FR-005 QA & Policy Gate | Redacao, bloqueios e validacao de acao final |
| FR-006 ServiceNow Ticketing | Payload Table API, dados minimos e mock/local |
| FR-007 Basic Admin Console | Conversas, tickets, fontes, decisoes e eventos |
| FR-008 QA And Basic Observability | Unit tests, integration test e logs redigidos |

## 3. Inputs

| Input Name | Type / Format | Source | Validation Rules |
| :-- | :-- | :-- | :-- |
| `session_id` | string UUID/local id | Frontend/API | obrigatorio apos criacao; deve existir |
| `message_text` | string | Chat UI | obrigatorio, nao vazio, dentro do limite configurado |
| `clarification_count` | integer | backend state | `0` ou `1` no P0 |
| `conversation_history` | lista redigida | PostgreSQL | historico curto, sem secrets persistidos |
| `knowledge_sources` | sete markdowns ficticios em `knowledge/` | knowledge local | aprovacao somente para demo, path conhecido, categoria interna cadastrada e trecho extraido nao vazio |
| `ticket_adapter_mode` | `mock` ou `servicenow` | `.env` | `mock` para testes; `servicenow` para demo real |
| `servicenow_config` | env vars OAuth | runtime | `SERVICENOW_AUTH_MODE=oauth`; nunca persistir valores secretos |

## 4. Processing Behavior

1. Frontend cria sessao em `POST /api/chat/sessions` quando necessario.
2. Frontend envia mensagem para `POST /api/chat/sessions/{session_id}/messages`.
3. Backend valida input e bloqueia deterministicamente pedidos de revelacao de segredos, credenciais ou dados pessoais de terceiros antes da crew, persistindo `final_action=blocked` e evento redigido sem chamar CrewAI ou ServiceNow. Pedido legitimo de redefinicao de senha nao e bloqueado por essa regra.
4. Para pedidos permitidos, backend cria `request_id` e `agent_run_id`, mascara secrets/PII conhecidos, persiste mensagem redigida e invoca `AgentRuntimeService` com CrewAI em processo sequencial.
5. `IntakeTriageAgent` produz `TriageResult`.
6. Backend valida output Pydantic, taxonomia, mapeamento, `impact`, `urgency`, `confidence` e `resulting_priority` por exclusao P1, senao P2, senao P3, senao P4. Sugestao inicial equivale a `initial_action` de FR-002, sem segundo campo de decisao alem de `candidate_action` e `final_action`.
7. `KnowledgeAgent` busca fonte local quando uma resposta puder depender de conhecimento operacional.
8. Backend considera evidencia elegivel se houver arquivo existente cadastrado como aprovado somente para demo, `internal_category` igual a triagem e `snippet` extraido nao vazio; `QAPolicyAgent` continua responsavel pelo veto de instrucao nao aplicavel ou insegura. Fonte ausente, nao aprovada, vazia ou de outra categoria nao permite `respond`.
9. `ResponseAgent` produz `ResponseDraft` com `candidate_action`.
10. `QAPolicyAgent` aprova ou veta a acao insegura para `blocked`.
11. Cada uma das quatro tasks centrais usa `output_pydantic` (`TriageResult`, `EvidenceSet`, `ResponseDraft`, `PolicyDecision`) e passa somente output validado por `Task.context`; falha interrompe o fluxo com erro redigido e sem POST. Backend valida dados minimos, limite de uma pergunta e contrato de seguranca; se a decisao provisoria for `open_ticket`, solicita e valida `TicketPayloadDraft` antes de gravar `final_action`.
12. Se `final_action=respond`, backend retorna resposta em pt-BR com fonte quando usada.
13. Se `final_action=ask_clarification`, backend retorna uma pergunta objetiva e incrementa `clarification_count`.
14. Para `final_action=open_ticket`, backend usa os dados minimos ja validados: descricao do problema, entendimento de `impact` e entendimento de `urgency`.
15. `TicketingEscalationAgent` prepara `TicketPayloadDraft` redigido antes da decisao persistida (com `output_pydantic` se for task CrewAI), sem acesso a ferramenta mutating; somente o backend chama o adapter ServiceNow real ou mock/local apos validar payload e persistir `final_action=open_ticket`.
16. Backend persiste `TicketRecord`, eventos de agentes e logs redigidos.
17. Console admin lista conversas, tickets, fontes usadas, decisoes finais, eventos e metricas basicas.

## 5. Outputs

| Output Name | Description | Destination |
| :-- | :-- | :-- |
| `TriageResult` | categoria, impacto, urgencia, prioridade, confianca e risco | backend, admin, eventos |
| `EvidenceSet` | titulo/path/trecho da fonte aprovada | response, admin |
| `ResponseDraft` | mensagem proposta, pergunta ou resumo de ticket | policy gate |
| `PolicyDecision` | aprovacao/veto e motivos seguros | backend |
| `TicketPayloadDraft` | campos redigidos para incidente proposto; sem chamada externa pelo agente | backend |
| `final_action` | `respond`, `ask_clarification`, `open_ticket` ou `blocked` | DB, frontend, admin |
| `TicketRecord` | ticket local e dados retornados pelo ServiceNow/mock | DB, admin, chat |
| `ChatResponse` | resposta HTTP final `{ data, error, meta }` | frontend |
| `AgentRunEvents` | eventos estruturados redigidos por etapa | DB/logs/admin |

## 6. Validations and Constraints

- `internal_category` deve ser: `password_reset`, `network_wifi`, `app_access`, `printer_label`, `critical_incident`, `applications_issues` ou `unknown`.
- `servicenow_category` deve ser: `inquiry`, `software`, `hardware`, `network` ou `database`.
- `impact` e `urgency` devem ser `1`, `2` ou `3`.
- `resulting_priority` usa precedencia exclusiva: P1 se `critical_incident` ou (`impact=1` e `urgency=1`); senao P2 se `impact=1` ou `urgency=1`; senao P3 se `impact=2` ou `urgency=2`; senao P4. `impact=1, urgency=2` resulta em P2 salvo `critical_incident`.
- `priority` nao deve ser obrigatorio no payload outbound ServiceNow.
- `confidence >= 0.70` permite seguir sem esclarecimento quando demais criterios forem satisfeitos.
- `confidence < 0.70` exige `ask_clarification` se nenhuma pergunta anterior foi feita.
- `confidence < 0.70` apos uma pergunta gera `open_ticket` quando o pedido for legitimo e dados minimos estiverem seguros.
- Cada conversa pode ter no maximo uma acao `ask_clarification`.
- Fonte elegivel exige cadastro aprovado para demo, categoria interna coincidente e trecho extraido nao vazio; o policy gate valida aplicabilidade e seguranca antes de `respond`. `unknown` nao autoriza resolucao inventada.
- Pedido para revelar secrets, credentials, tokens, passwords, keys ou dados pessoais de terceiros deve gerar `blocked` antes da crew, sem tratar redefinicao legitima de senha como revelacao.
- Logs, eventos, tickets e respostas nao podem conter secrets intencionais.
- QA/policy deve executar antes da resposta final ou chamada mutating externa.

## 7. ServiceNow Payload Contract

Endpoint: `POST /api/now/table/incident`.

Payload P0:

```json
{
  "short_description": "Short issue summary",
  "description": "Relevant redacted context",
  "impact": "2",
  "urgency": "2",
  "category": "software"
}
```

Campos obrigatorios:

- `short_description`
- `description`
- `impact`
- `urgency`
- `category`

Persistir retorno quando disponivel:

- `servicenow_sys_id`
- `servicenow_number`
- `status`
- payload redigido
- adapter usado: `mock` ou `servicenow`

## 8. Error Handling and Exceptions

- Falha de schema interrompe o fluxo, nao encaminha output invalido pelo `Task.context`, nao faz POST e registra `agent_event` redigido.
- Falha de knowledge local escolhe `ask_clarification` ou `open_ticket`; nunca `respond` inventado.
- Falha ServiceNow preserva ticket local com erro reprocessavel e mostra estado no admin.
- Falha de redacao impede persistencia de texto sensivel e retorna erro seguro.
- Pedido de revelacao proibida retorna `blocked` antes da crew; outros pedidos inseguros vetados pelo policy gate nao acionam ServiceNow.
- Erros HTTP usam `{ data: null, error: { code, message, retryable, details }, meta }` com `details` redigidos.

## 9. Acceptance Criteria

- Usuario consegue criar conversa, enviar mensagem e receber uma das quatro acoes P0.
- Resposta baseada em conhecimento mostra titulo/caminho/trecho da fonte.
- Baixa confianca inicial faz no maximo uma pergunta de esclarecimento.
- Baixa confianca persistente apos uma pergunta abre ticket quando dados minimos forem seguros.
- Fonte insuficiente nao gera resposta operacional inventada.
- Pedido inseguro envolvendo secrets ou dados pessoais de terceiros gera `blocked`.
- Bloqueio de revelacao proibida nao invoca a crew; falha de schema nao passa contexto invalido nem aciona o adapter.
- `impact=1, urgency=2` gera P2 salvo `critical_incident`; apenas o backend chama o adapter depois de persistir `final_action=open_ticket`.
- Ticket criado usa apenas `short_description`, `description`, `impact`, `urgency` e `category` como payload outbound obrigatorio.
- `resulting_priority` e exibida/persistida, mas nao exigida como campo outbound ServiceNow.
- Console admin mostra conversa, ticket, fonte, decisao final e eventos dos agentes.
- Testes unitarios cobrem fonte vazia/de categoria errada, prioridade P2, bloqueio pre-crew, schema invalido e ordenacao persistencia/POST; primeiro teste integrado `password_reset` usa PostgreSQL, `TICKET_ADAPTER_MODE=mock` e mostra titulo/caminho/trecho ou numero de incidente mock. Demais fluxos P0 usam os 12 casos em `project-context/1.define/support-cases.json`.
- No dataset, `expected_source` indica a fonte recuperada para a decisao, nao necessariamente exibida ao usuario. `test_mode=deterministic` assume categoria correta, confianca acima do limiar de escalonamento e dados minimos presentes; apenas TC004 (`expected_action=ask_clarification`) pede esclarecimento. TC012 e bloqueado antes da crew, sem categoria ou fonte recuperada. O fixture nao altera a politica de confianca do runtime normal.

## Sources

- `project-context/1.define/prd.md`
- `project-context/1.define/mrd.md`
- `project-context/1.define/sad.md`
- `.github/agents/system-arch.agent.md`
- Solicitacao do operador em 2026-09-26 com decisoes fechadas do MVP Slim
- Plano aprovado pelo operador em 2026-10-05: sete fontes ficticias aprovadas somente para demo, `unknown` limitado a coleta/escalonamento e primeiro fluxo `password_reset`.

## Assumptions

- O runtime resolvido e `crewai`.
- A SFS permanece necessaria porque o fluxo integrado P0 reduz ambiguidade para frontend, backend, integration e QA.
- Sete markdowns ficticios em `knowledge/` foram aprovados pelo operador somente para a demo; `password_reset` e a primeira fatia, e o dataset de 12 casos foi aprovado antes da validacao final do P0.
- O operador definiu OAuth para a PDI ServiceNow; `SERVICENOW_CLIENT_ID` e `SERVICENOW_CLIENT_SECRET` serao configurados por env vars na Build, sem valores secretos versionados.

## Audit

- Data/hora: 2026-09-26T02:23:54-03:00
- Persona id: `system-arch`
- Acao executada: `create-sfs`
- Runtime resolvido: `crewai`
- Ferramentas/arquivos lidos: `AGENTS.md`; `.github/instructions/aamad-core.instructions.md`; `.github/instructions/adapter-crewai.instructions.md`; `aamad.config.yml`; `project-context/1.define/mrd.md`; `project-context/1.define/prd.md`; SAD anterior; SFS anterior.
- Decisao sobre SFS: substituir por SFS menor em vez de excluir, porque o fluxo `chat -> agents -> ticket` e P0, ajuda implementacao/teste e remove duplicacoes ou itens antigos fora do MVP Slim.
- Revisao em 2026-10-05: SFS sincronizada com o SAD para evidencias, precedencia de prioridade, bloqueio pre-crew, schemas CrewAI e POST exclusivo do backend; validacao executada com `.venv/bin/aamad validate --phase define`.
- Decisao do operador em 2026-10-05: autenticacao ServiceNow via OAuth.