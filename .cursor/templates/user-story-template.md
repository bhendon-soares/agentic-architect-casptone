# AAMAD User Story Template

## Context & Instructions
Gere uma user story por arquivo em `project-context/1.define/user-stories/`.
Derive stories do PRD e da system description opcional. Nao invente product scope.

## Input Requirements

**PRD Document**: [REFERENCE RELEVANT PRD SECTIONS]
**System Description** (opcional): [REFERENCE IF PRESENT]
**Story ID**: [ex.: US-001]

## User Story Structure — Generate All Sections Below

### 1. Story Identity

- **ID**: US-NNN (stable identifier)
- **Title**: Nome curto e descritivo
- **Priority**: Must / Should / Could (foco MVP: apenas Must, salvo justificativa)
- **Persona**: Primary user persona do PRD

### 2. Narrative

Como [persona], quero [capability], para que [outcome].

### 3. Acceptance Criteria

Criterios numerados e testaveis (Given / When / Then ou checklist em bullets).
Cada criterio deve ser utilizavel por QA para derivar unit ou integration tests.

### 4. Scope Notes

- **In Scope for MVP**: Comportamentos incluidos agora
- **Deferred**: Future Work explicito

### 5. Traceability

- **PRD Anchors**: Secoes ou requirement IDs
- **Related SFS**: `project-context/1.define/sfs/<feature-id>.md` quando criado

## Sources

- Paths de PRD / system-description usados

## Assumptions

- Lacunas preenchidas por inferencia

## Open Questions

- Itens que precisam de esclarecimento antes de architecture ou build

## Audit

- Timestamp, persona id (`product-mgr`), action (`create-stories`)
