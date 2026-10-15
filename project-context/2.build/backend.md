# Backend P0: leituras admin locais

## Contratos HTTP

Envelope de sucesso: `{ "data": ..., "error": null, "meta": { "request_id": "UUID", "agent_run_id": null } }`. Erros usam o envelope da API (`data:null`, `error.code`, `meta.request_id`): 422 `INVALID_REQUEST` para paginacao invalida, 422 `INVALID_ID` para UUID invalido, 404 `SESSION_NOT_FOUND` e 403 `ADMIN_LOCAL_ONLY` para cliente nao local.

- `GET /api/admin/conversations?limit=20&offset=0`: `limit` de 1 a 100, `offset` >= 0; `data:{items:[...],total:int}` e `meta.limit/offset`. Cada item tem `session_id`, `status`, `created_at`, `updated_at`, `last_activity_at` e `last_run:{final_action,run_status,error_code}|null`. Atividade inclui atualizacao da sessao, mensagens, inicio/fim de runs e atualizacao de tickets. Ordem decrescente de atividade; desempate por `session_id` crescente. Inclui sessoes sem ticket e nao depende do navegador. `last_run` seleciona maior `started_at` (desempate por `agent_run_id` decrescente). Total conta todas as sessoes antes da paginacao.
- `GET /api/admin/conversations/{session_id}`: `data:{session_id,status,created_at,updated_at,clarification_count,messages,runs,tickets}`. Mensagens: `message_id,agent_run_id,role,message_pt_br,created_at`. Runs (todos, inclusive falhos e sem resposta): `agent_run_id,status,started_at,finished_at,final_action,error_code,summary,sources`. `summary=null` e `sources=[]` quando nao houve resposta. Cada fonte tem somente `title,path,snippet`. Tickets associados: `ticket_id,agent_run_id,status,error_code,servicenow_number,created_at,updated_at`. Mensagens, runs e tickets em ordem cronologica com desempate por ID. Campos de texto sao redigidos na leitura; nao ha `response_data` integral, prompts, payload de incidente, configuracao do modelo ou chain-of-thought.
- `GET /api/agent-runs/{agent_run_id}` continua sendo o detalhe dos eventos redigidos por execucao; `GET /api/chat/sessions/{session_id}` e os contratos de chat/ticket nao mudam.
- `GET /api/metrics/summary`: `responses_with_source` conta apenas runs `completed` com `final_action=respond` e `response_data.sources` nao vazio; as demais metricas mantem a semantica anterior.

IDs sao UUID string; datas nos novos endpoints sao UTC ISO 8601 (offset `+00:00`), valores opcionais usam `null`. As consultas de listagem fazem agregacao e classificacao em SQL, com numero fixo de queries por pagina.

## Limite de exposicao

Os novos endpoints admin so aceitam IP de cliente loopback; `testclient` e reservado para o transporte de testes. Nao existe autenticacao/RBAC P0. Inicie o backend em `127.0.0.1`, mantenha o proxy de desenvolvimento apenas local e nao publique o proxy nem encaminhe estes endpoints via proxy externo: um proxy local pode fazer uma requisicao remota parecer loopback. A protecao local nao substitui autenticacao para deploy publico.

## Sources

- `project-context/2.build/backend-funcional-spec.md`, `project-context/2.build/setup.md`, `src/backend/app/main.py`, `src/backend/app/persistence/models.py`, `src/backend/tests/test_api.py`, `aamad.config.yml`.

## Assumptions

- Ambiente de demo controlado com backend e proxy vinculados exclusivamente ao host local; nenhum acesso publico permitido.

## Open Questions

- Autenticacao/RBAC, analytics, streaming e reconciliacao automatica de incidentes nao fazem parte do P0. O fluxo apos esclarecimento sem dados minimos permanece sem aprovacao de produto/integracao.

## Audit

- 2026-10-15: persona `backend-eng`, comandos `*implement-endpoint` e `*document-backend`; `AAMAD_TARGET_RUNTIME=crewai` resolvido pela configuracao do projeto. Sem alteracoes no runtime dos agentes ou integracao ServiceNow.