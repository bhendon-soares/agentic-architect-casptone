# Avaliacao de seguranca do MVP

## Escopo e metodo

Data: 2026-10-29. Persona: `@security.eng`. Revisao estatica do backend, frontend, configuracao e testes, scan de padroes em arquivos rastreados, testes locais com sentinelas sinteticas e audits de dependencias. Nenhum segredo local, banco ou servico externo foi acessado. Evidencias originais e retestes estao separados abaixo; testes com doubles nao certificam provider, dados legados ou implantacao de release.

## Findings (por severidade)

### High - Dados sensiveis em texto livre escapam da redacao antes de persistencia e envio ao LLM

- Evidencia original (antes dos ajustes): `src/backend/app/runtime/policy.py`, `redact`, tratava pares chave/valor de segredos, Bearer, e-mail e CPF, mas nao credenciais em frases livres nem telefones. Teste local com sentinelas ficticias confirmou que `Minha senha atual e EXEMPLO_FICTICIO_123; telefone 11987654321` preservava os dois valores. Em `src/backend/app/main.py`, `post_message` grava `safe_text` em `chat_messages` e o passa a `run_workflow`; `src/backend/app/runtime/crew.py` insere o texto no prompt do agente. A rota admin de conversas tambem usa redacao na leitura. O contraexemplo de codigo de recuperacao tambem foi reproduzido antes da correcao abaixo.
- Impacto: se um usuario inserir segredo ou dado pessoal fora dos formatos reconhecidos, o valor permanece no banco, pode chegar ao provider LLM e pode ser visto por administradores. Nao ha evidencia nesta revisao de que dados reais tenham sido expostos; a exploracao depende do conteudo fornecido no chat. Nao presumir que regex cubra dados pessoais arbitrarios.
- Mitigacao / owner: `@backend.eng` implementou redacao antes da persistencia e do workflow para formatos principais de credenciais, codigos de recuperacao e contatos; `@qa.eng` cobriu esses caminhos com sentinelas. `@devops.eng` deve restringir acesso e retencao de banco, logs e eventuais traces do SDK/provider e confirmar controles contratuais do provider. Tratamento de registros historicos e cobertura de novas variantes permanecem como acompanhamento de `@backend.eng` e `@devops.eng`.
- Estado: **mitigado para o escopo do MVP, com risco residual explicitamente aceito pelo responsavel pelo projeto em 2026-10-29**. O teste HTTP confirma ausencia da sentinela de recuperacao no workflow, banco, resposta e leituras do dono/admin; 10 testes focados e a suite backend (149 passaram, 20 opt-in ignorados) passaram na revalidacao. Permanecem exemplos sinteticos que escapam de `redact`: `Meu codigo de acesso e ACESSO_FICTICIO_73912` e `A senha para o portal e SENHA_FICTICIA_98123`; o retorno de `redact` e usado antes de persistir e chamar o workflow. A decisao do responsavel e seguir com essa limitacao inerente ao chat livre, considerando os principais formatos bloqueados, sem afirmar cobertura integral nem apagamento de dados historicos, backups ou traces. Reavaliar se mudar o escopo, a exposicao ou a politica de tratamento de dados.

### Medium - Advisories nas dependencias Python instaladas, sem resolucao travada

- Evidencia original (antes da atualizacao das dependencias): `.venv/bin/pip-audit --local --progress-spinner off --format columns` informou **71 entradas em sete pacotes** no ambiente local: `certifi 2026.7.22` (versoes corrigidas 2026.10.18/19), `chromadb 1.5.9` (sem correcao informada), `filelock 4.1.1` (4.2.1), `mcp 1.28.1` (1.30.0/2.2.0), `pillow 12.3.0` (13.0.0), `setuptools 79.0.1` (84.1.0 para o advisory mais recente) e `uv 0.11.33` (0.13.4). O numero de entradas nao equivale a 71 falhas exploraveis; ha IDs duplicados no feed. `support-backend 0.1.0` foi ignorado por nao constar no PyPI.
- Impacto: nao foi confirmado caminho de exploracao no MVP; a varredura inclui tambem ferramentas do ambiente que podem nao entrar no deploy. `src/backend/pyproject.toml` usa intervalos de versao sem lockfile Python rastreado, logo outra instalacao pode resolver versoes diferentes.
- Mitigacao / owner: `@backend.eng` deve avaliar a cadeia transitiva e o uso real dos pacotes afetados, atualizar dependencias compativeis e documentar os advisories sem correcao; `@qa.eng` deve rodar testes apos a atualizacao; `@devops.eng` deve travar a resolucao do release, executar `pip-audit` nela e definir tratamento de excecoes com owner e prazo.
- Estado: **risco residual ChromaDB aceito pelo responsavel pelo projeto para prosseguir hoje (2026-10-29)**. O novo `pip-audit --local` encontrou somente cinco entradas em `chromadb 1.5.9` (PYSEC-2026-311 duplicado, PYSEC-2026-3813/3814/3815), sem versao corrigida indicada; os outros seis pacotes do audit anterior nao apareceram. `MEMORY_ENABLED=False` em `src/backend/app/runtime/crew.py`; a revisao da API nao identificou servidor Chroma exposto, mas o isolamento de deploy nao foi comprovado. Este aceite e independente do risco residual de redacao e nao equivale a correcao nem autoriza automaticamente o release. `@devops.eng` deve confirmar implantacao sem servidor Chroma acessivel, auditar a resolucao de release e solicitar nova decisao de risco antes de Deliver ou se versao/exposicao/arquitetura mudarem.

### Medium - Bloqueio persistente de login por tentativas de terceiros

- Evidencia original: `src/backend/app/main.py`, funcao `login`: cinco senhas incorretas bloqueavam indefinidamente o par IP/e-mail ate desbloqueio administrativo. A implementacao atual usa `login_lock_active` com expiracao progressiva (15 minutos, dobrando apos novas series de cinco falhas ate o teto de 4 horas) e zera contadores apos 24 horas sem falhas.
- Impacto residual: quem conhece o e-mail de uma conta ainda pode interromper temporariamente seu acesso em um IP compartilhado repetindo tentativas. Exige alcance do login; o bloqueio permanece restrito ao par IP/e-mail, nao a todos os IPs da conta.
- Mitigacao / owner: `@backend.eng` deve definir desbloqueio automatico com janela de tempo e limitacao progressiva de tentativas sem remover controles contra brute force; `@qa.eng` deve testar recuperacao apos janela e IPs compartilhados; `@devops.eng` deve monitorar picos de bloqueio. Nao aceitar como resolvido apenas por haver desbloqueio manual.
- Estado: **bloqueio permanente mitigado** no fluxo testado: `test_login_lock_expires_and_repeated_failures_extend_it` e `test_rbac_login_lock_csrf_and_admin_safety` passaram, assim como a suite backend (145 passaram, 20 ignorados). Permanece possivel bloqueio temporario por tentativas repetidas em IP compartilhado; `@devops.eng` deve confirmar rate limiting e monitoramento no proxy antes do deploy.

### Low - `undici` vulneravel na cadeia de testes do frontend

- Evidencia original (antes da atualizacao do lockfile): `npm audit --audit-level=moderate --json` identificou `undici@7.30.0` como transitiva de `jsdom@29.1.1`, com oito advisories (incluindo DoS, bypass de validacao TLS e divulgacao entre origens); a ferramenta atribuiu severidade High ao pacote e indicou correcao em `>=7.30.1`. `npm audit --omit=dev --audit-level=moderate --json` informou zero vulnerabilidades de producao. A classificacao Low aqui reflete uso apenas na dependencia de teste, nao a severidade dos advisories.
- Impacto: afeta execucao de testes/build que consumam entrada nao confiavel via `jsdom`; nao ha evidencia de que o pacote entre no bundle servido aos usuarios.
- Mitigacao / owner: `@frontend.eng` deve atualizar a arvore travada para versao corrigida e executar testes; `@devops.eng` deve auditar tambem dependencias de desenvolvimento na CI e evitar rodar testes com conteudo nao confiavel ate a atualizacao.
- Estado: **mitigado no frontend local**. O lockfile fixa `undici@7.30.1`; `npm ls undici --prefix src/frontend` confirmou a versao instalada, `npm audit --audit-level=moderate --prefix src/frontend` retornou zero vulnerabilidades, 43 testes passaram e o build concluiu. A auditoria de dependencias de desenvolvimento na CI permanece a cargo de `@devops.eng`.

## Scan de segredos e dependencias

- `*scan-secrets`: `git ls-files` encontrou `.env.example`, nao `.env` rastreado, e o lockfile do frontend. Busca por padroes de chave privada, tokens comuns e atribuicoes longas de credenciais em arquivos rastreados retornou apenas `src/backend/tests/test_api.py`; a ocorrencia verificada e uma chave JWT sintetica de teste. Foram excluidos logs e datasets do scan de padroes; o resultado nao e garantia de ausencia de segredos fora do escopo, em historico Git ou em formatos nao reconhecidos. `.env.example` deixa credenciais em branco e orienta nao versionar o segredo.
- `*review-deps`: o audit original do frontend encontrou um pacote High apenas na arvore de desenvolvimento; o audit completo atual encontrou zero. O audit Python atual encontrou cinco entradas somente em ChromaDB (aceite condicionado acima); `support-backend` nao e auditavel via PyPI. `@devops.eng` deve repetir ambos na resolucao de release, registrando versoes e excecoes.
- Controles observados, nao certificacao: `JWT_SECRET` minimo de 32 bytes, cookie HttpOnly/SameSite Strict/Secure por padrao, allowlist de Origin para metodos mutaveis, consultas de sessao por dono e admin separado, URL remota HTTPS e redirects desabilitados (`src/backend/app/auth.py`, `src/backend/app/main.py`, `src/backend/app/adapters/tickets.py`). `COOKIE_SECURE=false` e permitido somente para HTTP local conforme `.env.example`.

## Decisao de handoff

O finding High nao bloqueia mais o handoff para `@devops.eng`: mitigacoes dos principais formatos foram revalidadas e o responsavel pelo projeto aceitou explicitamente a cobertura parcial inerente ao chat livre. Isto nao e certificacao de cobertura total nem aprovacao automatica de Deliver; `@devops.eng` ainda deve confirmar controles de retencao/acesso e isolamento de ChromaDB na implantacao, auditar dependencias do release e tratar as demais pendencias operacionais. A execucao de `aamad validate --phase build` valida artefatos, nao a seguranca do MVP.

## Sources

- `src/backend/app/main.py` (`post_message`, `get_admin_conversation`, `login`, `unlock_login`); `src/backend/app/runtime/policy.py` (`redact`); `src/backend/app/runtime/crew.py` (`run_workflow`); `src/backend/app/persistence/models.py` (`ChatMessage`, `LoginAttempt`); `src/backend/app/auth.py` (`client_ip`).
- `.env.example`; `src/backend/pyproject.toml`; `src/frontend/package.json`; `src/frontend/package-lock.json`; `src/backend/tests/test_api.py`; `src/backend/tests/test_policy_adapter.py`.
- Comandos locais de 2026-10-29: `git ls-files`, `git grep -l -I -E` (somente nomes), `npm audit --omit=dev --audit-level=moderate --json`, `npm audit --audit-level=moderate --json`, `npm ls undici --all`, `.venv/bin/pip-audit --local --progress-spinner off --format columns`, teste sintetico de `redact`, `aamad validate --phase build`.

## Assumptions

- Servico destinado a uso interno; exposicao publica, rate limiting no proxy, politica de retencao, configuracao do tracing e politica operacional de desbloqueio ainda nao confirmados. O responsavel pelo projeto aceitou o risco residual da redacao parcial do chat livre em 2026-10-29, alem do aceite independente de ChromaDB nas condicoes acima; esses aceites nao comprovam controles de deploy.

## Open Questions

- O proxy de producao limita tentativas de login por IP e monitora bloqueios?
- Qual e o periodo de retencao e o controle de acesso a prompts/traces no provider, SDK e backups do banco, inclusive para registros anteriores a mitigacao?
- Quais versoes exatas das dependencias Python serao entregues e quais advisories alcancam caminhos executados pelo MVP?

## Audit

| Data | Persona | Acao | Resultado |
| :-- | :-- | :-- | :-- |
| 2026-10-29 | `@security.eng` | `*assess-security`, `*scan-secrets`, `*review-deps`, `*document-security` | Findings High, Medium e Low ordenados, owners definidos; scans npm e Python locais executados, triagem no release pendente. Gate build passou; Deliver bloqueado pelo finding High ate mitigacao ou aceite explicito. |
| 2026-10-29 | `@security.eng` | Reteste preliminar de handoff | A amostra sintetica de redacao passou, e o lockfile atualizado retornou zero advisories no audit; demais correcoes em andamento ainda requerem validacao e aceite. Gate build passou novamente. |
| 2026-10-29 | Responsavel pelo projeto (usuario) | Aceite explicito de risco residual ChromaDB | Autorizado prosseguir com `chromadb 1.5.9` apesar dos advisories sem fix; manter isolamento do servidor e reavaliar se mudar a exposicao, arquitetura ou versao. Nao abrange o finding High. |
| 2026-10-29 | Backend | Correcao tecnica do finding High | Testes focados passaram para senha em frase natural e chave/valor com multiplas palavras, antes do LLM e da persistencia; revalidacao de seguranca e controles para dados legados/traces ainda pendentes. |
| 2026-10-29 | `@security.eng` | Revalidacao apos ajustes | Backend 145 passaram/20 opt-in ignorados; frontend 43 passaram e build passou; npm audit zero, pip-audit cinco entradas apenas no ChromaDB aceito para hoje. Sonda sintetica de codigo de recuperacao ainda passa pela redacao; finding High permanece aberto e Deliver nao recomendado. |
| 2026-10-29 | Backend | Reteste do contraexemplo de recuperacao | Teste HTTP falhou antes e passou apos redacao rotulada de codigos de recuperacao/backup; cobertura de leitura legada sintetica e variantes; backend 149 passaram/20 ignorados e Ruff lint aprovado. Finding High segue aberto ate revalidacao de seguranca e decisao sobre dados fora da politica e historico. |
| 2026-10-29 | Responsavel pelo projeto (usuario) / `@security.eng` | Decisao sobre o finding High | Aceita seguir com a cobertura parcial de redacao no chat livre: formatos principais e recuperacao revalidados, mas variantes de codigo de acesso e senha para o portal ainda escapam em sondas sinteticas. Finding High considerado mitigado para o MVP com risco residual aceito; handoff a DevOps nao bloqueado por este finding, sujeito aos controles operacionais pendentes. |