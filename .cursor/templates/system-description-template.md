# AAMAD System Description Template

## Context & Instructions
Capture uma definicao de projeto rica e estruturada antes da geracao de MRD/PRD.
Prefira este documento (ou `*elicit-requirements`) quando o use case for especializado, interno ou pouco especificado por um prompt curto.
Nao invente fatos; registre desconhecidos em Open Questions.

## Input Requirements

**Working title**: [PROJECT NAME]  
**Author / stakeholder**: [NAME]  
**Selected Runtime** (opcional nesta etapa): [crewai | claude-agent-sdk | cursor-sdk | undecided]

## System Description — Generate All Sections Below

### 1. Intent and Problem

- **Problem statement**: Qual problema este sistema resolve?
- **Primary users / operators**: Quem usa o sistema e em qual contexto?
- **Success definition**: O que significa "bom o suficiente para o MVP"?

### 2. Domain Context

- Vocabulario do dominio e entidades criticas
- Sistemas existentes, data sources ou workflows que devem ser respeitados
- Regulatory ou organizational constraints, se houver

### 3. Functional Requirements

Requirements numerados com IDs estaveis (`FR-001`, ...):

| ID | Description | Priority (Must/Should/Could) |
|----|-------------|------------------------------|
| FR-001 | … | Must |

### 4. Non-Functional Requirements

NFRs numerados (`NFR-001`, ...) cobrindo performance, security, reliability, usability e operability conforme aplicavel.

### 5. Constraints

- Technology constraints (language, cloud, offline etc.)
- Budget / timeline constraints
- Integration constraints (must / must-not integrate with ...)

### 6. Assumptions

- Assumptions explicitas nas quais o build pode se apoiar

### 7. Acceptance Criteria

Criterios numerados (`AC-001`, ...) que QA possa mapear para unit e integration tests.
Prefira formato Given/When/Then ou checklist.

### 8. Out of Scope / Future Work

- Exclusoes explicitas do MVP

## Sources

- Entrevistas com stakeholders, notas, documentos anteriores

## Assumptions

- Lacunas preenchidas por inferencia durante a elicitation

## Open Questions

- Itens a resolver antes ou durante PRD/SAD

## Audit

- Timestamp, persona id (`product-mgr`), action (`elicit-requirements`)
