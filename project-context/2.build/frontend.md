# Frontend Build: UI integrada e historico da primeira etapa

## Ajustes de acesso e usuarios (RBAC)

- Login reutiliza a marca do chat, com titulo "Iniciar sessao" e ajuda secundaria mais discreta. Cabecalho compartilhado organiza navegacao, tema, nome formatado e saida ao lado do nome; o aviso de acesso restrito e um toast temporario fora do fluxo do chat.
- Console de usuarios usa icones Lucide e dialogos nativos estilizados para renomear, mudar perfil/status, redefinir senha e desbloquear login. O aviso de nova conversa apos ticket incerto tambem usa dialogo no lugar de `window.confirm`.
- Contrato atual: `POST /api/admin/users` recebe email no cadastro; `PATCH /api/admin/users/{user_id}` aceita apenas `display_name`, `role` e `is_active`. Alterar email exige mudanca explicita do backend e nao foi oferecido na UI.
- Verificacao: 38 testes de UI e `npm run build` aprovados; login inspecionado em desktop e 390 px sem overflow horizontal. Console autenticado conferido parcialmente com resposta simulada; fluxos autenticados ponta a ponta nao foram verificados nesta revisao.

## Redesign da UI integrada (A) e limites (B)

- Entregue: tema Sistema/Claro/Escuro, componentes compartilhados, chat com estados de resultado distintos e fonte sem caminho/trecho, cinco abas do console, timeline com payload redigido recolhido, IA com dados apenas do servidor, custo `null` distinto de zero e p95/maximo mascarados abaixo de 20 amostras. Nenhum endpoint novo ou alteracao de regras de ticket foi introduzido.
- Propostas B, sem implementacao de backend: reconciliacao autoritativa de tickets apos recarga/dispositivos, denominadores e cobertura de telemetria global, semantica tipada de eventos/rotulos de categorias. Contrato proposto e condicoes de aceite constam em `frontend-funcional-spec.md`; dependem de backend/integracao.
- Verificacao: 27 testes de UI aprovados (`corepack npm test -- --run`); `corepack npm run typecheck` e `corepack npm run build` aprovados. Nao existe script de lint no pacote. `.venv/bin/aamad validate --phase build` passou com aviso: `evals.md` recomendado antes de Deliver.
- Navegador local: chat e console sem overflow da pagina em 320, 390 e 1280 px; IA tem scroll proprio na tabela. Alternancia claro/escuro confirmada. Contrastes texto/superficie 18,27:1 claro e 14,64:1 escuro; secundario 6,71:1 e 6,94:1; botao primario 6,29:1 e 9,52:1. Verificacao visual feita em estados carregados existentes; nao comprova todas as combinacoes de dados ou integracao ServiceNow real.

## Historico: primeira etapa e contrato inicial de IA

## FR-009: aba IA (P1) - contrato assumido para @integration.eng

Atualizacao: a API entrega `pricing-config.data.reference_prices` com os quatro precos de referencia informados em USD por milhao de tokens (entrada 2,00; cache 0,20; escrita de cache 2,50; saida 10,00), `active:false`, sem deployment ou vigencia comprovados. A UI atual mostra estas referencias recolhidas, sem exemplos ou calculos de custo no cliente. `items` continua restrito a tarifas ativas; nenhuma referencia habilita custo por execucao sem tarifa aplicavel e consumo confiavel. A proposta inicial abaixo permanece como historico.

- Aba IA integrada ao console admin existente; Operacao, detalhes de conversa/execucao e chat permanecem nas rotas P0. Nao ha dados de demonstracao ou precos de fallback em producao: sem endpoints P1 disponiveis, a aba mostra erro e permite nova tentativa. Fixtures existem apenas nos testes de UI.
- Todas as quatro rotas `GET /api/ia-tab/{summary,details,timeseries,pricing-config}` usam `{ "data": T, "error": null, "meta": { "request_id": "...", "agent_run_id": "..." } }` no sucesso e `data: null` + erro `{ code, message, retryable }` na falha. `meta` pode conter outros campos; o cliente nao usa metadados para calcular metricas. Nomes de campos abaixo sao **proposta frontend** a confirmar com backend/integration, nao API P1 ja entregue.
- Filtros opcionais em `summary`, `details`, `timeseries`: `start_date` e `end_date` como datas inclusivas `YYYY-MM-DD` (UTC a confirmar); `model` como ID exato do modelo efetivamente usado; `step` em `triage|knowledge|response|policy|ticketing`; `result` em `respond|open_ticket|blocked|ask_clarification|failed|running`. String vazia e omitida. `details` adiciona `limit=20&offset=0` (offset zero-based). Backend aplica os mesmos filtros aos tres endpoints; a contagem de execucoes e distinta por `agent_run_id`, embora a tabela seja por etapa. Em filtro por etapa, definir se o resultado usa a execucao inteira ou apenas etapas filtradas.
- `summary.data`: `{ executions: number|null, available_models: string[], results: { respond, open_ticket, blocked, ask_clarification, failed, running }, terminal_sample_size: number, result_percentages: { respond, open_ticket, blocked }, estimated_cost: { value: number|null, currency: "USD"|null, sample_size: number }, stage_mean_ms: { value: number|null, sample_size: number }, stage_p95_ms: { value: number|null, sample_size: number }, step_failures: number|null, observed_model_attempts: number|null, operational_retries: number|null, replays: number|null }`. Cada entrada em `results` e `result_percentages` e `number|null`. `available_models` traz todas as opcoes relevantes, nao apenas as 20 etapas paginadas nem apenas modelos com tarifa. Percentuais e p95 (nearest-rank) sao calculados no servidor apenas com amostras confiaveis; denominador de percentuais e `terminal_sample_size` (somente respond/open_ticket/blocked). `estimated_cost` e uma estimativa USD completa ou null; `sample_size` descreve execucoes com preco aplicavel e consumo confiavel. Latencia em ms descreve etapas concluidas, nao execucoes inteiras; cada medida tem amostra propria. Contadores ausentes ficam null, inclusive tentativa real nao observada. Replay nao aumenta execucoes, custo, falhas nem amostras.
- `details.data`: `{ items: IaDetail[], total: number }`. Cada linha tem `agent_run_id`, `session_id: string|null` (para link de conversa), `step_name`, `model: string|null`, `start_time/end_time: ISO-8601|null`, `duration_ms: number|null`, `tokens_input/output/cache: number|null`, `estimated_cost_value: number|null`, `estimated_cost_currency: "USD"|null`, `estimated_cost_validity_start/end: ISO-8601|null`, `attempt_count/retry_count/replay_count: number|null`, `state: string`. Custo so existe quando tarifa vigente, moeda compativel e consumo completo permitem estimativa; UI nao precifica tokens e nao infere tentativas de uma crew concluida. `session_id` vincula a rota P0 de detalhe; `agent_run_id` vincula eventos P0. Resposta nao inclui prompts, respostas brutas, payload de eventos ou PII.
- `timeseries.data`: `{ executions: [{ date: "YYYY-MM-DD", count: number|null }], results: [{ result: IaResult, count: number|null }], stages: [{ step_name, mean_ms: number|null, p95_ms: number|null, max_ms: number|null, sample_size: number }] }`. Evolucao e distribuicao sao visualizadas como barras acessiveis; a distribuicao mostrada usa `summary.results` para garantir denominador comum. `pricing-config.data`: `{ items: [{ model, deployment_id, currency, token_type, rate_per_million, valid_from, valid_until }] }`; `valid_until` pode ser null. Precos nao sao usados pelo frontend para fazer calculos.
- `null` sempre aparece como "nao disponivel" (zero medido continua zero). Estado vazio requer `executions === 0`; contagem desconhecida nao e exibida como zero. Execucoes existentes sem amostras de custo e latencia mostram aviso de telemetria ausente. Erro HTTP, loading e ausencia de execucoes sao estados separados. A tabela continua visivel mesmo que valores de telemetria da linha sejam parciais.
- Pendencias para integracao: confirmar nomes/estruturas das quatro respostas e filtros, semantica de datas/timezone e de `result` sob filtro de etapa; garantir `available_models` nao paginado, `session_id` seguro no detalhe, amostras/denominadores e cobertura de custo total, p95 nearest-rank e `null` quando medicao/preco nao confiavel; determinar vigencia e moeda contratadas no Azure Foundry antes de liberar estimativas. Validar testes de contrato reais e estados 404/501 enquanto os endpoints P1 ainda nao existem. Nenhuma mudanca de decisao P0 foi introduzida.

## Validacao P0 da UI integrada

- FR-001: chat usa as rotas integradas de sessao, mensagem e historico; testes com respostas HTTP simuladas cobrem `respond`, `ask_clarification`, `open_ticket` e `blocked`, fonte, numero e estado do incidente, carregamento, falha e recuperacao do historico. A decisao `final_action` vem da API, nao do frontend.
- FR-004: console consome metricas, conversas paginadas, tickets e fontes; exibe as quatro metricas, historico, decisoes e eventos de execucao. Testes cobrem paginacao, execucao com falha sem turno concluido e erro parcial sem esconder dados disponiveis.
- FR-007: cada novo envio recebe chave de idempotencia; retry na mesma aba conserva chave e corpo, sem duplicar a mensagem. Em tentativa de ticket falha/incerta, a conversa bloqueia novos envios, mesmo com rascunho editado. A aba conserva somente um marcador de verificacao; apos recarga nao oferece retry sem chave e orienta consultar o suporte. Reiniciar uma conversa marcada exige confirmacao explicita. Erros HTTP explicitamente nao relacionados a ticket liberam a edicao e novo envio; falhas sem resultado conhecido conservam o bloqueio.
- Validacao: `corepack npm test -- --run` (19 testes aprovados), `corepack npm run typecheck` e `corepack npm run build` aprovados em `src/frontend`. No navegador local, chat e console foram inspecionados em 390 px e 1280 px, sem overflow horizontal; foco por teclado visivel no console. A consulta GET do console apresentou metricas e registros; nenhum POST real de ticket foi gerado nesta verificacao.
- Limites: o marcador depende de `sessionStorage` na mesma aba; nao e um mecanismo de reconciliacao entre dispositivos/abas nem recupera a chave de retry apos recarga. O backend e a operacao devem reconciliar `TICKET_CREATE_FAILED`/`TICKET_OUTCOME_UNKNOWN` antes de uma nova solicitacao. Testes de contrato de rede usam mocks; esta validacao nao comprova ServiceNow real ou persistencia backend ponta a ponta. `.venv/bin/aamad validate --phase build` falhou por ausencia de `project-context/2.build/qa.md`; `evals.md` foi recomendado antes de Deliver.

## Revisao visual da UI integrada

- Chat e Console Admin adotam uma identidade azul-grafite compartilhada em `src/frontend/style.css`, com cabecalho compacto, espacamento mais denso, metadados discretos e foco visivel. O chat destaca o formulario e a acao Executar; o console organiza metricas, listas e detalhes sem cards decorativos.
- Contratos, estados, handlers, integracoes e backend permanecem inalterados. A diretriz e os criterios de aceite visuais foram registrados em `project-context/2.build/frontend-funcional-spec.md`; as notas da primeira etapa mockada abaixo permanecem como historico.

## Decisoes

- A primeira etapa e uma unica rota React/TypeScript/Vite em pt-BR, tema escuro e visual minimo, com demonstracao local de `respond` para `password_reset`.
- A resposta deve seguir o procedimento de `knowledge/password_reset.md`: confirmar qual conta apresenta o problema sem pedir senha atual, orientar fluxo oficial e verificacao de identidade; se verificacao indisponivel, encaminhar a suporte para validacao manual; nao enviar senha temporaria.
- `startRun` e `getRunStatus` em `src/frontend/mockRuns.ts` sao servicos mockados locais com atrasos fixos de 350 ms e 1100 ms. A FSM local e `idle -> running -> done`; erro tecnico retorna a `idle` com entrada preservada e retry identico. As quatro `final_action` sao decisoes de negocio e nao estados de execucao; somente `respond` e demonstrado.
- Sem backend, CrewAI, banco, ServiceNow real ou alteracoes no PRD/SAD nesta etapa. Console admin e persistencia sao pendencias do P0 completo, nao funcionalidades entregues.
- A integracao futura substitui os mocks pelas rotas de sessao, mensagem e consulta de execucao previstas no SAD, mantendo o backend como autoridade de `final_action`.

## Spec Sync

| Item | Status | Nota |
| :-- | :-- | :-- |
| Especificacao funcional e contratos | Atualizado | Ver `project-context/2.build/frontend-funcional-spec.md`; contrato local implementado, payload HTTP ainda a alinhar. |
| Scaffold React/TypeScript/Vite e setup | Resolvido | `project-context/2.build/setup.md` entregue; typecheck e build do scaffold aprovados. |
| Implementacao e testes do chat | Validado | React/FSM/mocks e um teste do fluxo feliz com fonte. Falha tecnica tratada, sem injecao de falhas. |
| README e comandos | Atualizado | Passos locais e handoff de integracao registrados na raiz. |
| Screenshots | Parcial | Entrada/execucao/resultado visiveis na sessao; arquivos isolados pelo navegador; roteiro na especificacao. |
| Console admin e persistencia | Pendente | P0 completo; nao realizados por esta fatia mockada. |
| Gate AAMAD Build | Pendente | Faltam artifacts de backend, integration e qa de outras personas. |

## Validacao e handoff

- `corepack npm test`: um teste aprovado, exercitando entrada, mocks, `running`, `done`, resposta e fonte. `corepack npm run typecheck` e `corepack npm run build` sao os gates de codigo.
- Navegador: status em andamento e controles desabilitados observados; duas mensagens e fonte visivel apos conclusao; largura movel verificada sem overflow horizontal.
- `@integration.eng` substituira o servico local pelos endpoints do SAD, sem transferir ao frontend a autoridade sobre `final_action`. A restricao do runtime `crewai` nao aparece nesta UI mockada; sem streaming prometido.
- Console admin, persistencia e validacao Build completa continuam pendentes das demais personas.

## Sources

- `AGENTS.md`; `aamad.config.yml`; `.github/instructions/aamad-core.instructions.md`; `.github/instructions/development-workflow.instructions.md`; `.github/agents/frontend-eng.agent.md`; `.github/agents/project-mgr.agent.md`.
- `project-context/1.define/prd.md`; `project-context/1.define/sad.md`; `project-context/1.define/sfs/multi-agent-support-flow.md`; `knowledge/password_reset.md`; `project-context/2.build/frontend-funcional-spec.md`.

## Assumptions

- Mocks e textos usarao somente dados ficticios de demonstracao. `crewai` e runtime do backend futuro, nao do frontend.

## Open Questions

- Quais payloads concretos da API serao acordados por backend e integracao para substituir os mocks?

## Audit

- Data: 2026-10-09. Persona: `frontend-eng`. Acao: `document-frontend` e `halt-and-report` por ausencia de pre-requisito.
- Ferramentas: leitura de regras e artefatos, inspecao da arvore Build e edicao via `apply_patch`. Modelo/temperatura/max_tokens de runtime: nao aplicaveis, pois nenhum agente do produto foi executado. Prompt Trace omitido: nao houve output de alto risco ou de producao.
- Revisao em 2026-10-09: handoff recebido; acao `develop-fe`, teste automatizado, build e verificacao visual. Teste e ferramentas de navegador registrados acima; sem execucao de agentes do produto.
- Revisao do gate: `corepack npm test`, `corepack npm run typecheck`, `corepack npm run build` aprovados; `.venv/bin/aamad validate --phase build` falhou por `backend.md`, `integration.md`, `qa.md` ausentes; `evals.md` recomendado antes de Deliver. Capturas dos tres estados ficaram visiveis na sessao, nao no repositorio.