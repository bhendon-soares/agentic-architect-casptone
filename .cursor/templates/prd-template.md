# AAMAD PRD Generation Template

## Context & Instructions
Gere um Product Requirements Document (PRD) abrangente para um multi-agent system.
Baseie decisions nos findings do Deep Research / MRD quando presentes, ou em uma system description / elicitation notes quando o MRD foi pulado.
Garanta que o PRD esteja production-ready para o escopo MVP e trate necessidades reais identificadas nos inputs.
O runtime selecionado (`AAMAD_TARGET_RUNTIME`) restringe as convencoes de implementacao da Phase 2; nao fixe um unico runtime framework como definicao do produto.

## Input Requirements

**Deep Research Report / MRD**: [PASTE OR REFERENCE `project-context/1.define/mrd.md` — ou marque N/A se pulado]  
**System Description** (opcional): [REFERENCE `project-context/1.define/system-description.md` IF PRESENT]  
**System Concept**: [INSERT YOUR MULTI-AGENT SYSTEM DESCRIPTION]  
**Selected Runtime**: [crewai | claude-agent-sdk | cursor-sdk]

## PRD Structure — Generate All Sections Below

### 1. Executive Summary

**Problem Statement** (Research-backed when MRD exists):

* Problema especifico do customer ou operator  
* Impacto quantificado e pain points  
* Escopo de target market ou user population (N/A com rationale se for ferramenta interna)

**Solution Overview** (Evidence-based):

* Abordagem de multi-agent system e unique value proposition  
* Diferenciais principais vs alternativas  
* Business ou operational outcomes esperados e success metrics

**Strategic Rationale**:

* Por que multi-agent architecture e ideal para este problema  
* Business case / ROI ou operational value  
* Market timing e competitive positioning (ou N/A para ferramentas internas)

### 2. Market Context & User Analysis

**Target Market / Users** (From Research or System Description):

* Primary user personas com caracteristicas detalhadas  
* Tamanho do market segment e growth projections (ou N/A)  
* Foco geografico e expansion opportunities (ou N/A)

**User Needs Analysis**:

* Pain points criticos e necessidades nao atendidas  
* User journey mapping e interaction patterns  
* Adoption barriers e success factors

**Competitive Landscape** (optional when MRD skipped):

* Competidores diretos e indiretos ou alternative workflows  
* Feature gaps e differentiation opportunities  
* Pricing benchmarks quando relevantes

### 3. Technical Requirements & Architecture

**Runtime & Agent Specifications** (aligned with Selected Runtime):

* Agent roles e responsibilities (com base em workflow analysis)  
* Collaboration patterns (sequential, hierarchical ou harness-specific)  
* Task / turn orchestration e delegation boundaries  
* Example (CrewAI-style quando runtime e `crewai`): role, goal, backstory, tools, memory, delegation — adapte nomes de campos para outros runtimes conforme a regra ativa do adapter

**Core Agent Definitions**:

* agent: [agent_name]  
* role: "[specific role from user journey analysis]"  
* goal: "[goal derived from user needs]"  
* tools: [list_of_required_tools]  
* runtime notes: [adapter-specific controls, ex.: max_iter, hooks, allowed_tools]

**Integration Requirements**:

* APIs e external services obrigatorios  
* Especificacoes de database e storage (MVP vs deferred)  
* Authentication e security requirements  
* Performance e scalability targets

**Infrastructure Specifications**:

* Cloud / hosting requirements para o MVP  
* Especificacoes de compute e memory  
* Network e security architecture  
* Monitoring e logging requirements

### 4. Functional Requirements

**Core Features** (Priority P0):

* [Feature 1]: Formato de user story com acceptance criteria  
* [Feature 2]: Technical specifications e constraints  
* [Feature 3]: Integration requirements e dependencies

**Enhanced Features** (Priority P1):

* Deferred salvo justificativa para MVP

**Future Features** (Priority P2):

* Lista explicita de Future Work

### 5. Non-Functional Requirements

**Performance Requirements**:

* Response time targets  
* Throughput e concurrency specifications  
* Availability e uptime requirements

**Security & Compliance**:

* Data protection e privacy requirements  
* Access control e authentication specifications  
* Regulatory compliance needs quando aplicavel

**Scalability & Reliability**:

* Scaling triggers (MVP: documente abordagem deferred)  
* Fault tolerance e recovery procedures

### 6. User Experience Design

**Interface Requirements**:

* User interaction patterns  
* Especificacoes de plataforma web / mobile  
* Accessibility e usability standards

**Agent Interaction Design**:

* Human-agent communication patterns  
* Abordagens de feedback e error handling  
* Transparency e explainability features

### 7. Success Metrics & KPIs

**Business / Operational Metrics**:

* Targets alinhados ao problem statement

**Technical Metrics**:

* System performance e reliability targets  
* Agent effectiveness e accuracy rates  
* Cost efficiency e resource utilization

**User Experience Metrics**:

* Satisfaction, task completion, time-to-value

### 8. Implementation Strategy

**Development Phases**:

* Phase 1 (Define): MRD (opcional), PRD, SAD  
* Phase 2 (Build): Setup → FE/BE → Integration → QA  
* Phase 3 (Deliver): Deploy configs e runbook

**Resource Requirements** e **Risk Mitigation**: documente realisticamente para o MVP

### 9. Launch & Go-to-Market Strategy

Opcional para ferramentas internas — se pulado, registre N/A em Assumptions.

## Quality Assurance Checklist

- [ ] Requirements rastreaveis ao MRD, system description ou Assumptions registradas  
- [ ] Technical specifications viaveis com o runtime adapter selecionado  
- [ ] Success metrics alinhadas aos objetivos declarados  
- [ ] Limites MVP vs Future Work explicitos  
- [ ] Market sections marcadas como N/A quando MRD foi intencionalmente pulado

## Sources

- MRD / system-description / stakeholder inputs usados

## Assumptions

- Lacunas preenchidas por inferencia; rationale de MRD-skip quando aplicavel

## Open Questions

- Itens nao resolvidos para decisao do architect ou stakeholder

## Audit

- Timestamp, persona id (`product-mgr`), action (`create-prd` or `create-context`), resolved `AAMAD_TARGET_RUNTIME`
