---
applyTo: '**'
name: Adapter Registry Rules
description: Registry e selection rules para escolher o runtime adapter usado por
  aplicacoes multi-agent geradas pelo AAMAD.
---

# Adapter Registry Rules

## Purpose
- Selecionar o runtime target para a aplicacao multi-agent gerada sem mudar o core crew workflow do AAMAD.

## Selection Mechanism
- Use a environment variable `AAMAD_TARGET_RUNTIME` com valores:
    - `crewai` (default)
    - `claude-agent-sdk`
    - `cursor-sdk`
- Runtime adapter rules sao carregadas de `.cursor/rules/adapter-<name>.mdc`; o runtime selecionado deve ter um adapter file correspondente.
- Se ausente ou desconhecido, use `crewai` por default e registre o valor resolvido mais warning no artifact Audit.

## Adapter Contract
- Cada adapter deve definir:
  - Setup requirements (dependencies, env vars e runtime prerequisites).
  - Agent declaration pattern para a aplicacao gerada (como runtime agents/subagents sao representados).
  - Tool e MCP binding policy, incluindo validation e least-privilege guidance.
  - Execution controls (iteration/time/budget caps, retries e cancellation behavior).
  - Logging hooks para secoes Prompt Trace, Diagnostic e Audit.
  - Memory/session handling e reproducibility constraints.
  - Output contract conventions (structured I/O, schema checks, citation/grounding rules quando aplicavel).

## Runtime Hooks
- Preflight: verifique presenca de PRD/SAD/SFS por persona, valide runtime/tool config, resolva runtime value, entao prossiga ou Halt and Report.
- Postflight: valide artifact contra template schema, acrescente Prompt Trace + Audit, garanta escrita deterministica.

## Extensibility
- Novos adapters devem manter a mesma section taxonomy: Purpose, Setup, Mapping, Execution, Tools, Logging, Quality Gates, Failure Policy.
- Adapters podem adicionar capabilities (ex.: graph supervision), mas nao podem mudar AAMAD Core contracts.

## Selection Criteria
- `crewai`: melhor quando voce quer declarative task orchestration com YAML-first config e task graph controls explicitos.
- `claude-agent-sdk`: melhor quando voce quer um agentic runtime harness com hooks, custom tools/MCP integration e session-level control.
- `cursor-sdk`: melhor quando voce quer TypeScript-first runtime integration com Cursor-native harness capabilities e tool/runtime contracts explicitos.

## Usage
- Operators definem `AAMAD_TARGET_RUNTIME` antes do Build-phase implementation work; personas alinham generated runtime code e docs a `.cursor/rules/adapter-${AAMAD_TARGET_RUNTIME}.mdc`.