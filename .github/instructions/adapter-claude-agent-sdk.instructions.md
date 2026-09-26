---
applyTo: '**'
name: Adapter Claude Agent Sdk Rules
description: Orientacao de runtime adapter para construir MVPs gerados pelo AAMAD no Claude
  Agent SDK.
---

# Claude Agent SDK Adapter Rules

## Purpose
- Definir orientacao especifica de runtime quando `AAMAD_TARGET_RUNTIME=claude-agent-sdk`.
- Este adapter governa implementation patterns para backends MVP gerados que usam o Claude Agent SDK.

## Setup
- Instale SDK dependencies para o language runtime selecionado:
    - Python: `pip install claude-agent-sdk`
    - TypeScript: install the Claude Agent SDK package used by your org standard.
- Configure required runtime environment variables (`ANTHROPIC_API_KEY` e quaisquer settings org-specific de gateway/base URL).
- Registre SDK version, resolved model, temperature e token controls em artifact Audit.

## Mapping
- Represente specialized runtime agents como entradas `AgentDefinition` em `ClaudeAgentOptions.agents`.
- Use o main runtime agent como coordinator e invoque specialized agents via a tool `Agent`.
- Para cloud-managed multi-agent orchestration, use callable-agent patterns quando apropriado e documente delegation boundaries em SAD/backend.md.

## Execution
- Defina turn e token budgets explicitos por task; nao dependa de defaults implicitos.
- Use `ClaudeSDKClient` para bidirectional interactive flows e streaming workflows.
- Defina retry e idempotency behavior para runtime actions que possam ser repetidas.
- Use session resume/fork apenas quando obrigatorio, e documente rationale e retention scope em Audit.

## Tools
- Use por default listas `allowed_tools` de least-privilege por runtime task.
- Use built-in tools (`Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`) apenas quando exigido pelo scope.
- Prefira in-process MCP servers para custom internal tools; use external MCP servers quando process boundaries forem necessarios.
- Valide MCP server availability e auth antes da execucao; falhe rapido com Diagnostic em missing dependencies.

## Logging
- Capture Prompt Trace antes da execucao e acrescente em artifacts ou trace logs conforme persona output rules.
- Use hooks (`PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`) para registrar lifecycle events e impor guardrails.
- Persista runtime trace logs em `project-context/2.build/logs` e redija valores sensiveis.

## Quality Gates
- Imponha structured output contracts usando output schema validation ou post-write validators.
- Exija citation e numeric grounding checks para analytical outputs quando aplicavel.
- Mantenha artifact-generation tasks deterministicas (low temperature salvo justificativa em Audit).
- Valide required headings e machine-ingested formatting antes da escrita final.

## Failure Policy
- Pare com Diagnostic quando schema validation, guardrails, tool authorization ou runtime prerequisites falharem.
- Em budget/context overrun, pare a execucao e escreva remediation notes no artifact.