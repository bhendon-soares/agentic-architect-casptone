# AAMAD System Functional Specification (SFS) Template

## Context & Instructions
Gere uma System Functional Specification para uma unica feature ou user story.
Baseie todo o conteudo no PRD, SAD e na user story referenciada. Nao invente requirements.
Registre o runtime selecionado (`AAMAD_TARGET_RUNTIME`) quando a feature tocar agent ou API behavior.

## Input Requirements

**PRD Document**: [REFERENCE OR PASTE RELEVANT PRD SECTIONS]
**User Story / Feature ID**: [ex.: US-001 ou feature-id]
**Selected Runtime**: [crewai | claude-agent-sdk | cursor-sdk | N/A for pure UI]

## SFS Structure — Generate All Sections Below

### 1. Purpose and Scope

- **Feature ID**: Identificador unico correspondente ao PRD ou user-story ID
- **Purpose**: O que esta feature realiza para o usuario
- **In Scope**: Comportamentos cobertos por este SFS
- **Out of Scope**: Exclusoes explicitas adiadas para outras features ou Future Work

### 2. Traceability

- **PRD Anchors**: Secao ou requirement IDs
- **User Story**: Link para `project-context/1.define/user-stories/<id>.md`
- **SAD Anchors**: Architectural views ou decisions relevantes

### 3. Inputs

- **Input Name**: Description, type/format, source, validation rules
- Liste todo input obrigatorio e opcional

### 4. Processing Behavior

- Descricao step-by-step do processing
- Envolvimento de runtime-agent ou API quando aplicavel
- State changes e side effects

### 5. Outputs

- **Output Name**: Description, type/format, destination
- Success response shape (schema-level, nao exemplos completos de payload salvo se obrigatorio)

### 6. Validations and Constraints

- Input validation rules
- Business rules e invariants
- Timing, rate ou size constraints quando conhecidos

### 7. Error Handling and Exceptions

- Expected failure modes e error envelopes visiveis ao usuario ou API
- Retry, fallback ou halt behavior alinhado ao runtime adapter selecionado

### 8. Acceptance Criteria

- Condicoes testaveis derivadas da user story
- Mapping notes para QA (`*test-unit` / `*test-integration`)

## Sources

- Liste paths de PRD/SAD/user-story e external references usadas

## Assumptions

- Documente lacunas preenchidas por inferencia; nao as apresente como verified requirements

## Open Questions

- Itens nao resolvidos para decisao de stakeholder ou architect

## Audit

- Timestamp, persona id (`system-arch`), action (`create-sfs`), resolved `AAMAD_TARGET_RUNTIME` when applicable
