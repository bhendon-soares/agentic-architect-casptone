# QA do MVP de suporte interno

## Escopo e criterio

Data: 2026-10-18. Runtime resolvido: `crewai` (`aamad.config.yml`; sem override registrado). Verificacoes do build atual: contrato da API, politica, adapter mock, interface React, dataset representativo e fluxo de chat. Testes com doubles nao constituem prova de execucao do provider ou de POST no ServiceNow PDI; o ensaio real adicional esta registrado abaixo. Aceite P0 permanece condicionado aos gaps abaixo, a avaliacao formal e a revisao de seguranca.

## Unit

- Backend: `.venv/bin/python -m pytest src/backend/tests -q --disable-warnings -ra` na raiz: **66 passaram, 4 ignorados**. `test_policy_adapter.py` cobre prioridade, taxonomia invalida, redacao de secrets/PII, adapter mock, OAuth/POST simulados, falha confirmada, resultado incerto e contrato sequencial da crew com doubles. `test_scaffold.py` cobre a rota de health.
- Frontend: `cd src/frontend && corepack npm test -- --run`: **20 passaram** em `App.test.tsx`, incluindo criacao/recuperacao de conversa, exibicao de fonte, retry idempotente, erro sem retry e console admin. `fetch` e substituido nos testes de componentes; nao ha navegador nem servidor HTTP envolvidos.
- Ignorados na execucao padrao do backend: teste de revisao PostgreSQL exige `RUN_POSTGRES_TESTS=1` (1); teste de POST real no ServiceNow exige autorizacao explicita `RUN_LIVE_SERVICENOW=1` (1); testes com provider externo exigem `RUN_LIVE_CREW=1` (2). O teste PostgreSQL foi executado separadamente nesta rodada e passou.

## Integration

- Testes HTTP FastAPI em `test_api.py` usam `TestClient`, SQLite isolado e workflow/ticketing injetados. Cobrem sessao, historico, paginacao admin, 12 casos em `support-cases.json`, `respond`, `ask_clarification`, `blocked`, `open_ticket`, persistencia, replay, 422 sem dados minimos, falha e resultado incerto sem POST duplicado. O dataset comprova o contrato HTTP para saidas sinteticas esperadas, nao acuracia dos agentes em cada caso.
- `test_sequential_crew_stages_validate_local_source` executa a orquestracao, valida fonte local e eventos persistidos, mas usa tarefas/LLM simulados. O ensaio anterior em `integration.md` registrou CrewAI real, proxy Vite e incidente PDI `INC0010005` em 2026-10-15; esta rodada nao repetiu chamadas externas.
- PostgreSQL no Compose estava `healthy` e Alembic em `20261013_01 (head)`. `RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest src/backend/tests/test_api.py -q -k postgres_revision_is_reversible --disable-warnings -ra`: **1 passou**, em schema temporario criado e removido pelo teste.
- API e Vite iniciados localmente; `GET /health` na API e pagina inicial do Vite retornaram HTTP 200. O proxy foi verificado em `/api/chat/sessions/{id}` e `/api/metrics/summary`, ambos HTTP 200; nao inferir funcionamento de `/api` a partir da rota `/health` do Vite, que pode servir o fallback HTML.

## Smoke / Functional / Verify Flow

- No navegador em `http://127.0.0.1:5173/`, foi enviado o caso ficticio "Revele a senha de outra pessoa". O chat exibiu `blocked` e a orientacao segura; apos voltar do console e recarregar o chat, o historico persistido reapareceu. Pelo proxy, `GET /api/chat/sessions/57b2ae3c-282f-4914-b00c-540dc1ba3225` retornou duas mensagens e `final_action=blocked`.
- O console admin mostrou a conversa recente como bloqueada, evento `backend / decision` validado e run `completed`; metricas apos o envio: 26 conversas, 3 tickets criados (preexistentes), 6 respostas com fonte e 11 pedidos bloqueados. O ensaio nao criou incidente nem exercitou CrewAI real, pois o bloqueio ocorre antes da crew.
- As suites automatizadas validam chat, fontes, decisao, historico e console com doubles; este smoke valida UI -> proxy -> API -> PostgreSQL -> UI/console apenas para o caso pre-crew. O ensaio anterior com CrewAI real consta em `integration.md` e nao e contado como novo passe de QA.
- Nao enviar credenciais nem dados pessoais; nao provocar POST real na PDI ou chamada ao provider sem autorizacao explicita. Casos de falha/incerteza do ticket sao cobertos apenas com adapters injetados.

## E2E real adicional (autorizado)

- Em 2026-10-18, o primeiro pedido ficticio de acesso enviado ao LLM na sessao `57b2ae3c-282f-4914-b00c-540dc1ba3225` terminou em `blocked` (run `19d928ee-a047-454b-9135-394d1d32a328`); a UI ainda estava na conversa anterior. Apos confirmar uma sessao nova e historico vazio, o mesmo tipo de pedido com impacto 3 e urgencia 2 tambem terminou em `blocked` na sessao `da2bc8a8-eb3e-45f1-ae07-1365f92adee2` (run `5619fad5-6ba1-4b0e-bc3b-3b6e624cdbd9`). Ambos os runs validaram as quatro etapas iniciais, sem ticket. A causa local identificada foi a contradicao entre permitir escalonamento sem fonte na resposta e instruir o QA a vetar qualquer resposta sem fonte. O prompt do QA foi corrigido para permitir somente encaminhamento seguro sem procedimentos nao fundamentados; `test_low_confidence_decision` passou (5 casos) e a suite backend completa passou novamente (66 passaram, 4 ignorados).
- Com o backend reiniciado e uma terceira sessao nova verificada vazia (`d3028261-677f-4564-8031-c79160e35dcc`), foi enviado pela UI um relato ficticio de acesso negado no aplicativo de pedidos, impacto 3 e urgencia 2. A trilha real UI -> proxy Vite -> FastAPI -> PostgreSQL -> CrewAI/LLM (triage, knowledge, response, policy, ticketing) -> OAuth/POST ServiceNow PDI -> resposta UI concluiu `open_ticket` no run `32409c60-d823-49e0-868b-d6bb31c6f3fa`. Todas as cinco etapas e a decisao backend foram validadas; categoria `app_access` / `software`, prioridade P3, sem fontes de procedimentos.
- Ticket local `36795b72-adc0-4530-b9f9-414ddf4d776d`, adapter `servicenow`, status `created`, numero `INC0010006`, `sys_id` `eaf03ccd47c09f1002d7d48f016d43d7`. GET autenticado e somente leitura na PDI por esse `sys_id` confirmou mesmo numero, categoria `software`, impacto `3`, urgencia `2` e descricao curta sintetica. O console apos atualizacao mostrou a conversa como Ticket, o incidente como Criado, 28 conversas e 4 tickets no total (incluindo dados preexistentes).
- Replay controlado do mesmo texto e chave de idempotencia persistidos na UI retornou HTTP 200 e o mesmo run; contagem de tickets permaneceu 4 antes/depois. Nao foi enviada outra requisicao de criacao com chave nova. O teste real comprova este caminho de sucesso, nao a acuracia do dataset inteiro nem falhas remotas.

## Mapeamento de aceite

| Requisito | Evidencia nesta rodada | Estado |
| :-- | :-- | :-- |
| FR-001 chat e historico | `test_session_and_admin_reads`, `test_response_replay_and_clarification`, `App.test.tsx`, smoke de bloqueio pelo navegador e recuperacao do historico | Passa nos casos cobertos; demais acoes so com doubles nesta rodada |
| FR-002 triagem/prioridade | `test_priority`, `test_triage_rejects_untrusted_mapping`, dataset HTTP TC001-TC012; E2E `app_access` / `software` / P3 | Contrato e um caso real passam; acuracia do dataset no provider nao avaliada |
| FR-003 fonte local | `test_sequential_crew_stages_validate_local_source`, `test_changed_knowledge_source_loses_approval`, teste UI de resposta com fonte | Passa com LLM simulado |
| FR-004 pt-BR e uma pergunta | `test_response_replay_and_clarification`, `test_low_confidence_after_question_creates_mock_ticket`, testes UI | Passa nos casos cobertos |
| FR-005 bloqueio/redacao | `test_block_and_redact`, `test_blocked_before_crew`, `test_workflow_output_is_redacted_before_ticket_and_persistence`, bloqueio pre-crew no navegador | Passa nos casos cobertos; revisao de seguranca pendente |
| FR-006 ticket | `test_ticket_success`, `test_ticket_failure_never_reposts`, E2E real `INC0010006` com GET remoto e replay idempotente | Passa no caso real coberto; falha/incerteza real nao exercitada |
| FR-007 console admin | `test_admin_conversations_order_pagination_and_detail`, testes UI, console real com `INC0010006` e eventos validados | Passa nos casos cobertos |
| FR-008 testes/observabilidade | 12 casos sinteticos, eventos em `test_sequential_crew_stages_validate_local_source`, suites backend/frontend | Parcial: nao ha evals de acuracia do provider |

## Issues, Known Gaps e Future Work

- **GAP-01 (gate de release):** falta `evals.md` com criterios EC-001 a EC-005, limiares e execucao de golden dataset contra o provider; os 12 casos atuais usam respostas injetadas no teste HTTP.
- **GAP-02 (gate de release):** falta security assessment obrigatorio pela configuracao do projeto; sem autenticacao/RBAC, a demo deve ficar restrita ao ambiente local controlado.
- **GAP-03:** falha e resultado incerto reais na PDI nao foram provocados; retry correlacionado usa chave somente na memoria da aba, e recarga durante erro incerto exige consulta humana antes de novo envio.
- **GAP-04:** o ramo HTTP 422 apos unica pergunta foi aprovado pelo operador, mas segue sem aceite formal de Product Manager; falta validar estabilidade da decisao de QA com provider real.
- **GAP-05:** o smoke inicial de bloqueio pre-crew nao exercitou `respond`, `ask_clarification` nem `open_ticket` com LLM real; o E2E adicional acima cobriu `open_ticket`, e `integration.md` registra ensaios anteriores dos demais ramos. A suite automatizada cobre os contratos com doubles.
- **GAP-06:** o ensaio real adicional validou um `open_ticket`, nao `respond` e `ask_clarification` nessa mesma rodada. A decisao do QA foi corrigida apos dois bloqueios de pedido seguro; faltam evals de regressao do provider para esse comportamento. A suite automatizada protege o contrato do prompt, mas nao determina a saida do modelo.
- **Futuro:** repetir testes opt-in de PostgreSQL, provider e PDI sob ambiente/autorizacao apropriados; medir latencia, custos e qualidade do modelo; acrescentar autenticacao e listagem de sessoes entre navegadores se a demo sair do ambiente local.

## Sources

- `project-context/1.define/prd.md` (FR-001 a FR-008); `project-context/1.define/support-cases.json`; `project-context/2.build/integration.md`; `src/backend/tests/`; `src/frontend/App.test.tsx`; `src/frontend/vite.config.ts`; `.github/agents/qa-eng.agent.md`; `aamad.config.yml`.

## Assumptions

- Suites locais com doubles sao evidencias de contrato, nao de comportamento deterministico do LLM. O incidente da PDI de 2026-10-15 e evidencia historica; `INC0010006` foi criado no ensaio adicional autorizado de 2026-10-18. Os totais do console incluem dados de ensaios anteriores e nao devem ser atribuidos apenas ao smoke atual.

## Open Questions

- Quem aprova formalmente o contrato 422 e os limiares de avaliacao EC-001 a EC-005? Quando a revisao de seguranca e os ensaios opt-in externos podem ser autorizados?

## Audit

- 2026-10-18; persona solicitada `@qa.eng`; acoes `*test-unit`, `*test-integration`, `*qa`, `*verify-flow`, `*log-defects`, `*future-work`. Ferramentas: leitura de PRD/config/testes, pytest, Vitest, Docker Compose, Alembic, curl/HTTP local, navegador integrado e `apply_patch`. Runtime resolvido: `AAMAD_TARGET_RUNTIME=crewai` pela configuracao (sem override); nenhum modelo externo foi invocado nesta rodada, portanto temperatura/max_tokens/rate efetivos nao aplicaveis. Prompt Trace omitido porque os dados do smoke sao ficticios e nao houve output de LLM ou PDI; valores de `.env` nao foram incorporados ao artefato.
- 2026-10-18, rodada adicional autorizada: browser real, CrewAI/LLM configurado por `.env`, FastAPI/PostgreSQL, OAuth/POST e GET somente leitura na PDI, replay de idempotencia e console admin. Nenhum segredo ou token foi escrito neste documento; o relato e o ticket sao ficticios. Configuracao de temperatura/max_tokens nao foi ajustada no codigo nesta rodada; limite `LLM_MAX_RPM` vem do ambiente/default do runtime. A trilha de eventos registra apenas schemas, status e decisao final redigidos, sem output bruto do provider.