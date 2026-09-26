---
description: "AAMAD: Definir e rodar a evaluation strategy (golden dataset, code-based checks, LLM-as-judge, production monitoring recommendations)"
agent: qa-eng
---
# Run Evals

Defina e implemente a evaluation strategy para o projeto AAMAD atual, depois escreva `project-context/2.build/evals.md`. Responsabilidade de `@qa.eng`; invocado como `*run-evals`.

Para detalhes de grading-ladder, judge calibration, exemplo trabalhado e anti-patterns a evitar, veja [reference.md](reference.md).

## Step 1: Load context

Leia, nesta ordem:
- `project-context/1.define/prd.md`, `sad.md`, `system-description.md` (if present), `project-context/1.define/user-stories/*.md`
- `project-context/2.build/backend.md`, `integration.md`
- `aamad.config.yml` (if present); resolve `AAMAD_TARGET_RUNTIME`

Se a secao "9. Testing & Quality Assurance Specifications" de `sad.md` ja contiver uma tabela de evaluation criteria (dimension, metric, threshold, grading method, source), trate-a como o contrato a implementar — nao derive novamente thresholds que ela ja decidiu. A maioria dos projetos criados antes dessa capacidade nao tera essa tabela; isso e esperado, nao um erro.

## Step 2: Gap check — ask the operator

O business context que uma eval suite precisa frequentemente esta ausente de `project-context/`. Nao invente thresholds, SLAs ou risk tolerance — conforme `aamad-core.mdc`, quando inputs estiverem ausentes ou ambiguos, escreva Assumptions e Open Questions em vez de fabricar conteudo.

Verifique estes seis itens. Pule qualquer item ja respondido pela criteria table do SAD ou por outro artifact carregado:

1. Accuracy threshold — o que conta como resposta aprovada
2. Latency target (p95) e cost ceiling por request
3. Consequencia de uma resposta errada — define o nivel de confianca exigido
4. Regulatory/safety constraints e qualquer acao que o sistema nunca deve executar
5. Representative input distribution e origem dos golden data (real logs vs. synthetic)
6. Se existe um human-labeled set para judge calibration, e qual model pode atuar como judge

Se algum permanecer sem resposta, pergunte em uma **single batched round** — nao interrogue um por vez. Cada pergunta deve oferecer 3–5 opcoes concretas como valores utilizaveis (nao rotulos abstratos), alem de uma escape hatch:

- Boa opcao: "p95 under 2s — interactive chat"
- Opcao ruim: "Low latency"
- Sempre inclua uma escape hatch: "No target defined yet — use a placeholder and flag under Open Questions"

Quando a ferramenta `AskQuestion` estiver disponivel, use-a para que as opcoes aparecam como escolhas selecionaveis na janela de chat. Quando ela nao estiver disponivel, apresente as mesmas perguntas como uma lista numerada curta na resposta e aguarde a resposta do operador antes de continuar.

Registre cada resposta em `evals.md` em **Assumptions**, atribuida ao operador. Para qualquer item que o operador nao queira especificar, use o valor de escape-hatch e registre em **Open Questions** em vez de bloquear.

## Step 3: Derive success criteria

Para cada comportamento em escopo, transforme um requisito vago em algo mensuravel:

1. **Nomeie o comportamento especificamente** — "summarize claims accurately" vira "extract claimant name, policy number, and loss amount with 100% field accuracy."
2. **Defina o threshold a partir do SLA e do cost-of-wrong-answer**, nao do score acidental do build atual.
3. **Enumere failure modes** como categorias do dataset (ex.: missing field, wrong-claim leakage, malformed output).
4. **Inclua adversarial e edge-case inputs** — um golden dataset apenas com inputs limpos nao prediz performance em producao.

Cubra no minimo cinco dimensions: accuracy, latency, safety, security, cost. Veja [reference.md](reference.md) para um exemplo completo nessas cinco.

## Step 4: Select grading methods (the ladder)

Suba apenas ate o nivel que o comportamento exige:

| Method | Use for | Cost |
|---|---|---|
| **Code-based** | Schema validation, exact/regex match, length, presence checks, numeric comparisons — anything unambiguous | Milliseconds, near-zero |
| **LLM-as-judge** | Tone, reasoning quality, faithfulness, edge-case appropriateness — anything requiring interpretation | One API call per item |
| **Human review** | High-stakes or novel behavior neither code nor a calibrated judge can be trusted on | Slow, expensive, sample only |

Rules:
- Prefira code-based sempre que o comportamento permitir.
- Avalie com um judge model **diferente** do model under test, para evitar self-preference.
- Use constrained verdicts (um conjunto pequeno e fixo de labels) em vez de free-form scores.
- **Calibre o judge** contra exemplos human-labeled antes de confiar nos verdicts — um judge nao calibrado produz scores confiantes que podem nao ser confiaveis, o que e pior do que nao ter avaliacao automatizada.

## Step 5: Build the suite

No projeto alvo, crie:
- `evals/dataset/*.jsonl` — golden dataset, one file per failure-mode category from Step 3
- `evals/checks/` — code-based check functions
- `evals/judge/` — judge prompt(s) and rubric, if any dimension needs one
- `evals/run.py` (or runtime-appropriate equivalent) — runner that executes the dataset against the system and produces per-item pass/fail or score

### Runtime instrumentation

Instrumente conforme a regra ativa do adapter `AAMAD_TARGET_RUNTIME` para que o eval runner e o production monitoring posterior compartilhem os mesmos trace data:

- **`crewai`** — use step callbacks / event listeners for task start/stop, retries, and guardrail outcomes; persist logs under `project-context/2.build/logs` per `adapter-crewai.mdc`.
- **`claude-agent-sdk`** — use `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop` hooks to capture lifecycle events; persist under `project-context/2.build/logs` per `adapter-claude-agent-sdk.mdc`.
- **`cursor-sdk`** — capture Prompt Trace and per-tool-call diagnostics; persist lifecycle logs under `project-context/2.build/logs` per `adapter-cursor-sdk.mdc`.

Redija/remova secrets de todo trace output, seguindo a secao Logging de cada adapter.

## Step 6: Execute and interpret

- Rode a suite completa; registre breakdown por categoria, nao apenas media — um aggregate score pode parecer saudavel enquanto uma categoria especifica falha.
- Reporte calibration evidence para qualquer judge em uso (agreement rate contra a amostra human-labeled).
- Marque qualquer dimension sem resultado aprovado como Deliver blocker ou accepted gap explicito.

## Step 7: Write evals.md

Preencha `.cursor/templates/evals-template.md` e escreva em `project-context/2.build/evals.md`. Inclua:
- A tabela Success Criteria com uma coluna `Source` rastreando cada threshold para um anchor de PRD/SAD ou resposta do operador no Step 2.
- **Production Monitoring Recommendations** — o handoff explicito para `@devops.eng` no Deliver:
  - Request-level trace fields: model/version, input/output token counts, latency, stop reason, tool calls
  - Dashboard metrics: cost per request, latency p50/p95, task success rate, error rate by type
  - Threshold alerts: e.g. cost spike over 150% of 7-day average, latency p95 crossing SLA
  - Change attribution: distinguir model drift, data drift e efeitos de model-update para aplicar a correcao adequada
  - Business-KPI translation: mapear as technical metrics acima para a business metric que elas influenciam (ex.: task success rate → first-contact resolution)
- Acrescente uma entrada de Audit: timestamp, persona id (`qa-eng`), action (`run-evals`), `AAMAD_TARGET_RUNTIME` resolvido.

## Adopting evals in an existing project

Se `sad.md` nao tiver criteria table porque o projeto chegou ao QA antes desta capacidade existir, rode esta skill diretamente — o gap check do Step 2 fornece o que o SAD normalmente teria definido. Seja deliberado para que o dataset resultante nao apenas confirme o comportamento atual: derive itens do PRD e das user stories, e inclua inputs contra os quais a implementacao nunca foi exercitada (veja o contract-review postmortem em [reference.md](reference.md)). Quando `evals.md` tiver thresholds acordados, use `prompt-sync-docs` para incorporá-los de volta na secao 9 do SAD, criando um gate real para mudancas futuras.