---
applyTo: '**'
name: Adapter Crewai Rules
description: Orientacao de runtime adapter para construir MVPs gerados pelo AAMAD em CrewAI.
---

# CrewAI Adapter Rules

## Purpose
- Definir orientacao especifica de runtime quando `AAMAD_TARGET_RUNTIME=crewai`.
- Este adapter governa como implementation personas criam scaffold e validam o runtime MVP gerado.

## Setup
- Instale CrewAI e dependencies no backend environment gerado.
- Required runtime files devem incluir:
    - `config/agents.yaml`
    - `config/tasks.yaml`
    - `crew.py` (or equivalent runtime entrypoint)
- Carregue secrets de environment variables e forneca nomes em `.env.example`.
- Registre `llm`, temperature e max token controls resolvidos em Audit.

## Mapping
- Todas as CrewAI agent e task definitions DEVEM ser externalizadas em arquivos YAML em um diretorio config/ (ex.: config/agents.yaml, config/tasks.yaml).
- Use task context chaining explicito (`Task.context`) para deterministic dependency flow.
- Defina `expected_output` com required headings e target artifact paths.
- Prefira `allow_delegation=false` salvo se o SAD justificar delegated manager patterns.

## Execution
- Prefira sequential process mode para builds de MVP reproduziveis.
- Use hierarchical process mode apenas quando justificado no SAD e documentado em Audit.
- Baseline controls:
    - `max_iter <= 12` for MVP tasks unless explicitly justified.
    - `max_execution_time` tuned per epic.
    - `max_retry_limit >= 2`.
    - `max_rpm` set at crew level for budget stability.
- Se usar function-calling agents, nao troque o modo no meio da execucao; registre o modo escolhido em Audit.
- Use `kickoff_for_each` apenas para batch items realmente independentes e documente deterministic merge keys.

## Tools
- Vincule apenas o minimo required tool set por agent/task.
- Valide tools referenciadas por YAML antes do kickoff para evitar runtime binding errors.
- Mantenha tool configs JSON-serializable; carregue secret parameters via env vars.
- Permita web/API tools apenas quando explicitamente justificado pelo persona scope.

## Logging
- Capture rendered system/user prompts em Prompt Trace antes da execucao.
- Registre lifecycle events (task start/stop, retries, guardrail outcomes) em Trace Log.
- Mantenha Prompt Trace e Trace Log em project-context artifacts, nao inline no generated code.
- Se usar step callbacks/event listeners, redija secrets e persista logs em `project-context/2.build/logs`.

## Quality Gates
- Valide required template headings antes da escrita final do artifact.
- Use `Task.guardrail` para high-risk outputs (schema limits, content rules, size checks).
- Exija `Task.id` e output path explicito para traceability.
- Para secoes machine-ingested output, imponha markdown/JSON simples sem code fences.
- Para high-risk outputs, exija human review gate (`human_input=true` ou explicit review task).

## Failure Policy
- Em missing runtime prerequisites, unresolved tools, heading mismatches ou guardrail failure: pare e escreva Diagnostic.
- Em context overflow ou budget breach: pare e reporte remediation notes no artifact.

## Memory
- Default memory=False para reproducibility; se memory=True, restrinja a current epic, redija secrets e persista logs em project-context/2.build/logs.
- Se memory=True, defina `CREWAI_STORAGE_DIR` para um path escopado ao projeto e registre scope/retention em Audit.