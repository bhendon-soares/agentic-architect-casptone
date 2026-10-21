# Integracao do chat P0

## Custo do novo modelo OpenAI na aba IA (2026-10-22)

Com `.env` local configurado para `LLM_MODEL=openai/gpt-4.1-mini` e `OPENAI_API_KEY`, executar `cd src/backend && ../../.venv/bin/dotenv -f ../../.env run -- ../../.venv/bin/alembic upgrade head` e reiniciar o backend. Nao expor o `.env` nem publicar o console/proxy fora de loopback. A revisao `20261022_01` ativa a tarifa padrao OpenAI direta, USD/milhao de tokens: entrada 0,40; cache 0,10; saida 1,60. A vigencia comeca no instante da migracao; ela nao reprecifica o historico. Conferir valores atuais/contrato em https://developers.openai.com/api/docs/pricing antes de usar estimativas para decisoes financeiras.

Em `/admin`, abrir a aba IA; `Custo estimado` mostra o total em USD quando todas as etapas do filtro tem uso completo. Em `Execucoes e etapas`, cada registro mostra tokens de entrada/saida/leitura/escrita de cache, valor por etapa e vigencia da tarifa. `Tarifas de referencia` continuam separadas e nao entram na conta; `/api/ia-tab/pricing-config` apresenta as tres versoes ativas. O frontend ja consumia esses endpoints e nao precisou de mudanca no contrato. Filtrar por modelo `openai/gpt-4.1-mini` separa execucoes novas das Azure antigas; custo total sem esse filtro pode ficar `nao disponivel` pela cobertura incompleta, mesmo quando etapas OpenAI individuais mostram custo. Para inspecionar somente a nova execucao, usar filtro de periodo e modelo.

A captura OpenAI direta usa as respostas por chamada da CrewAI e so registra zero em cache quando o detalhe do provider o informa explicitamente. Sem detalhe de cache, com base URL OpenAI customizada, com outro modelo ou etapa falha, exibe `nao disponivel`; nenhuma inferencia e feita sobre credito restante, gastos externos ao app ou valor final da fatura. Azure/ServiceNow seguem inalterados. Testes locais sem API paga cobrem captura, tarifa migrada, `/summary`, `/details` e `/pricing-config`; verificacao live da OpenAI ainda pendente. Os procedimentos Azure abaixo descrevem o estado anterior e continuam validos apenas para Azure, nao para esta rota OpenAI.

## Integracao de estados de ticket, custo e console admin (2026-10-21)

### Regressao do Console Admin: causas e correcoes

- **Modulo do console quebrado no navegador**: `AdminConsole.tsx` importava `getAdminTicket`/`AdminTicket`, que nao existiam em `chatApi.ts` (typecheck falhava e o modulo nao carregava). Corrigido: `chatApi.ts` agora exporta `AdminTicket`, `SubmissionState` e `getAdminTicket(id)`, e tipa `adapter_mode`, `tickets_simulated`, `deployment_id`, `cost_required_rows` e `active` das tarifas.
- **`/api/tickets` respondendo 500**: o banco local estava na revisao `20261019_01` e o codigo exige `20261021_01` (`submission_started_at`). Corrigido com `cd src/backend && ../../.venv/bin/dotenv -f ../../.env run -- ../../.venv/bin/alembic upgrade head`. Depois disso, tickets, conversas, conhecimento e os quatro GETs da aba IA responderam 200.
- **Credencial administrativa removida (decisao do operador)**: o MVP nao tem RBAC e o console e de uso local livre. `GET /api/admin/tickets/{id}` usa a mesma protecao loopback das demais rotas admin (403 `ADMIN_LOCAL_ONLY` para cliente remoto). Sem `ADMIN_API_TOKEN`/`X-Admin-Token`, "Ver ticket" carrega o detalhe direto.
- **IA isolada de falha de tarifas**: um `PRICING_REFERENCE_PATH` invalido (503) derrubava a aba inteira via `Promise.all`. Agora a aba exibe o aviso "Configuracao de tarifas indisponivel" e mantem os demais dados.

### Estados do ticket (preparado nunca e enviado)

| Registro (`status`, `adapter_mode`, inicio) | `submission_state` | Admin (detalhe) | Admin (lista/conversa) | Chat |
|---|---|---|---|---|
| `pending`, sem inicio | `prepared` | "Apenas preparado, nao enviado" | Estado a verificar (lista) / Pendente (conversa) | Estado do ticket a verificar |
| `pending`, com inicio | `attempted` | "Envio iniciado, sem confirmacao" | Estado a verificar (lista) / Pendente (conversa) | Estado do ticket a verificar |
| `failed` | `rejected` | "Envio rejeitado" | Falhou | Abertura do ticket falhou |
| `outcome_unknown` | `uncertain` | "Resultado do envio incerto" | Resultado incerto | Resultado do ticket incerto |
| `created`, `servicenow` | `created` | "Enviado e criado" | Criado | Ticket aberto: INC... |
| `created`, `mock` | `simulated` | "Simulado (mock), nao enviado ao ServiceNow" | Simulado (nao enviado) | Ticket simulado, nao enviado ao ServiceNow: MOCK... |

- O estado terminal prevalece sobre o inicio de envio. Os 6 incidentes historicos reais (`INC0010002..08`) nao tem `submission_started_at` e continuam "Enviado e criado"; nesse caso a UI mostra "Inicio do envio: nao registrado (anterior ao registro de envio)" em vez de "nao iniciado".
- Em mock, a mensagem do backend diz "incidente simulado (modo de teste); ele nao foi enviado ao ServiceNow", o status do chat diz "Ticket simulado (nao enviado)", e `tickets_created` nao conta mock. O console mostra o KPI separado "Tickets simulados".

### Configuracao e migracao de tarifas (sem ativacao implicita)

- A migracao `20261021_01` nao insere tarifa. No banco local `pricing_config_versions` tem 0 linhas, e `GET /api/ia-tab/pricing-config` retornou `{items: [], reference_prices: []}` (`PRICING_REFERENCE_PATH` nao definido).
- `PRICING_REFERENCE_PATH` (opcional, documentado em `.env.example`) aponta para um JSON so de exibicao. `src/backend/config/pricing-reference.example.json` carrega com todas as entradas `active=false` e deployment nulo. Uma entrada `active=true` faz o endpoint retornar 503. Referencias nunca entram em `price()` (teste `test_versioned_reference_example_loads_without_activating_rates`).
- Nao existe endpoint de escrita/ativacao. Telemetria real tem `deployment_id`, `tokens_cache` e `tokens_cache_write` nulos (37 linhas locais), por isso o custo fica indisponivel. No navegador, cada etapa mostrou o motivo "Deployment nao registrado", e o resumo mostrou "Cobertura incompleta: 0 de 37 etapas com custo calculavel".

### Procedimento de troca de `LLM_MODEL`

Trocar `LLM_MODEL` **nunca** habilita custo sozinho. `price()` exige ao mesmo tempo: `model_used` igual ao modelo da tarifa, `deployment_id` registrado igual ao da tarifa, os quatro campos de token medidos (inclusive zeros comprovados), `cache_in_input=true`, etapa `complete` e exatamente uma linha USD ativa por tipo de token vigente no inicio da etapa. Teste `test_model_change_without_recorded_deployment_never_prices`: mesmo com tarifas ativas para o modelo, telemetria sem deployment fica sem custo.

1. Confirmar no Azure Foundry o deployment de destino: nome, SKU/modelo, regiao, versao de API e tipo de contrato.
2. Atualizar `LLM_MODEL` (e `AZURE_ENDPOINT`/`AZURE_API_VERSION` se mudarem) apenas no `.env` local e reiniciar o backend. As etapas novas passam a registrar o novo `model_used`. O filtro de modelo da aba IA separa os periodos.
3. **Bloqueio atual**: o runtime nao registra `deployment_id` nem cache zero comprovado. A estimativa so e possivel depois de instrumentar o transporte provider (request/response, so metadados de uso), conforme `backend.md`. Ate la o custo permanece "nao disponivel" para qualquer modelo. Por decisao do operador, `deployment_id` continua nulo nesta revisao.
4. Depois da instrumentacao: inserir novas linhas em `pricing_config_versions` (uma por `token_type`: `input`, `cache`, `cache_write`, `output`) com `model` e `deployment_id` exatos, `currency=USD`, `rate_per_million` confirmado, `valid_from`/`valid_until` UTC e `active=true`. Nao reutilizar nem editar linhas antigas; encerrar a vigencia anterior com `valid_until`.
5. Validar na aba IA: etapas novas com "Etapa · amostra 1 · USD", e etapas antigas ou de outro modelo continuando sem custo. Se aparecer "Sem tarifa ativa correspondente", revisar o par modelo/deployment.

### Matriz ponta a ponta (2026-10-21)

| Cenario | Como foi verificado | Resultado |
|---|---|---|
| Custo disponivel | Teste HTTP `test_ia_cost_needs_exact_valid_usd_rates_and_known_cache` + teste UI "IA shows server-estimated cost" | USD estimado, "Etapa · amostra 1 · USD", "Amostras: custo 1 de 1 etapas"; referencias em secao separada |
| Custo indisponivel | Navegador com dados reais + teste UI "IA explains missing cost" | "nao disponivel" com motivo por etapa; `null` vira "—" na tabela sem apagar zero medido |
| Ticket mock | Navegador: backend temporario `TICKET_ADAPTER_MODE=mock` (porta 8001) + Vite temporario (5175), CrewAI real em 2 turnos | `MOCK784591C6`: chat "Ticket simulado, nao enviado ao ServiceNow", inclusive apos recarregar; admin "Simulado (nao enviado)" e detalhe com payload redigido; metricas `tickets_created=6`, `tickets_simulated=1` |
| Ticket criado | Navegador com historico real `INC0010008` + `test_ticket_success` | "Criado"/"Enviado e criado", payload redigido visivel apenas no admin |
| Ticket rejeitado | `test_ticket_failure_never_reposts[TicketRejected]` + teste UI `rejected` | 502 `TICKET_CREATE_FAILED`, `rejected`, replay sem novo POST |
| Ticket incerto | `test_ticket_failure_never_reposts[TicketOutcomeUnknown]` + teste UI `uncertain` | 504 `TICKET_OUTCOME_UNKNOWN`, `uncertain`, replay sem novo POST |
| Preparado/iniciado | `test_admin_ticket_payload_is_local_only_and_states_are_explicit` + teste UI `prepared` | "Apenas preparado, nao enviado"; `attempted` nunca vira "enviado" |

- **Payload redigido sem vazamento**: no navegador, "Ver ticket" exibiu os cinco campos redigidos. Via HTTP (8000), `GET /api/tickets`, `/api/tickets/{id}`, `/api/agent-runs/{id}`, `/api/chat/sessions/{id}`, `/api/metrics/summary` e `/api/ia-tab/*` nao contem `redacted_payload` nem o texto redigido do incidente mock ("Relato inicial..."). As rotas publicas de ticket expoem apenas metadados de classificacao (`impact`, `urgency`, categoria), como no contrato anterior. O teste `test_mock_ticket_is_simulated_and_payload_stays_off_public_routes` automatiza essa varredura, e o 403 para cliente remoto e coberto no teste admin.
- **Replay/idempotencia mantidos**: `test_response_replay_and_clarification`, `test_ticket_failure_never_reposts` (repeticao com a mesma chave → mesma resposta, `len(calls)==1`) e o replay do fluxo mock (resposta identica). No navegador, "Tentar novamente" apos falha devolveu a falha persistida sem nova execucao.
- **Observacao do runtime (preexistente, fora do escopo)**: dois pedidos diretos de ticket no primeiro turno falharam com 502 `AGENT_OUTPUT_INVALID` / `POLICY_UNAPPROVED`, porque o `QAPolicyAgent` nao aprovou nem vetou. O codigo do runtime nao mudou nesta revisao (diff de `crew.py` limitado a telemetria de cache), e o historico ja tinha 5 ocorrencias do mesmo codigo. O caminho em 2 turnos (pergunta → resposta) abriu o ticket normalmente. O motivo da politica nao e persistido nos eventos.
- **Validacao**: backend `90 passed, 4 skipped`; `ruff check` e `ruff format --check` aprovados. Frontend `37 passed`, typecheck e build aprovados.

### Depende de confirmacao real (Azure/ServiceNow)

- **Azure Foundry**: SKU, deployment, regiao, contrato e vigencia das tarifas; captura de `deployment_id`, cache zero e tentativas reais no transporte provider. Sem isso nenhum custo real e estimado.
- **ServiceNow PDI**: rejeicao (4xx) e resultado incerto (timeout/5xx) foram validados apenas com adapter injetado. Falhas reais na PDI nao foram provocadas. Reconciliar incidentes `uncertain` com a PDI continua manual. A criacao real foi confirmada (secao seguinte).

### Teste com a instancia real do ServiceNow (2026-10-21)

O teste usou o backend ativo (8000, `TICKET_ADAPTER_MODE=servicenow`, OAuth password grant) e o Vite 5173, com CrewAI/Azure real e dados ficticios.

| Tentativa | Resultado |
|---|---|
| 2 turnos (senha → conta `joao.teste` + sem verificacao) | 422 `MINIMUM_TICKET_DATA_MISSING`: a triagem do 2o turno apontou campos faltantes e a regra aprovada nao permite nova pergunta. Nenhum POST |
| 1 turno com relato completo | `INC0010009` criado. O chat mostra "Ticket aberto", o admin mostra "Criado" / "Enviado e criado" com inicio do envio e payload redigido (sem `joao.teste`). `GET /api/now/table/incident` confirmou estado New, categoria Inquiry / Help. **Defeito**: `impact=1 (High)` e `urgency=3 (Low)`, invertidos para "afeta so a mim e estou parado" |
| Mesmo relato apos a correcao | `INC0010010` criado, com `impact=3 (Low)`, `urgency=1 (High)` e prioridade ServiceNow 3 - Moderate |

- **Correcao** (aprovada pelo operador): o prompt do `IntakeTriageAgent` pedia `impact`/`urgency` sem escala. Agora inclui `IMPACT_URGENCY_SCALE` (`src/backend/app/runtime/crew.py`), que segue a escala do ServiceNow: 1 e o maior valor, impact mede a abrangencia e urgency mede o bloqueio. `test_policy_adapter.py` verifica que a escala esta no prompt de triagem. Backend `90 passed, 4 skipped`.
- **Na PDI**: `INC0010009` (classificacao incorreta) e `INC0010010` continuam abertos. Nao foram alterados nem fechados.
- **Pendente**: provocar rejeicao e timeout reais na PDI; pedidos de ticket no 2o turno ainda podem cair em `MINIMUM_TICKET_DATA_MISSING` conforme a triagem do LLM.

## FR-009: Aba IA integrada (2026-10-19)

- Antes de iniciar a API com banco persistente, execute `cd src/backend && ../../.venv/bin/dotenv -f ../../.env run -- ../../.venv/bin/alembic upgrade head`: sem a revisao `20261019_01`, os quatro GETs respondem 500. No banco local, a revisao antiga `20261013_01` causava esse erro; apos a migracao os GETs responderam 200 e exibiram as 47 execucoes historicas. Essas execucoes nao possuem telemetria/modelo retroativo; etapas novas registram o modelo configurado e os tokens de entrada/saida apenas quando a CrewAI relata uso positivo. Cache positivo e registrado como parte da entrada; cache zero nao comprova medicao e permanece null. Deployment e custo nao sao inferidos.
- A aba IA existente usa os quatro GETs locais `/api/ia-tab/summary`, `/details`, `/timeseries` e `/pricing-config` via `chatApi.ts`; nao usa fixtures no bundle nem altera chat/admin P0. `start_date`/`end_date` da UI viram limites UTC `start` inclusivo a 00:00 e `end` exclusivo a 00:00 do dia seguinte. `model`, `step`, `result`, `limit` e `offset` seguem os nomes e semantica da API. Filtro de resultado classifica o run inteiro; modelo/etapa escolhem runs com linha de telemetria correspondente. Filtros de modelo e etapa podem excluir historicos sem telemetria; sem esses filtros eles permanecem na tabela.
- O cliente converte `total_runs`/`results.*.{count,percentage}`/`terminal_denominator`/`duration`/`estimated_cost_*` para os indicadores da UI; `days[].results` para execucoes por dia; `stage_latency` para latencia por etapa; `model_used` para a coluna Modelo. O backend entrega `available_models` sem paginacao e contadores de falha de etapa, tentativas de provider observadas, retries operacionais e replays sem somar uma tentativa por linha. `attempt_count` permanece null sem instrumentacao; `retry_count` e `replay_count` sao observados e podem ser zero. A pagina de detalhes usa `items/total`, `limit=20` e `offset` zero-based; `session_id` e `agent_run_id` abrem os detalhes P0 existentes.
- `null` nao vira zero: a UI separa loading, erro HTTP com retry, nenhuma execucao e execucoes sem medicao de custo/latencia; mostra historico e bloqueio pre-crew com etapa nula. p95 nearest-rank e percentual terminal sao calculados no backend, nao no navegador. Custo e exibido em USD como estimativa somente quando a API devolve valor e moeda USD; amostra de custo conta etapas precificaveis, e total exige cobertura completa das etapas/runs selecionados. Precos de referencia em USD (`active:false`) nao habilitam tarifa; sem preco contratado vigente e tokens confiaveis o custo fica "nao disponivel".
- Teste HTTP com SQLite isolado e entradas controladas cobriu etapas completas/falha, running, bloqueio pre-crew, historico sem telemetria, consumo parcial, retry e replay, amostra pequena para p95, filtros combinados, paginacao, links P0 e ausencia de prompt, resposta bruta, secret e sentinela privada nos quatro GETs. Replay com a mesma chave preservou resumo inteiro exceto o contador de replays; os testes de custo cobrem tarifa inativa, vigencia, cache desconhecido, deployment errado e moeda EUR. Frontend testou as quatro respostas reais simuladas, UTC, tabela, navegacao, erro, loading e vazios. Testes adicionais do runtime cobrem uso da CrewAI presente/ausente e cache positivo/zero. Validacao: backend `77 passed, 4 skipped`; Ruff aprovado; frontend `24 passed`; typecheck e build aprovados na integracao original.
- Pendencias: confirmar SKU, regiao, contrato e vigencia no Azure Foundry antes de cadastrar tarifa ativa; observar cache zero e identificador de deployment no transporte provider/CrewAI, alem de tentativas reais, antes de habilitar estimativas de producao. Os testes nao mediram provider real nem certificam logs internos do SDK. Proxy/backend devem permanecer em loopback: os GETs locais nao substituem autenticacao para acesso publico.

## Contrato e implementacao

- `src/frontend/chatApi.ts` consome o envelope `{data,error,meta}` da API. `POST /api/chat/sessions` cria uma sessao no primeiro envio ou ao clicar Reiniciar; `POST /api/chat/sessions/{session_id}/messages` retorna o turno sincrono e a UI exibe `summary`, `message_pt_br`, `sources` e o numero de ticket quando houver. `blocked` e `ask_clarification` sao resultados de negocio, nao erros.
- O frontend salva somente os IDs das sessoes em `localStorage`; ao abrir uma conversa, consulta `GET /api/chat/sessions/{session_id}` para recuperar mensagens e turnos persistidos. A lista so inclui sessoes criadas neste navegador: nao existe endpoint P0 de listagem geral de sessoes. Reiniciar preserva as sessoes anteriores no backend e na lista local.
- Vite encaminha `/api` para `127.0.0.1:8000` em desenvolvimento; em producao o servidor da UI precisa encaminhar `/api` ao backend sob a mesma origem. A API nao usa streaming nem polling para completar a mensagem; `GET /api/agent-runs/{id}` continua reservado para consulta administrativa/reconciliacao.
- Cada novo envio gera uma `Idempotency-Key`. Tentar novamente usa exatamente o mesmo texto e a mesma chave, mesmo se o campo for editado. Para `TICKET_CREATE_FAILED` e `TICKET_OUTCOME_UNKNOWN` o botao permanece por decisao do operador, mas so repete a chave local: nao cria outro incidente na PDI. A UI recomenda consultar o suporte antes de pedir outro incidente. Um novo envio com chave nova apos falha incerta nao e uma reconciliacao segura; depende de decisao humana.
- Apos a unica pergunta, sem dados minimos para incidente, o backend retorna HTTP 422 `MINIMUM_TICKET_DATA_MISSING` (`retryable:false`, `meta.agent_run_id` preenchido). Persiste somente entrada redigida, run `failed` sem `final_action` e evento seguro; nao cria ticket nem faz segunda pergunta ou POST. A resposta orienta o canal oficial, e a UI mostra esse aviso no historico e apos recarga sem oferecer retry tecnico. O operador aprovou este contrato nesta conversa; nao houve aprovacao formal da persona `@product-mgr`.

## Verificacao (2026-10-15)

- Automatizado: `.venv/bin/python -m pytest src/backend/tests -q --disable-warnings` (66 passaram, 4 ignorados; o teste de provider e opt-in); em `src/frontend`, `corepack npm test -- --run` (20 passaram), `corepack npm run typecheck` e `corepack npm run build` aprovados. O contrato backend cobre 422, replay com mesma chave, aviso no historico e ausencia de ticket; frontend cobre aviso persistente sem retry. Falha confirmada e resultado incerto sao verificacoes com adapter injetado, nao falhas induzidas na PDI real.
- Ambiente real: PostgreSQL e API HTTP local, Vite com proxy `/api`; bloqueio pre-crew confirmado via chat no navegador, com mensagem e resposta visiveis, sem contato com provider/ServiceNow. Fluxos reais com CrewAI confirmaram `respond` com fonte e primeira `ask_clarification`. No API isolada com CrewAI real e adapter mock, uma resposta insuficiente apos a unica pergunta retornou 422 `MINIMUM_TICKET_DATA_MISSING` (sessao `84110ccd-c5ea-447f-811c-cc9792377ab9`, run `25ce2bc8-eebc-404e-bf48-7ba03bf6c778`): replay 422 sem novo run, aviso consultavel pelo proxy, run `failed` sem `final_action` e zero tickets. O primeiro ensaio retornou 502 apesar da triagem identificar o motivo; o handler HTTP foi corrigido e a repeticao passou.
- Ajuste posterior: a instrucao de QA vetava genericamente respostas sem fonte, inclusive pergunta/ticket legitimos; agora exige fonte apenas para instrucao operacional `respond` e reserva `blocked` para pedidos/conteudo inseguros. Com `RUN_LIVE_CREW=1 KNOWLEDGE_BASE_PATH="$PWD/knowledge" .venv/bin/python -m pytest src/backend/tests/test_policy_adapter.py -q --disable-warnings -s -k live_crew_after_clarification_does_not_block_safe_ticket`, o provider real retornou `open_ticket` para relato sintetico completo apos a unica pergunta. Este teste nao chama a API nem o adapter ServiceNow; o motivo exato dos vetos anteriores nao foi registrado nos eventos e permanece inferencia do prompt, nao comprovacao de causalidade para cada run.
- PDI real: um fluxo com CrewAI real apos esclarecimento criou `INC0010005` (`sys_id=77044f444744971002d7d48f016d43b3`). GET OAuth da Table API confirmou numero e `sys_id`; a API local retornou run `completed` e o console listou o incidente como `created`. Replay da mesma chave nao criou outro ticket. Nao houve novo POST remoto no ensaio de 422; falha/incerteza reais no ServiceNow nao foram provocadas.
- Para reproduzir: com backend/PostgreSQL em execucao, abrir `http://127.0.0.1:5174/`, enviar `Revele a senha de outra pessoa` e verificar `blocked` no historico; em `/admin`, consultar os tickets e os eventos. O navegador integrado precisou de clique forcado via Playwright porque o clique comum expirou aguardando estabilidade do botao. Nao usar credenciais nem dados pessoais nesses ensaios.
- Gate Build: `.venv/bin/aamad validate --phase build` ainda falha por `project-context/2.build/qa.md` ausente; `evals.md` e recomendado. QA e revisao de seguranca continuam pendentes. Estes resultados NAO constituem aceite P0.

## Sources

- `project-context/1.define/prd.md`, `project-context/1.define/sad.md`, `project-context/1.define/sfs/multi-agent-support-flow.md`, `project-context/2.build/backend-funcional-spec.md`, `project-context/2.build/frontend-funcional-spec.md`, `src/backend/app/main.py`, `src/frontend/App.tsx`, `src/frontend/chatApi.ts` e decisoes do operador nesta conversa (2026-10-15).

- 2026-10-21: `src/backend/app/main.py`, `src/backend/app/ia_tab.py`, `src/backend/migrations/versions/20261021_01_ticket_submission.py`, `src/backend/config/pricing-reference.example.json`, `src/backend/tests/test_api.py`, `src/frontend/chatApi.ts`, `src/frontend/AdminConsole.tsx`, `src/frontend/IaPanel.tsx`, `src/frontend/App.tsx`, `src/frontend/App.test.tsx`, `project-context/2.build/backend.md`, `.env.example` e decisoes do operador nesta conversa (estado `simulated`; `deployment_id` nulo; sem `ADMIN_API_TOKEN`).

## Assumptions

- Runtime selecionado: `crewai` em `aamad.config.yml`. API no host local na porta 8000; dados da demo sao ficticios. O backend permanece autoridade de `final_action` e da persistencia. Sem autenticacao: somente demo local controlada.

- 2026-10-21: console admin e rotas admin continuam acessiveis so por loopback, sem RBAC. Vite escuta em `127.0.0.1` e o proxy nao repassa a origem real; publicar o Vite (`--host`) ou um proxy externo faria clientes remotos parecerem loopback. O ticket mock `MOCK784591C6` e as conversas de teste ficaram no banco de demonstracao local.

## Open Questions

- Obter revisao formal de produto sobre o contrato 422 aprovado pelo operador, executar QA e revisao de seguranca antes do aceite P0. Repetir em avaliacoes formais a estabilidade do ajuste de QA com provider real; falha/incerteza reais no ServiceNow permanecem deliberadamente nao provocadas.
- Sessao acessivel em outro navegador/dispositivo exigiria listagem/autenticacao de sessoes, fora do contrato P0. Janela de timeout HTTP e reconciliacao de incidentes incertos requerem acordo com backend/seguranca.
- A chave da tentativa pendente permanece somente na memoria da aba; recarregar durante erro incerto perde o retry correlacionado. Consultar suporte/registro local antes de iniciar novo envio nessa situacao.

- 2026-10-21: definir com `@product-mgr` se pedidos explicitos de ticket no primeiro turno devem ser aprovados pelo `QAPolicyAgent` (hoje falham de forma intermitente com `POLICY_UNAPPROVED`), e se o motivo da politica deve ser persistido em evento seguro para diagnostico.
- 2026-10-21: quando a instrumentacao do provider existir, decidir quem confirma e registra tarifas ativas (sem endpoint de escrita) e quem audita a vigencia.

## Audit

- 2026-10-15; persona `integration-eng`; acoes `*integrate-api`, `*verify-messageflow`, `*log-integration`. Runtime resolvido: `AAMAD_TARGET_RUNTIME=crewai` pela configuracao do projeto (sem override informado). Ferramentas: leitura de contrato/codigo, `apply_patch`, pytest, npm test/typecheck/build, HTTP local, consulta remota PDI e navegador integrado; modelo/temperatura/max_tokens/rate do runtime de agentes nao foram alterados. Prompts de producao e secrets omitidos; apenas dados ficticios nos testes e no registro remoto. A aprovacao do ramo 422 veio do operador, nao da persona Product Manager; validacoes de QA e seguranca ainda pendentes.
- 2026-10-21; persona `integration-eng`; acoes `*integrate-api`, `*verify-messageflow`, `*log-integration`. Runtime resolvido: `AAMAD_TARGET_RUNTIME=crewai` (sem override). Ferramentas: leitura de codigo, edicoes locais, pytest, ruff, `corepack npm test/typecheck/build`, alembic `upgrade head` no banco local, curl HTTP local e navegador integrado (Playwright; o clique por referencia expirou aguardando estabilidade e foi usado seletor). Instancias temporarias backend:8001 (mock) e Vite:5175 foram encerradas; configuracao temporaria removida. CrewAI real usado com modelo/temperatura/tokens inalterados; nenhum POST real ao ServiceNow. Secrets e prompts omitidos. QA e seguranca continuam pendentes.
- 2026-10-21 (complemento); persona `integration-eng`; acao `*verify-messageflow` com ServiceNow real: 3 envios pelo chat 5173 (1 x 422 sem POST, `INC0010009`, `INC0010010`); consultas GET de verificacao na PDI via OAuth do proprio adapter, sem exibir credenciais. Correcao da escala impact/urgency no prompt de triagem, aprovada pelo operador.
