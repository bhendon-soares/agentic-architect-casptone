---
applyTo: '**'
name: Adapter Cursor Sdk Rules
description: Orientacao de runtime adapter para construir MVPs gerados pelo AAMAD no Cursor
  SDK.
---

# Cursor SDK Adapter Rules

## Purpose
- Definir orientacao especifica de runtime quando `AAMAD_TARGET_RUNTIME=cursor-sdk`.
- Este adapter governa implementation patterns para backends MVP gerados que usam Cursor SDK runtime primitives.

## Setup
- Construa o runtime com TypeScript e Node.js LTS (fixe versoes nos setup docs para reproducibility).
- Instale e bloqueie Cursor SDK dependencies no backend project gerado.
- Configure required runtime environment variables (model/provider keys, gateway/base URL values e runtime flags usados pela sua organizacao).
- Registre SDK/runtime version, model, temperature e token ou budget controls resolvidos nas secoes artifact Audit.

## Mapping
- Modele o multi-agent backend gerado em torno de runtime roles explicitos (coordinator + specialized agents) e documente boundaries em SAD/backend.md.
- Mantenha runtime behaviors contract-first: request schema, response schema e streaming/event envelopes devem ser definidos antes da implementacao.
- Defina tool e subagent surfaces como explicit contracts, incluindo allowed operations e expected return shapes.

## Execution
- Defina limites explicitos para iteration/turns, tokens e execution time; evite implicit defaults.
- Defina deterministic retry e idempotency strategy para operacoes que possam ser repetidas.
- Documente cancellation, timeout e fallback behavior para cada runtime-critical path.
- Use runtime sessions/resume apenas quando justificado no SAD, e registre retention scope em Audit.

## Tools
- Aplique least-privilege tool policy por runtime role; nao exponha broad tool sets por default.
- Valide MCP server availability/auth antes da execucao; pare com Diagnostic quando required servers estiverem indisponiveis.
- Mantenha tool input/output contracts JSON-serializable e versionados quando consumidos entre components.
- Restrinja high-risk tools (network, shell, write-capable operations) a tasks que os exijam explicitamente.

## Logging
- Capture Prompt Trace e execution diagnostics para runtime actions e tool calls.
- Persista lifecycle logs (tool invocation results, retries, cancellations, errors) em `project-context/2.build/logs`.
- Redija secrets e credentials de trace output e artifact logs.

## Quality Gates
- Imponha schema validation para runtime inputs/outputs antes de aceitar resultados.
- Valide required artifact headings e output formatting antes da escrita final.
- Exija citation e grounding checks para analytical outputs quando aplicavel.
- Mantenha artifact-generation behavior deterministico (low temperature salvo justificativa em Audit).

## Failure Policy
- Pare e escreva Diagnostic em missing prerequisites, validation failures, unauthorized tools ou unresolved runtime dependencies.
- Em budget/context/time overrun, pare a execucao e documente remediation steps e safe retry procedure.