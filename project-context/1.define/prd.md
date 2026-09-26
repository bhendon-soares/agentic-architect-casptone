# Product Requirements Document (PRD): Multi-Agent Customer Support Crew - MVP Slim

## 1. Executive Summary

### Problem Statement

Equipes internas de IT Help Desk recebem solicitacoes repetitivas que frequentemente chegam com contexto incompleto, categoria incerta e ausencia de `impact`/`urgency`. Colaboradores precisam de um canal simples em portugues brasileiro para descrever problemas, receber orientacao segura com base em conhecimento local e abrir um incidente ServiceNow qualificado quando o autoatendimento nao for suficiente.

### Solution Overview

O MVP e um chat web para suporte interno de IT Help Desk em portugues brasileiro. Ele usa um workflow sequencial simples em `crewai` para classificar o problema, buscar fontes locais em markdown/FAQ/runbook, responder com fonte quando possivel e criar incidente no ServiceNow PDI quando necessario. Um console admin basico aberto mostra tickets, conversas, fontes, decisoes finais, eventos dos agentes e metricas simples.

### Strategic Rationale

O produto deve provar uma fatia vertical em 5 semanas: `chat -> agentes -> conhecimento local -> decisao -> resposta ou ticket -> console admin`. Ele nao deve virar uma plataforma enterprise de ITSM. Papeis multiagente sao uteis aqui porque intake, busca de conhecimento, redacao de resposta, QA/politica e ticketing possuem responsabilidades distintas e outputs observaveis.

## 2. Market Context & User Analysis

### Target Market / Users

Usuario principal: colaborador interno solicitando suporte de TI em portugues brasileiro.

Usuario operacional: operador/admin da demo que revisa conversas, tickets, fontes, decisoes dos agentes e metricas basicas.

O MVP e single-tenant e nao inclui tipos de usuario, RBAC, niveis de acesso, status VIP, segmentacao por cargo ou prioridade baseada em atributo pessoal.

### User Needs Analysis

- Colaborador precisa de orientacao rapida ou criacao de ticket sem aprender campos do ServiceNow.
- Help Desk precisa receber tickets com contexto suficiente para agir.
- Usuario admin/demo precisa de visibilidade sobre `internal_category`, `servicenow_category`, `impact`, `urgency`, `resulting_priority`, `final_action`, fontes locais e resultado no ServiceNow.
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
- Environment variables / `.env` para secrets.

Integracoes adiadas:

- Slack/Teams, omnichannel, conectores externos de conhecimento, sincronizacao incremental ServiceNow, OIDC, vector DB, APM/SIEM.

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

#### FR-002 Intake & Triage

Historia de usuario: Como operador/admin da demo, quero ver a classificacao do caso para entender a decisao da crew.

Criterios de aceite:

- Gerar `internal_category`, `servicenow_category`, `impact`, `urgency`, `resulting_priority`, `confidence`, `risk_flags` e `initial_action`.
- `internal_category` deve ser uma de: `password_reset`, `network_wifi`, `app_access`, `printer_label`, `critical_incident`, `applications_issues`, `unknown`.
- `servicenow_category` deve ser uma de: `inquiry`, `software`, `hardware`, `network`, `database`.
- `impact` e `urgency` devem ser `1`, `2` ou `3`.
- `confidence >= 0.70` permite seguir sem esclarecimento quando demais criterios forem satisfeitos; `confidence < 0.70` exige uma pergunta de esclarecimento se nenhuma pergunta anterior foi feita; `confidence < 0.70` apos uma pergunta deve resultar em `open_ticket` quando o pedido for legitimo.
- Prioridade nunca deve depender de tipo de usuario, status VIP, cargo, perfil ou atributo pessoal.

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

#### FR-007 Basic Admin Console

Historia de usuario: Como operador/admin da demo, quero revisar tickets, conversas, fontes e decisoes.

Criterios de aceite:

- Listar tickets.
- Mostrar detalhe de conversa/ticket.
- Mostrar fontes usadas.
- Mostrar decisao final e eventos dos agentes.
- Mostrar metricas basicas: total de conversas, tickets criados, respostas com fonte e pedidos bloqueados.

#### FR-008 QA And Basic Observability

Historia de usuario: Como QA Engineer, quero validar as regras essenciais com testes pequenos.

Criterios de aceite:

- Testes unitarios cobrem categorias, impacto, urgencia, prioridade, payload ServiceNow e bloqueio basico de secrets.
- Teste de integracao cobre `chat -> agents -> ticket`.
- Dataset inclui 8-12 casos representativos.
- Logs estruturados e eventos dos agentes ficam visiveis sem persistir secrets intencionais.

### Enhanced Features (Priority P1)

- Adicionar `handoff_required` como acao separada se stakeholders precisarem distinguir criacao automatica de ticket de revisao humana.
- Autenticacao basica/OIDC se a demo virar ambiente compartilhado fora do escopo MVP.
- Busca/ranking local melhorado.
- Sincronizacao de status de incidentes ServiceNow.
- Dashboard operacional mais detalhado.
- Golden dataset com 20-30 casos.

### Future Features (Priority P2)

- Suporte a espanhol e alternancia de idioma.
- Slack/Teams e suporte omnichannel.
- RBAC, multi-tenant, perfis de usuario e visoes baseadas em papel.
- Vector DB/pgvector obrigatorio.
- Sincronizacao incremental da base de conhecimento.
- OpenTelemetry, APM, SIEM e metricas de custo.
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
- Compliance enterprise formal esta fora do escopo do MVP.

### Scalability & Reliability

- MVP single-tenant.
- Console admin aberto no MVP, sem RBAC, niveis de acesso ou autenticacao P0.
- Sem requisito de fila distribuida ou Kubernetes.
- Adapter mock/local suporta confiabilidade de desenvolvimento/teste.
- Escala futura fica adiada ate validacao da fatia vertical.

## 6. User Experience Design

### Interface Requirements

- Tela de chat com historico de mensagens, resposta/pergunta/ticket/bloqueio e exibicao de fonte.
- Tela de lista de tickets.
- Tela de detalhe de conversa/ticket.
- Detalhes admin para fontes, decisao final e eventos dos agentes.
- Visao de metricas basicas.

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

### Technical Metrics

- 8-12 casos de teste representativos.
- Testes unitarios para regras de decisao e ticketing.
- Um teste de integracao para `chat -> agents -> ticket`.
- 0 secrets intencionais persistidos em logs de testes planejados.

### User Experience Metrics

- Resposta mostra fonte local quando fonte for usada.
- No maximo uma pergunta de esclarecimento antes de resposta ou ticket.
- Pedidos inseguros bloqueados recebem recusa segura e orientada a suporte.

## 8. Implementation Strategy

| Semana | Foco | Entregas esperadas |
| :-- | :-- | :-- |
| 1 | Frontend | Chat UI, layout do console admin, lista/detalhe de tickets e detalhe de conversa |
| 2 | Backend | App FastAPI, PostgreSQL local via Docker, modelos relacionais, endpoints de chat/ticket/eventos, adapter ServiceNow/mock |
| 3 | Integracao | Workflow sequencial CrewAI, busca local de conhecimento, decisao final, fluxo chat-para-ticket |
| 4 | QA / Observabilidade Basica | Testes unitarios, teste de integracao, logs estruturados, eventos de agentes no console admin |
| 5 | Deploy / Docs / Ajustes Finais | `.env.example`, runbook de deploy, user guide, ajustes de demo end-to-end |

## 9. Launch & Go-to-Market Strategy

N/A para lancamento comercial. Este e um MVP interno/capstone, nao um produto monetizado. O foco de entrega e prontidao de demo, handoff para SAD/SFS, evidencias de QA e documentacao de deploy.

## Sources

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

- Credenciais e instancia ServiceNow PDI estao disponiveis por environment variables, e o payload outbound confirmado exige somente `short_description`, `description`, `impact`, `urgency` e `category`.
- O MVP permanece single-tenant, somente em portugues brasileiro e com console admin aberto, sem RBAC ou niveis de acesso.
- PostgreSQL local via Docker sera o banco do MVP.
- Arquivos locais de conhecimento serao preparados depois, antes do teste de integracao.
- `handoff_required` foi adiado intencionalmente para P1 para manter pequenos os estados de decisao P0.
- Normalizacao fina de tipos entre aplicacao e ServiceNow, como `impact`/`urgency` numericos ou string no payload, sera resolvida na fase de Build.

## Open Questions

- Quais 8-12 casos representativos definirao o dataset do MVP? Definicao adiada para Build antes do teste de integracao.
- Quais arquivos locais markdown/FAQ/runbook serao fontes aprovadas de conhecimento? Definicao adiada para Build antes do teste de integracao.

## Audit

- Data/hora: 2026-09-26
- Persona id: `product-mgr`
- Acao: `create-prd`
- Runtime resolvido: `crewai` a partir de `aamad.config.yml`
- Uso de ferramentas: leitura local de regras/templates/config AAMAD; consultas web para fundamentacao do MRD; edicoes localizadas via `apply_patch`
- Prompt Trace: omitido porque este PRD e um artefato de planejamento, nao um prompt de runtime de producao; instrucoes e inputs principais estao listados em Sources.