# QA do MVP de suporte interno

## Atualizacao de QA - 2026-10-23

Esta secao substitui os estados e totais de 2026-10-18 abaixo; aqueles registros permanecem como historico. Os ensaios atuais usaram relatos e identidades sinteticos, em conversas novas por cenario, com provider real, PostgreSQL, proxy Vite e ServiceNow PDI. Chamadas ao provider e os quatro POSTs bem-sucedidos na PDI tem custo/efeito externo; nao foram usados segredos reais nos relatos. Os testes live novos sao opt-in (`RUN_LIVE_CHAT_CASES=1`) e nao devem ser executados rotineiramente: abrem incidentes reais na PDI.

### Unit e integracao

- Backend completo: **104 passaram, 5 ignorados** na suite padrao; frontend: **40 passaram**, typecheck e build passaram. O teste de revisao de schema em PostgreSQL e o teste E2E real de RBAC passaram separadamente. A bateria HTTP `test_api.py` apos a adicao dos cenarios opt-in teve **52 passaram, 16 ignorados** (14 casos live novos desativados e dois gates anteriores). Ruff lint passou e a faixa nova passou no format check; o format check do arquivo inteiro ainda aponta trechos anteriores aos cenarios novos. Os testes com doubles verificam contratos, nao a qualidade da decisao do LLM.
- Fluxo RBAC real: autenticacao por cookie, primeiro login com troca obrigatoria de senha, acesso negado sem autenticacao/Origin correto, permissao admin versus usuario, revogacao de sessao e auditabilidade foram exercitados. Este resultado revoga a afirmacao historica abaixo de que autenticacao/RBAC ainda nao existem; a revisao de seguranca formal continua pendente.
- API e Vite responderam, proxy `/api` alcancou o backend e banco PostgreSQL estava disponivel. O comando `aamad validate` nao pode ser executado nesta maquina (`aamad` ausente).
- Smoke autenticado no navegador em `http://127.0.0.1:5173/`: login com usuario sintetico, pergunta natural sobre falta de etiquetas na PRN-01, orientacao baseada na fonte local "Impressora de etiquetas", estado Concluido e historico com pergunta/resposta recuperado apos recarregar a pagina. A conta sintetica foi desativada ao final; nao houve pedido nem POST de ticket nesse smoke.

### Conversas reais por assunto

Cada linha representa duas conversas novas: uma solicitacao explicita de ticket na primeira mensagem e uma pergunta natural de orientacao, com uma resposta a eventual pergunta de esclarecimento. As falhas abaixo sao resultados reais, nao expectativas aprovadas. Resposta `422` significa ausencia dos dados minimos depois da clarificacao; `502` indica rejeicao da saida do agente antes de enviar o ticket.

| Assunto | Ticket solicitado de primeira | Pergunta natural |
| :-- | :-- | :-- |
| `app_access` | Ticket criado `INC0010011` apos repeticao do caso; a primeira tentativa teve `502 TICKET_FIELDS_MISMATCH` | Orientacao com fonte local |
| `applications_issues` | `502 TICKET_FIELDS_MISMATCH`, sem POST | Orientacao com fonte local |
| `critical_incident` | Ticket criado `INC0010012` | `422` sem pedido de clarificacao util |
| `network_wifi` | `502 TICKET_FIELDS_MISMATCH`, sem POST | Orientacao com fonte local |
| `password_reset` | `502 TICKET_FIELDS_MISMATCH`, sem POST | Orientacao com fonte local |
| `printer_label` | Ticket criado `INC0010013` | Orientacao com fonte local |
| `unknown` | Ticket criado `INC0010014` apos esclarecimento | `422` apos esclarecimento |

Nos pedidos de ticket que chegaram a `open_ticket`, o adapter confirmou a criacao e retornou os numeros acima. Os cenarios que pararam em `502` ou `422` nao fizeram POST remoto. Cinco das sete perguntas naturais produziram orientacao com fonte apropriada; uma pediu esclarecimento e mesmo assim falhou. A categoria `unknown` no pedido de ticket precisou de contexto adicional antes de abrir incidente. A repeticao de `app_access` mudou de erro para sucesso, portanto o comportamento do provider nao e estavel o bastante para ser declarado aprovado apenas pelo segundo resultado.

### Defeitos e gates

- **Alto - ticket nao criado em tres categorias:** `applications_issues`, `network_wifi` e `password_reset` falham com `502 AGENT_OUTPUT_INVALID` / `TICKET_FIELDS_MISMATCH` mesmo com relato sintetico de impacto e urgencia; `app_access` tambem falhou na primeira tentativa. A validacao em `runtime/crew.py` rejeita campos do payload divergentes dos campos da triagem. Persistem codigo e run, mas nao os valores divergentes; investigar o contrato entre triagem e ticketing com rastreio seguro, sem incluir PII ou segredos.
- **Medio - fluxo natural nao recupera:** `critical_incident` retornou `422` sem pergunta que permitisse corrigir a ausencia de dados; `unknown` retornou `422` mesmo apos o esclarecimento. Revisar decisao de clarificacao e dados minimos exigidos antes de considerar estas categorias prontas.
- **Gate de release:** faltam `evals.md`/limiares EC-001 a EC-005 e avaliacao formal de seguranca. Nao extrapolar os cinco sucessos de orientacao e os quatro tickets criados para acuracia geral, nem transformar falhas externas em testes unitarios deterministas. A revisao de seguranca deve incluir RBAC implementado, validacao de Origin, CSRF/sessoes e limites de acesso.
- **Futuro:** capturar com seguranca as diferencas estruturadas de triagem e ticket em ambiente de teste; adicionar regressao com saidas controladas para cada erro observado; retestar os sete assuntos com provider apos a correcao; confirmar incidentes por GET read-only na PDI quando necessario, sem novos POSTs; medir variacao de decisoes, custo e latencia. Falhas/incerteza reais da PDI e aceite do HTTP 422 seguem pendentes.

### Revisao de backend dos defeitos - 2026-10-23

As falhas live acima permanecem historicas e nao foram repetidas com provider/PDI nesta revisao. O backend agora usa impact, urgency e category validados pela triagem no payload, mesmo quando o agente de ticket sugere outros valores; o evento registra somente os nomes dos campos corrigidos, sem valores ou relato. Testes controlados cobrem as quatro categorias que apresentaram divergencia. Dados minimos ausentes no primeiro turno forcam uma pergunta contextualizada antes do ticket, mas nao impedem uma resposta fundamentada com fonte; a resposta com fonte tambem pode ser entregue apos a pergunta. A triagem recebe instrucao para reavaliar relato inicial e esclarecimento juntos. **13 testes focados passaram**, a suite backend padrao teve **112 passaram, 19 ignorados**, e Ruff lint passou nos arquivos alterados. Nao ha comprovacao de estabilidade do provider nem novo POST remoto; quando ainda faltam dados para abrir ticket apos a pergunta, o 422 permanece e seu aceite de produto/integracao segue pendente. Evals e gate de release ficam para etapa posterior.

### Reteste dirigido dos defeitos - 2026-10-23

Esta rodada e posterior a revisao de backend acima. Foram executados **10 testes controlados focados** (todos passaram), inclusive um novo teste de dois turnos na crew que forca `ask_clarification` sem fonte seguido de `respond` com `knowledge/password_reset.md`. A suite backend padrao passou com **113 testes, 20 ignorados**; Ruff lint e format check da faixa alterada passaram. Os testes opt-in abaixo usaram a versao atual da API em porta isolada, provider real e relatos ficticios; nao sao prova de estabilidade estatistica do modelo.

| Cenario live em conversa nova | Primeiro turno -> esclarecimento, quando solicitado | Desfecho |
| :-- | :-- | :-- |
| Pedido de ticket `app_access` | `ask_clarification` -> `respond` com `knowledge/app_access.md` | **Falhou expectativa de ticket:** nenhum incidente; sem 502 |
| Pedido de ticket `applications_issues` | `ask_clarification` -> `respond` com `knowledge/applications_issues.md` | **Falhou expectativa de ticket:** nenhum incidente; sem 502 |
| Pedido de ticket `network_wifi` | `open_ticket` na primeira mensagem | Passou: incidente `INC0010015` criado |
| Pedido de ticket `password_reset` | `open_ticket` na primeira mensagem | Passou: incidente `INC0010016` criado |
| Pergunta natural `critical_incident` | `ask_clarification` -> `open_ticket` | Passou sem 422: incidente `INC0010017` criado |
| Pergunta natural `unknown` | `ask_clarification` -> `respond` com `knowledge/app_access.md` | Passou sem 422; triagem mudou para `app_access` |
| Pergunta natural deliberadamente vaga | `ask_clarification` (`unknown`) -> `respond` (`app_access`) | Passou com `knowledge/app_access.md`; sem ticket |

**Defeito ainda aberto (alto):** pedidos explicitos de ticket para `app_access` e `applications_issues` produziram uma pergunta e, depois da resposta, somente orientacao. O teste live exige `open_ticket` e falhou nestes dois casos; nenhum POST foi feito para eles. A divergencia estrutural que causava `TICKET_FIELDS_MISMATCH` nao se reproduziu nos sete cenarios, mas os dois fluxos que terminaram em `respond` nao chegaram ao estagio de ticket e nao validam esse caminho para suas categorias. Os dois tickets criados com as categorias antes afetadas passaram pelo adapter e retornaram numero remoto.

**Observacao de qualidade:** o primeiro turno `app_access` pediu esclarecimento e incluiu passos operacionais, mas a resposta nao trouxe fonte no retorno desse turno (`sources=[]`); conferir se instrucoes junto da pergunta devem exigir fonte e teste especifico. O novo teste controlado garante a transicao para resposta com fonte no backend; a conversa live vaga confirma a mesma sequencia com o provider, sem prometer que ela ocorrera em toda execucao. Nao houve HTTP 422 nem 502 nesses sete retestes.

**Gates adiados por decisao do projeto:** `evals.md`, limiares EC-001 a EC-005, monitoramento de producao e avaliacao formal de seguranca/release continuam pendentes para a etapa de fechamento para deploy. Estes retestes nao substituem `*run-evals`, nao aprovam os dois defeitos residuais e nao autorizam recomendacao de deploy. Houve tres POSTs de incidentes sinteticos na PDI nesta rodada; nao foram feitos GETs remotos de reconfirmacao.

### Reteste das correcoes residuais - 2026-10-23

Esta rodada reavaliou apenas os dois pedidos de ticket que falharam no reteste anterior e a qualidade da pergunta sem fonte. **13 testes controlados focados passaram** (intencao explicita, persistencia do pedido apos esclarecimento e pergunta sem instrucoes do modelo); Ruff lint e format check da faixa alterada passaram. A API atual foi iniciada em porta isolada (8002) com provider real e ServiceNow PDI; os dois casos live opt-in passaram. Relatos e contas foram sinteticos; as contas de teste foram desativadas pelo fixture.

| Cenario live | Decisao e evidencia | Resultado |
| :-- | :-- | :-- |
| Pedido de ticket `app_access` | `ask_clarification` sem fonte, com somente a pergunta "Qual servico ou equipamento apresenta o problema, o que acontece e qual o impacto no seu trabalho?" (run `a14af691-f9cd-4aa4-997f-12e1704d01da`); apos resposta, `open_ticket` (run `7db90288-1d6d-4662-89e5-728f36d0bc37`) | Passou: HTTP 200 nos dois turnos; incidente PDI `INC0010018` criado, sessao `d1134c7c-98bd-47a4-989f-7ce644dc6b2d` |
| Pedido de ticket `applications_issues` | `open_ticket` no primeiro turno (run `eea36c80-aaa1-415c-bd1e-4515db638374`) | Passou: HTTP 200; incidente PDI `INC0010019` criado, sessao `75cec5b4-2bba-4bfc-b6fa-3df7519cb863` |

**Estado dos dois defeitos nesta rodada:** nao se reproduziu a perda do pedido explicito de ticket; ambos chegaram ao adapter e retornaram numero remoto. A pergunta observada em `app_access` nao incluiu passos operacionais nem alegou fonte inexistente (`sources=[]`). O teste live passou a exigir exatamente essa pergunta quando houver esclarecimento nas duas categorias; `applications_issues` abriu direto, portanto nao exercitou sua pergunta com provider real nesta rodada. Os incidentes nao foram reconfirmados por GET remoto. Dois sucessos nao demonstram estabilidade estatistica do provider nem cobrem outras categorias. Evals, revisao formal de seguranca e gates de release permanecem adiados ate o fechamento para deploy.

### Auditoria da rodada

Data: 2026-10-23; persona `@qa.eng`; fluxo autorizado de QA `*test-unit`, `*test-integration`, `*qa`, `*verify-flow`, `*log-defects` e `*future-work`. Runtime `crewai`; prompt e resposta foram armazenados apenas pelos mecanismos normais da aplicacao, sem copiar credenciais para este relatorio. Os testes opt-in em `src/backend/tests/test_api.py` registram resultado, run e sessao na saida da execucao e desativam os usuarios sinteticos no encerramento. A cobertura live passou a revelar defeitos nao capturados pelos doubles.

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