# AAMAD MVP System Architecture Document (SAD) Template

## Context & Instructions
Gere uma system architecture specification para um multi-agent MVP.
Alinhe agent e API design ao runtime selecionado via `AAMAD_TARGET_RUNTIME` (`crewai` | `claude-agent-sdk` | `cursor-sdk`) e a regra ativa do adapter.
Frontend stack usa por default uma web chat UI moderna quando o PRD nao especificar outra coisa; nao fixe uma unica vendor UI library como obrigatoria a menos que PRD/SAD decisions exijam.
Este documento e o blueprint para as personas da Build phase. Prefira views enxutas de MVP; adie NFRs nao essenciais para Future Work.

## Input Requirements

**PRD Document**: [REFERENCE `project-context/1.define/prd.md`]  
**MRD** (opcional): [REFERENCE `project-context/1.define/mrd.md` OR N/A]  
**User Stories** (quando presentes): [REFERENCE `project-context/1.define/user-stories/`]  
**MVP Scope**: Foco na core value proposition (80/20)  
**Selected Runtime**: [crewai | claude-agent-sdk | cursor-sdk]

## System Architecture Specification — Generate All Sections

### 1. MVP Architecture Philosophy & Principles

**MVP Design Principles**:

- Customer / operator feedback primeiro  
- Conjunto minimo viavel de agentes e a orquestracao mais simples que entregue core value  
- Observable by default (basic logging / health)  
- Automated deploy scaffolding desde o dia 1 quando Deliver phase estiver no escopo

**Core vs Future Features**:

- **MVP**: Core agent functionality, interface de chat (ou primary interface), apenas essential integrations  
- **Future**: Advanced features, enterprise security, horizontal scaling  
- Exclusions e deferrals explicitos

**Technical Architecture Decisions**:

- Justifique a escolha de frontend framework (ex.: Next.js App Router quando selecionado)  
- Justifique a abordagem de UI para human-agent interaction  
- Defina agent communication patterns especificos do runtime  
- Especifique streaming vs non-streaming requirements

### 2. Multi-Agent System Specification

**Agent Architecture Requirements**:

- Defina no maximo 3-4 specialized agents para o MVP  
- Especifique roles, goals e collaboration patterns a partir do PRD  
- Memory / session requirements (default: none ou short-lived para reproducibility)  
- Necessidades de Tool / MCP integration por agent (least privilege)

**Task / Turn Orchestration**:

- Dependencies e execution flow  
- Expected outputs e data formats  
- Context passing entre agents  
- Error handling, retries, cancellation / timeout behavior  
- Performance budgets (max execution time, token / turn limits)

**Runtime-Conditional Configuration** (fill the subsection matching Selected Runtime):

- **crewai**: crew composition, process type, YAML agent/task config, `max_iter`, task context chaining  
- **claude-agent-sdk**: coordinator + `AgentDefinition` specialists, hooks, `allowed_tools`, session policy  
- **cursor-sdk**: TypeScript/Node runtime roles, tool contracts, streaming/event envelopes, budget controls

### 3. Frontend Architecture Specification

**Technology Stack** (from PRD or justified defaults):

- Framework, UI library, styling, type safety, state management

**Application Structure**:

- Organizacao de route / page  
- API client boundaries (sem backend wiring no FE epic)  
- Component architecture e responsive / accessibility requirements

**Interface Requirements**:

- Superficie primaria de chat ou interaction  
- Loading / error states  
- Placeholders para Future Work features

### 4. Backend Architecture Specification

**API Architecture**:

- Chat (ou primary) endpoint contract: request schema, response schema, streaming/event envelope  
- Validation, rate limiting, error envelope shape  
- Alinhamento com o runtime adapter selecionado

**Data Architecture** (MVP default: none unless PRD requires):

- Adie explicitamente persistence quando estiver fora do MVP; se incluida, justifique minimal store

**Runtime Integration Layer**:

- Como a camada HTTP/API invoca o runtime selecionado  
- Agent configuration management  
- Logging / Prompt Trace hooks conforme adapter Quality Gates

**Authentication & Secrets**:

- Apenas env-var names (de `.env.example`); nenhum secret value em artifacts

### 5. DevOps & Deployment Architecture

**CI/CD** (minimal MVP): lint, test, build  
**Hosting**: menor target adequado ao MVP; health-check endpoint  
**IaC / multi-region / advanced monitoring**: Future Work salvo exigencia do PRD  
**Observability**: baseline logs e health; advanced APM deferred salvo se estiver no escopo

### 6. Data Flow & Integration Architecture

- Request/response path da UI pela API ate runtime agents  
- External tool/API integrations exigidas apenas para o MVP  
- Error propagation e feedback visivel ao usuario

### 7. Performance & Scalability Specifications

- Response-time e concurrency targets para o MVP  
- Scaling path deferred com rationale  
- Token / cost controls na runtime layer

### 8. Security & Compliance Architecture

- AuthN/AuthZ para o MVP  
- Baselines de encryption e input validation  
- Compliance deferred com Open Questions explicitas quando desconhecida

### 9. Testing & Quality Assurance Specifications

- Expectativas de unit, integration e smoke/acceptance para o MVP  
- Checks especificos do runtime (task outputs, hook traces, schema validation)  
- Security assessment recomendado antes do Deliver

**Evaluation Criteria** (when `*define-eval-criteria` has been run):

Criterios de aprovacao mensuraveis em accuracy, latency, safety, security e cost, derivados dos PRD KPIs, do SLA e da consequencia de uma resposta errada — nao do score acidental de um prototipo inicial. Pergunte ao operador por thresholds que nao possam ser derivados dos inputs; nao os invente.

| ID | Dimension | Metric | Threshold | Grading Method | Source |
|----|-----------|--------|-----------|-----------------|--------|
| EC-001 | Accuracy | … | … | Code-based / LLM judge / Human | PRD §x / Operator answer |

`@qa.eng` implementa esta tabela via `*run-evals`, produzindo golden dataset, graders e `evals.md`. Quando esta tabela estiver ausente (projetos anteriores a esta capacidade), `*run-evals` roda seu proprio operator gap check em vez de bloquear.

### 10. MVP Launch & Feedback Strategy

- Beta / pilot criteria quando aplicavel  
- Success metrics ligadas aos PRD KPIs  
- Iteration priorities apos o primeiro deploy

## Implementation Guidance for AI Development Agents

1. Foundation setup conforme epic `setup.md`  
2. Frontend MVP UI sem backend wiring  
3. Backend runtime scaffolding conforme adapter rule  
4. Integration epic conecta FE ↔ BE  
5. QA valida unit, integration e smoke paths  
6. Deliver empacota apenas deploy/CI/runbook

## Architecture Validation Checklist

- [ ] PRD requirements mapeados para architectural components  
- [ ] Agents desenhados para o domain e runtime selecionado  
- [ ] Frontend e backend contracts concordam em schemas / streaming  
- [ ] Secrets apenas via env vars  
- [ ] Limites MVP vs Future Work explicitos  
- [ ] `AAMAD_TARGET_RUNTIME` resolvido registrado em Audit

## Sources

- PRD, MRD (se houver), user stories, adapter rule path

## Assumptions

- Stack defaults escolhidos quando o PRD foi silencioso; liste explicitamente

## Open Questions

- Itens nao resolvidos de NFR, hosting ou compliance

## Audit

- Timestamp, persona id (`system-arch`), action (`create-sad` or `create-sad --mvp`), resolved `AAMAD_TARGET_RUNTIME`
