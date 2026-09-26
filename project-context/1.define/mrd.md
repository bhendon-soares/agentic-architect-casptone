# Market Research Document (MRD): Multi-Agent Customer Support Crew - MVP Slim

## Executive Summary

O mercado de atendimento e IT Service Management esta em transicao de autoatendimento basico para fluxos de suporte assistidos por IA. Relatorios e materiais de Salesforce, Zendesk, McKinsey e ServiceNow indicam demanda clara por automacao, triagem e resolucao de solicitacoes rotineiras, mas tambem mostram que a adocao depende de governanca, seguranca, qualidade de resposta e integracao com sistemas de ticketing existentes.

Para este projeto, a oportunidade nao e competir com suites enterprise como ServiceNow ITSM, Zendesk AI ou Salesforce Service Cloud. A oportunidade realista para um capstone de 5 semanas e provar uma fatia vertical: chat interno de IT Help Desk em portugues brasileiro, classificacao multiagente simples, consulta a uma base local de conhecimento, resposta com fonte quando houver evidencia e criacao de incidente no ServiceNow PDI quando necessario.

A recomendacao e manter o MVP Slim: `crewai` como runtime selecionado, fluxo sequencial, busca local em markdown/FAQ/runbook, backend FastAPI, frontend React/TypeScript, PostgreSQL local via Docker e ServiceNow Table API para criacao de incidente. O produto deve evitar escopo enterprise, RAG avancado, banco vetorial obrigatorio, RBAC, multi-tenant, omnichannel, observabilidade avancada e avaliacoes sofisticadas ate que a tese central esteja demonstrada.

## Research Query Structure

**Foco principal**: Multi-Agent Customer Support Crew para IT Help Desk interno.  
**Dominio alvo**: IT Help Desk interno, suporte a colaboradores, triagem de incidentes e criacao de incidentes no ServiceNow.  
**Runtime selecionado**: `crewai`.  
**Prazo do MVP**: 5 semanas.  
**Idioma do MVP**: somente portugues brasileiro.  
**Tese do MVP**: um chat interno pode usar uma crew para classificar, consultar conhecimento local, responder com fonte ou abrir um incidente ServiceNow qualificado.

## Detailed Findings by Dimension

### 1. Market Analysis & Opportunity Assessment

**Principais achados**

- Atendimento assistido por IA e agentic AI ja aparecem como prioridade em operacoes de suporte: a Salesforce destaca que 79% dos profissionais de servico pesquisados estao investindo em agentic AI.
- O valor operacional vem de reduzir trabalho repetitivo e melhorar a primeira triagem, nao de substituir todo o ITSM. A McKinsey relata casos maduros de atendimento com IA com reducao de 40-50% em interacoes de servico e mais de 20% em cost-to-serve, mas esses resultados exigem maturidade muito acima de um MVP.
- ServiceNow, Zendesk, Salesforce e Intercom validam o espaco competitivo, mas tambem mostram que suites completas trazem escopo, custo e governanca que excedem o capstone.
- IT Help Desk interno e um nicho adequado porque possui categorias recorrentes, processos de incident management, artigos de conhecimento e necessidade clara de qualificar tickets.

**Dados e evidencias**

- Salesforce State of Service: 79% dos profissionais de servico investindo em agentic AI.
- McKinsey: maturidade alta em atendimento com IA pode reduzir interacoes de servico em 40-50% e cost-to-serve em mais de 20%; tambem aponta que 75% dos clientes usam multiplos canais, reforcando que omnichannel e real, mas deve ficar fora do MVP.
- ServiceNow posiciona ITSM como plataforma para incident, problem, change e request management, com AI specialists para solicitacoes rotineiras.
- IBM/Ponemon reforca risco de vazamento de dados e necessidade de identidade agentica, permissoes restritas e auditabilidade para agentes.

**Implicacoes**

- O MVP deve medir demonstracao funcional, nao KPIs enterprise.
- O produto deve se posicionar como uma camada fina de IA sobre o ITSM existente, nao como substituto do ITSM.
- A integracao com ServiceNow deve ser P0 porque fecha o fluxo operacional.

### 2. Technical Feasibility & Requirements Analysis

**Principais achados**

- CrewAI e adequado para prototipar roles, tasks e processos sequenciais com guardrails simples.
- FastAPI e uma escolha pragmatica para backend Python por oferecer type hints, validacao, documentacao OpenAPI e testes com HTTPX/pytest.
- ServiceNow Table API suporta POST em `/api/now/table/incident`, retornando `201` para criacao de registro e campos como `short_description`, `description`, `impact`, `urgency` e `category`.
- Busca local por texto/keyword e suficiente para o MVP porque a base de conhecimento sera pequena; banco vetorial obrigatorio aumentaria setup, debugging e superficie de seguranca.

**Dados e evidencias**

- ServiceNow Table API documenta operacoes CRUD em tabelas existentes e POST para inserir um registro em `incident`.
- FastAPI documenta validacao automatica, documentacao OpenAPI/Swagger e uso forte de Python type hints.
- CrewAI docs suportam agents, tasks, processes, guardrails, knowledge, structured outputs e padroes sequenciais/hierarquicos.
- PostgreSQL local via Docker e a opcao definida para o MVP; SQLite nao deve ser usado como banco primario do scaffold.

**Implicacoes**

- `crewai` deve usar processo sequencial, `allow_delegation=false` por padrao e encadeamento explicito de contexto entre tasks.
- O backend deve validar outputs de decisao e payload ServiceNow antes de qualquer chamada externa.
- O handoff de arquitetura deve manter knowledge local simples e adiar embeddings vetoriais.

### 3. User Experience & Workflow Analysis

**Principais achados**

- O usuario interno precisa de uma entrada simples: relatar problema, receber orientacao e pedir ticket.
- Transparencia e essencial: fonte usada, decisao final e status do ticket reduzem desconfiança em respostas geradas por IA.
- O console admin basico e importante para a demo porque mostra a tese multiagente: categoria, acao, fonte, decisao final e resultado do incidente.
- Mais de uma pergunta de esclarecimento cria atrito e aumenta o escopo conversacional; o MVP deve limitar a uma pergunta.

**Jornada do usuario no MVP**

1. Colaborador abre o chat e relata um problema de TI em pt-BR.
2. `IntakeTriage` classifica `internal_category`, `impact`, `urgency`, `confidence` e `risk_flags`.
3. `Knowledge` busca fontes locais.
4. `Response` prepara `respond`, `ask_clarification`, `open_ticket` ou `blocked`.
5. `QAPolicy` valida seguranca, suficiencia de fonte e tratamento de secrets/PII.
6. `TicketingEscalation` cria incidente ServiceNow quando a acao final for `open_ticket` e houver descricao, impacto e urgencia compreendidos.
7. Console admin exibe conversa, ticket, fontes, eventos dos agentes e metricas basicas.

**Implicacoes**

- UI P0 deve ser chat + console admin basico, sem mobile completo.
- UX deve expor titulo/caminho/trecho da fonte quando uma fonte for usada.
- O produto nao deve mostrar chain-of-thought; deve mostrar uma justificativa curta e estruturada da decisao final.

### 4. Production & Operations Requirements

**Principais achados**

- Mesmo em MVP, logs estruturados e redacao de dados sao necessarios porque Help Desk pode receber senhas, tokens e dados pessoais.
- OWASP LLM Top 10 2025 destaca prompt injection, sensitive information disclosure, excessive agency e misinformation como riscos centrais para aplicacoes com LLM.
- NIST AI RMF recomenda incorporar confiabilidade e gestao de risco ao design e avaliacao de sistemas de IA.
- O MVP deve ter observabilidade suficiente para debugging e demo, mas nao OpenTelemetry/APM/SIEM completos.

**Operacao MVP**

- Logs estruturados para conversa, evento de agente, acao, referencia de fonte e resultado de ticket.
- Mascara/redacao de secrets/credentials antes da persistencia.
- `.env`/environment variables para secrets.
- Testes unitarios para regras de decisao e payload ServiceNow.
- Teste de integracao para chat -> agentes -> ticket.

**Implicacoes**

- Seguranca basica e P0; compliance formal fica para Future.
- Acoes externas mutating devem se limitar a criacao de incidente ServiceNow.
- Console admin deve mostrar eventos dos agentes, mas nunca secrets.

### 5. Innovation & Differentiation Analysis

**Principais achados**

- A diferenciacao do MVP e um workflow multiagente explicavel, nao um chatbot generico.
- A combinacao de citacao de fonte local + estados simples de decisao + criacao de incidente ServiceNow cria uma demo mais forte que um FAQ bot isolado.
- A reducao deliberada de escopo e uma vantagem: evita que a arquitetura seja dominada por capacidades enterprise antes de provar a tese.

**Diferenciacao vs alternativas**

| Alternativa | Forca | Lacuna / oportunidade para o MVP |
| :-- | :-- | :-- |
| ServiceNow ITSM / Virtual Agent | Workflow ITSM profundo, governanca enterprise | Escopo pesado de plataforma; o MVP usa PDI apenas para criacao de incidente |
| Zendesk AI / Salesforce Service Cloud | Automacao madura de atendimento | Suites comerciais amplas, menos focadas em uma arquitetura customizada de crew para capstone |
| Chatbot RAG generico | Respostas rapidas sobre documentos | Geralmente fraco em auditoria de decisao e contrato de ticketing |
| Intake manual de Help Desk | Julgamento humano | Triagem lenta, tickets incompletos e trabalho repetitivo |

**Implicacoes**

- Manter o produto estreito e auditavel.
- Investir em visibilidade da decisao final, nao em dashboard avancado.
- Adiar monetizacao, marketplace e parcerias enterprise.

## Critical Decision Points

| Decisao | Recomendacao | Racional |
| :-- | :-- | :-- |
| Go/No-Go | Go para MVP Slim | A fatia vertical e viavel em 5 semanas |
| Runtime | `crewai` | Combina com workflow por roles/tasks e com a config AAMAD |
| Knowledge | busca local em markdown/FAQ/runbook | Suficiente para 8-12 casos de demo; corpus exato sera definido depois |
| Ticketing | ServiceNow Table API POST em `incident` | PDI existente e contrato confirmado com campos `short_description`, `description`, `impact`, `urgency` e `category` |
| Actions | `respond`, `ask_clarification`, `open_ticket`, `blocked` | Testaveis e pequenas o bastante para P0 |
| Acao adiada | mover `handoff_required` para P1 | Evita quinto estado e UX ambigua no MVP |
| Modelo de prioridade | derivar apenas de categoria, impacto e urgencia | Evita vies por atributo pessoal e alinha com campos ServiceNow |

## Risk Assessment Matrix

| Nivel | Risco | Mitigacao |
| :-- | :-- | :-- |
| Alto | Resposta alucinada sem fonte | Exigir fonte local para resposta baseada em conhecimento; caso contrario esclarecer ou abrir ticket |
| Alto | Secret/token persistido em logs | Redacao antes da persistencia; testes unitarios para bloqueio/mascara de secrets |
| Alto | Falha da API ServiceNow bloqueia demo | Adapter mock/local para dev/test e demos de contingencia |
| Medio | Regras de categoria/prioridade ficam complexas demais | Manter categorias fixas e matriz de prioridade simples |
| Medio | Workflow CrewAI fica nao deterministico | Processo sequencial, sem loops complexos, outputs estruturados |
| Medio | Base local de conhecimento fica pequena demais | Construir 8-12 casos de demo em torno de markdown/FAQ/runbooks disponiveis |
| Baixo | Falta de polimento mobile | Explicitamente fora do MVP |
| Baixo | Sem analytics avancado | Metricas basicas sao suficientes para demo |

## Actionable Recommendations

### Immediate Next Steps

- Atualizar SAD/SFS para refletir o MVP Slim e remover assumptions enterprise.
- Definir os 8-12 casos representativos de teste.
- Selecionar os arquivos locais iniciais de conhecimento.
- Preparar PostgreSQL local via Docker para o scaffold de backend.

### Short-term Priorities

- Construir chat, console admin, modelos backend e adapter ServiceNow.
- Implementar regras de decisao como codigo deterministico ao redor dos outputs dos agentes.
- Adicionar mascara de secrets/PII antes de logs/tickets.
- Validar com testes unitarios e um teste de integracao.

### Long-term Strategy

- Depois do MVP, considerar `handoff_required`, retrieval/ranking mais forte, OIDC, dataset maior e mais observabilidade.
- Adicionar vector DB, omnichannel, RBAC ou multi-tenant somente depois que a fatia vertical estiver estavel.

## Sources

- Solicitacao do usuario, 2026-09-26: escopo MVP Slim, plano de 5 semanas, categorias/actions permitidas e contrato ServiceNow.
- `AGENTS.md`: workflow AAMAD e expectativas de handoff entre personas.
- `.github/instructions/aamad-core.instructions.md`: regras AAMAD de artefatos, idioma e secoes finais Sources/Assumptions/Open Questions/Audit.
- `.cursor/templates/mrd-template.md`: estrutura esperada do MRD e dimensoes de pesquisa.
- `aamad.config.yml`: runtime selecionado `crewai`, linguagem primaria Python e preferencias de seguranca/testes/documentacao.
- Salesforce, State of Service: sinal de investimento em agentic AI, https://www.salesforce.com/resources/research-reports/state-of-service/
- McKinsey, The next frontier of customer engagement: AI-enabled customer service, 2023, https://www.mckinsey.com/capabilities/operations/our-insights/the-next-frontier-of-customer-engagement-ai-enabled-customer-service
- Pagina de produto ServiceNow ITSM, acessado em 2026-09-26, https://www.servicenow.com/products/itsm.html
- Documentacao ServiceNow Developer Table API, acessado em 2026-09-26, https://developer.servicenow.com/dev.do#!/reference/api/yokohama/rest/c_TableAPI
- Documentacao CrewAI, acessado em 2026-09-26, https://docs.crewai.com/
- Documentacao FastAPI, acessado em 2026-09-26, https://fastapi.tiangolo.com/
- OWASP Top 10 for LLM Applications 2025, acessado em 2026-09-26, https://genai.owasp.org/llm-top-10/
- NIST AI Risk Management Framework, acessado em 2026-09-26, https://www.nist.gov/itl/ai-risk-management-framework
- IBM Cost of a Data Breach Report, acessado em 2026-09-26, https://www.ibm.com/reports/data-breach
- Site oficial PostgreSQL, acessado em 2026-09-26, https://www.postgresql.org/

## Assumptions

- O MRD foi mantido objetivo para respeitar a decisao de MVP Slim, embora o template permita pesquisa mais longa.
- Dados quantitativos foram usados apenas quando retornados pelas fontes acessadas; metricas enterprise nao foram transformadas em metas do MVP.
- ServiceNow PDI ja existe, sera configurado por environment variables e usa somente os campos de payload definidos no PRD.
- O banco do MVP sera PostgreSQL local via Docker.
- Dimensionamento detalhado de mercado foi resumido porque o produto e um capstone/MVP interno, nao um lancamento comercial.

## Open Questions

- Quais 8-12 casos de teste finais entrarao no dataset? Definicao adiada para Build antes do teste de integracao.
- Quais markdown/FAQ/runbooks locais serao a primeira base de conhecimento? Definicao adiada para Build antes do teste de integracao.

## Audit

- Data/hora: 2026-09-26
- Persona id: `product-mgr`
- Acao: `create-mrd`
- Runtime resolvido: `crewai` a partir de `aamad.config.yml`
- Uso de ferramentas: leitura local de regras/templates/config AAMAD; consultas web para fontes de mercado, tecnicas e seguranca; edicoes localizadas via `apply_patch`
- Prompt Trace: omitido porque este e um artefato de planejamento para escopo MVP, nao um output de runtime de producao; as instrucoes principais do usuario estao capturadas em Sources e Assumptions.