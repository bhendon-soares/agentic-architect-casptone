# AAMAD Evaluation Strategy Template

## Context & Instructions
Defina e registre a evaluation strategy e os resultados para o MVP construido neste projeto.
Derive success criteria da evaluation criteria table do SAD (section 9) quando presente, do PRD e de `system-description.md` / user-story acceptance criteria. Quando business context obrigatorio (thresholds, SLA, risk tolerance) estiver ausente, pergunte ao operador conforme Step 2 de `.cursor/skills/run-evals/SKILL.md` em vez de inventar valores.
Alinhe runtime instrumentation com a regra ativa do adapter `AAMAD_TARGET_RUNTIME`.

## Input Requirements

**PRD**: [REFERENCE `project-context/1.define/prd.md`]
**SAD** (section 9 criteria table, if present): [REFERENCE `project-context/1.define/sad.md`]
**System Description / User Stories** (opcional): [REFERENCE IF PRESENT]
**backend.md / integration.md**: [REFERENCE]
**Selected Runtime**: [crewai | claude-agent-sdk | cursor-sdk]

## Evaluation Report — Generate All Sections Below

### 1. Eval Strategy

- Behaviors no escopo desta eval suite e por que
- Dimensions cobertas (accuracy, latency, safety, security, cost — estenda se o PRD exigir mais)

### 2. Success Criteria and Thresholds

| ID | Dimension | Metric | Threshold | Grading Method | Source |
|----|-----------|--------|-----------|-----------------|--------|
| EC-001 | Accuracy | … | … | Code-based / LLM judge / Human | PRD §x / SAD §9 / Operator answer |

A coluna **Source** e obrigatoria: todo threshold deve rastrear para um anchor de PRD/SAD ou para uma resposta do operador registrada em Assumptions. Uma linha sem source rastreavel sinaliza que o numero foi chutado.

### 3. Golden Dataset

- Failure-mode categories cobertas, com contagem de itens por categoria
- Cobertura adversarial / edge-case
- Provenance: dados reais com formato de producao vs. synthetic, e por que

### 4. Grading Methods

- Code-based checks implementados (liste files/functions)
- LLM-as-judge rubric(s) usados, judge model (diferente do model under test) e calibration result (agreement rate vs. amostra human-labeled)
- Human-review items, se houver, e reviewer process

### 5. Implementation

- Localizacao da eval suite no repo (ex.: `evals/dataset/`, `evals/checks/`, `evals/judge/`, `evals/run.py`)
- Runtime instrumentation adicionada (trace fields, hooks/callbacks usados) conforme a regra ativa do adapter
- Como rodar a suite novamente

### 6. Results

- Breakdown pass/fail ou score por categoria (nao apenas aggregate mean)
- Dimensions que passam vs. falham o threshold
- Known gaps e se bloqueiam Deliver ou sao explicitamente aceitos

### 7. Production Monitoring Recommendations

Handoff para `@devops.eng` na Deliver stage:

- **Request-level trace fields**: model/version, input/output token counts, latency, stop reason, tool calls
- **Dashboard metrics**: cost per request, latency p50/p95, task success rate, error rate by type
- **Threshold alerts**: e.g. cost spike over 150% of 7-day average, latency p95 crossing SLA
- **Change attribution**: como distinguir model drift, data drift e model-update effects
- **Business-KPI translation**: mapear cada technical metric acima para a business metric que ela influencia

### 8. Future Work

- Deferred eval coverage (ex.: multi-turn conversation evals, live A/B ou shadow testing) nao implementada neste MVP pass

## Sources

- Paths de PRD / SAD / system-description / user-story usados

## Assumptions

- Thresholds e scope decisions fornecidos pelo operador durante o Step 2 gap check, atribuidos como tal

## Open Questions

- Qualquer item de gap-check que o operador recusou especificar, com o placeholder value usado no lugar

## Audit

- Timestamp, persona id (`qa-eng`), action (`run-evals`), resolved `AAMAD_TARGET_RUNTIME`
