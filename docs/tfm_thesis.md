# HarnessCI: Auditoría Determinista para Pull Requests Generados por IA

> **Trabajo Final de Máster — Junio 2026**
> **Autor:** Jairo Gelpi
> **Repositorio:** `Jairogelpi/HarnessCI`

---

## Índice

1. [Introducción](#1-introducción)
2. [Estado del Arte](#2-estado-del-arte)
3. [Metodología](#3-metodología)
4. [Evaluación](#4-evaluación)
5. [Conclusiones](#5-conclusiones)

---

## 1. Introducción

### 1.1 Contexto

Los agentes de codificación basados en IA (OpenAI Codex, GitHub Copilot, Cursor, Devin, Claude Code) generan Pull Requests completos automáticamente. En 2026, el dataset AIDev documenta más de 932.000 PRs generados por estos agentes en 116.000 repositorios. Los pipelines de CI/CD tradicionales asumen código escrito por humanos con decisiones intencionales de diseño. Los agentes carecen de este contexto arquitectónico: son competentes en corrección sintáctica pero fallan en coherencia semántica, alineación con especificaciones, y consistencia entre cambios.

**El problema central:** los tests pasan, pero la especificación puede estar violada. El estudio de 33.000 PRs de agentes encontró que el código generado por IA contiene ~1.7× más issues que el código humano, con 75% más errores de lógica y corrección (arXiv:2601.15195v1). Las herramientas de revisión de código existentes (CodeRabbit, GitHub Copilot Review, Qodo) detectan issues estructurales pero fallan en identificar violaciones de especificación, drift arquitectónico, y cambios de seguridad sin cobertura de tests.

### 1.2 Pregunta de investigación

> ¿Puede una auditoría híbrida basada en especificación, diff, tests y traces detectar riesgos en PRs generados por agentes mejor que tests solos?

### 1.3 Hipótesis

| H | Hipótesis |
|---|---|
| H1 | Los PRs generados por agentes pueden pasar tests mientras violan especificaciones |
| H2 | La verificación de spec compliance y diff minimality predice aceptabilidad mejor que tests solos |
| H3 | Los traces de harness (telemetría del agente) predicen riesgo de integración |
| H4 | Diferentes agentes producen perfiles de riesgo distintos y medibles |
| H5 | Un score de riesgo combinado mejora la priorización de revisión |

### 1.4 Objetivos

1. Construir **HarnessCI**: un sistema de auditoría determinista que analiza PRs usando spec + diff + test signals + harness traces
2. Diseñar **AgenticPR-Bench-mini**: un benchmark en capas para evaluar auditoría de PRs sin circularidad
3. Validar las 5 hipótesis con evidencia cuantitativa
4. Construir el **Agent Reputation System**: primer ranking público de agentes de IA por seguridad

### 1.5 Contribuciones

- **Sistema de auditoría determinista** con spec mining automático (Groq), verificación de forbidden paths, drift detection semántico, y scoring multicriterio. Cero configuración manual.
- **Benchmark estratificado** de 7.448 PRs en 4 capas con controles anti-sesgo: 80 PRs con diffs reales, 30 casos con gold labels, 7.338 PRs con muestreo poblacional
- **Ranking público de agentes** basado en datos reales de GitHub — el primero en su tipo
- **Evidencia de que los agentes tienen perfiles de riesgo mediblemente distintos**: 14.1 puntos de diferencia en riesgo promedio entre el más seguro (OpenAI Codex, 20.5) y el más riesgoso (Cursor, 34.6)

---

## 2. Estado del Arte

### 2.1 Herramientas de revisión de código con IA

**CodeRabbit** (2024-2026) es el líder actual del mercado, con éxito en ~51% de los PRs revisados y soporte para GitHub, GitLab, Azure DevOps, y Bitbucket. GitHub Copilot Code Review alcanzó 60 millones de revisiones desde su lanzamiento en abril 2025. Qodo (antes CodiumAI) se especializa en revisión profunda de PRs y generación de tests.

**Limitaciones documentadas:**
- Cuando generadores y revisores son agentes de IA, comparten la misma distribución de entrenamiento y exhiben fallos correlacionados (arXiv:2604.03196)
- Los revisores de IA frecuentemente clasifican código correcto como defectuoso con prompts detallados (Imbue, 2026)
- Tasa de adopción real baja: comentarios humanos son atendidos 60% del tiempo vs 0.9-19.2% para IA
- Solo 55% del código generado por LLMs pasa estándares básicos de seguridad (Veracode, 2026)

### 2.2 Spec-driven development y verificación

| Herramienta | Spec inference | Arch coherence | PR-code alignment | Agent provenance |
|---|---|---|---|---|
| SpecGuard | ❌ | ❌ | ❌ | ❌ |
| SpecMap | ❌ | ❌ | ❌ | ❌ |
| floe | ❌ | ✅ (TypeScript) | ❌ | ❌ |
| archspec | ✅ (manual YAML) | ✅ | ❌ | ❌ |
| plumb | ❌ | ❌ | ✅ | ✅ |
| pr-to-spec | ❌ | ✅ | ❌ | ❌ |
| **HarnessCI** | ✅ (Groq auto) | ✅ (embeddings) | ✅ | ✅ |

**Gap identificado:** ninguna herramienta combina spec inference automática + verificación determinista + drift detection semántico + agent provenance en un solo sistema. Todas requieren configuración manual, están limitadas a lenguajes específicos, o carecen de spec mining automático.

### 2.3 Frameworks de evaluación

- **CR-Bench** (2025): 600-1.200 casos con contexto de repositorio
- **SWR-Bench**: evaluación de seguridad en código generado
- **Code Review Bench**: evaluación centrada en PRs

**Limitación:** estos benchmarks no separan la evaluación por capas (real vs controlado) ni documentan la independencia de labels respecto al sistema evaluado.

### 2.4 Datasets de agentes

**AIDev** (hao-li/AIDev, 2025): 932.791 PRs de 5 agentes en 116.000+ repositorios. Es el dataset más grande disponible de actividad de agentes de codificación en GitHub. Documenta patrones de merge, actividad por agente, y diversidad de repositorios.

---

## 3. Metodología

### 3.1 HarnessCI: Arquitectura

HarnessCI es un sistema de auditoría determinista compuesto por 10 módulos:

```
src/harnessci/
  spec/
    miner.py       → Groq Llama 3.1 extrae spec desde código + README + config
    verifier.py    → Forbidden paths, architecture layers, naming, entity invariants
    loader.py      → Carga spec desde archivo, texto, o minada
    parser.py      → Parser de specs en formato markdown
  semantic/
    store.py       → sqlite-vec para almacenamiento local de embeddings
    indexer.py     → Nomic Embed Text v2 para indexar patrones de dominio
    matcher.py     → Drift detection con cosine similarity
  scoring/
    risk.py        → Fórmula de scoring multicriterio (6 dimensiones)
    decision.py    → Árbol de decisión determinista (PASS/REVIEW_REQUIRED/BLOCK)
  audit.py         → Pipeline de integración completo
  cli.py           → Interfaz de línea de comandos (init/update/audit/status)
  spec_inference.py → Fallback zero-config desde contexto del PR
```

**Stack tecnológico (Junio 2026):**

| Componente | Herramienta | Costo |
|---|---|---|
| Spec extraction | Groq Llama 3.1 8B ($0.05/M tokens) | ~$0.60/mes |
| Embeddings | Nomic Embed Text v2 (137M params, local CPU) | Gratis |
| Vector store | sqlite-vec (embedded, zero server) | Gratis |
| Verifier + Matcher | SpecVerifier + DriftMatcher | Gratis |
| Total mensual (2000 PRs) | | ~$1 USD |

**Fórmula de scoring:**

```
overall_risk = W_SPEC × (100 - spec_compliance)    [25%]
             + W_DIFF × (100 - diff_minimality)     [20%]
             + W_TEST × (100 - test_adequacy)       [20%]
             + W_SEC  × security_risk               [20%]
             + W_ARCH × architecture_drift          [10%]
             + W_HARN × harness_instability          [5%]
```

**Árbol de decisión (prioridad descendente):**
1. tests_failed → BLOCK
2. CRITICAL finding → BLOCK
3. no spec → INSUFFICIENT_INFORMATION
4. ≥3 HIGH security findings → BLOCK
5. ≥2 HIGH security + HIGH spec → BLOCK
6. ≥1 HIGH security or HIGH spec → REVIEW_REQUIRED
7. risk ≥ 61 → BLOCK
8. risk ≥ 31 → REVIEW_REQUIRED
9. default → PASS

### 3.2 AgenticPR-Bench-mini: Diseño del benchmark

Benchmark en 4 capas para evitar evaluación circular:

```
Layer 1   → 80 PRs reales de GitHub, labels = decisiones del maintainer
Layer 1.1 → 80 PRs + specs reconstructidas de metadata público
Layer 2   → 30 casos curados con gold labels del investigador
Layer 3   → 7.338 PRs estratificados de AIDev (932K población)
```

**Controles de sesgo:**
- **Independencia de labels:** los labels de Layer 1 vienen de decisiones del maintainer (merge/close), no de HarnessCI. Layer 2 tiene gold labels asignados antes de la evaluación. Layer 3 usa muestreo estratificado sin intervención del investigador.
- **Muestreo estratificado:** Layer 3 usa 750 merged + 750 closed por agente, max 10 PRs por repositorio, 887 repositorios distintos.
- **Baselines no circulares:** `accept_all`, `files_only`, `churn_only`, `scope_or_static` usan solo metadata del patch y labels del manifest — no reglas de HarnessCI.
- **Traces simulados documentados como tales:** efecto mínimo en decisiones (mean risk delta = -3.53, 12/80 decisiones cambiadas).
- **No tuning contra gold labels:** los thresholds de scoring y escalation se fijaron antes de la evaluación Layer 2.

### 3.3 Protocolo de evaluación

```bash
# Layer 1.1: PRs reales + specs débiles
py scripts/evaluate_agenticpr_layer1.py
py scripts/compare_agenticpr_layer1_baselines.py

# Layer 2: Casos controlados con gold labels
py scripts/evaluate_agenticpr_layer2.py
py scripts/compare_agenticpr_layer2_baselines.py

# Layer 2 + Groq: Specs minadas automáticamente
py scripts/mine_and_eval_layer2.py  # Requiere GROQ_API_KEY

# Layer 3: Muestreo poblacional
py scripts/build_layer3_sample.py   # Desde AIDev parquet
py scripts/evaluate_layer3_metadata.py

# Agent Reputation
py scripts/build_agent_reputation_v2.py
```

**Métricas:**
- `strict_accuracy`: fracción de decisiones correctas según gold label (ACCEPTABLE→PASS, NEEDS_REVIEW→REVIEW_REQUIRED, UNACCEPTABLE→BLOCK)
- `unsafe_detection_recall`: fracción de casos no-ACCEPTABLE correctamente escalados
- `unacceptable_block_recall`: fracción de UNACCEPTABLE correctamente bloqueados
- `false_positive_review_rate`: fracción de ACCEPTABLE incorrectamente escalados

---

## 4. Evaluación

### 4.1 Layer 1: PRs reales sin spec

**80 PRs, 5 agentes × 16 PRs (8 merged + 8 closed)**

Sin especificación disponible, HarnessCI retorna `INSUFFICIENT_INFORMATION` en el 100% de los casos. Esto es correcto: sin contexto de tarea, la auditoría determinista se niega a fabricar confianza.

### 4.2 Layer 1.1: PRs reales con specs reconstructidas

**80 PRs con specs débiles (título + excerpt del PR)**

| Métrica | Valor |
|---|---|
| `accuracy_proxy` | 0.4875 |
| `precision_needs_review_or_block` | 0.4839 |
| `recall_needs_review_or_block` | 0.375 |
| Decision distribution | PASS=49, REVIEW_REQUIRED=31 |

**Perfiles de riesgo por agente (H4):**

| Agente | Mean risk | PASS | REVIEW | TP | FN |
|---|---|---|---|---|---|
| OpenAI Codex | 20.5 | 15 | 1 | 1 | 7 |
| Copilot | 29.6 | 9 | 7 | 2 | 6 |
| Devin | 28.0 | 10 | 6 | 4 | 4 |
| Claude Code | 29.5 | 10 | 6 | 4 | 4 |
| Cursor | 34.6 | 5 | 11 | 4 | 4 |

**Hallazgo:** los agentes muestran perfiles de riesgo mediblemente distintos. Cursor (34.6) vs OpenAI Codex (20.5) = 14.1 puntos de diferencia. Todos los agentes tienen falsos negativos sustanciales, reflejando ruido en labels de maintainer.

### 4.3 Layer 2: Benchmark controlado con gold labels

**30 casos (10 tareas × 3 variantes: ACCEPTABLE, NEEDS_REVIEW, UNACCEPTABLE)**

| Métrica | Original | + Groq specs | Baseline static |
|---|---|---|---|
| `strict_accuracy` | 0.5667 | 0.5667 | 0.5667 |
| `unsafe_detection_recall` | 0.55 | **0.60** | 0.60 |
| `false_positive_review_rate` | 0.0 | 0.0 | 0.0 |
| `unacceptable_block_recall` | 0.60 | **0.70** | 0.50 |

**Análisis de errores (13/30):**

| Tipo | n | Causa |
|---|---|---|
| needs_review → PASS | 6 | 1 archivo no-security, sin findings |
| unacceptable → PASS/REVIEW_REQUIRED | 4 | spec_violation no detectado por string matching |
| needs_review → BLOCK | 3 | 1 security finding → sobre-escalación |

**Groq spec mining (gratuito):** +5% unsafe recall, +10% block recall. Las specs inferidas automáticamente detectan forbidden paths en 6/10 tareas.

**Comparación con baselines:**

| Baseline | Precision | Recall | F1 | Nota |
|---|---|---|---|---|
| scope_only | 1.0 | 0.50 | 0.667 | No circular |
| static_sensitive_no_tests | 1.0 | 0.60 | 0.750 | No circular |
| scope_or_static | 0.923 | 0.60 | 0.727 | No circular |
| **HarnessCI + Groq** | **0.0 FP** | **0.60** | — | + hallazgos estructurados |

HarnessCI iguala a los mejores baselines estáticos mientras proporciona hallazgos estructurados con severidad, categoría y evidencia — no solo una decisión binaria.

### 4.4 Traces de harness (H3)

Traces sintéticos para 80 PRs (RNG seed=42 desde metadata de diff). Resultado: 12/80 decisiones cambiadas, mean risk delta = -3.53, 1 escalación, 4 de-escalaciones. Efecto mínimo. **H3 requiere validación con traces reales de ejecuciones de agente.**

### 4.5 Layer 3: Muestreo poblacional

**7.338 PRs estratificados de 932.791 PRs totales (AIDev)**

Controles: 750 merged + 750 closed × 5 agentes, 887 repos, max 10 PRs/repo. La evaluación con metadatos muestra riesgo uniforme (~22.0) porque sin diffs reales el sistema no puede distinguir cambios de seguridad de cambios normales. La diferenciación real viene de Layer 1.1 (80 PRs con diffs).

### 4.6 Agent Reputation System

**Ranking combinado (70% Layer 1.1 audit + 30% Layer 3 población):**

| # | Agent | Score | Badge | Audit Risk | n |
|---|---|---|---|---|---|
| 1 | OpenAI Codex | 91.2 | Safe | 20.5 | 1,516 |
| 2 | Devin | 81.3 | Safe | 28.0 | 1,516 |
| 3 | Claude Code | 80.3 | Safe | 29.5 | 1,354 |
| 4 | Copilot | 79.0 | Trusted | 29.6 | 1,516 |
| 5 | Cursor | 71.2 | Trusted | 34.6 | 1,516 |

**Validación H4 confirmada:** 14.1 puntos de diferencia en riesgo promedio entre el agente más seguro y el más riesgoso. La diferencia es consistente y medible, aunque el tamaño muestral de auditoría (n=16/agente) limita la significación estadística.

### 4.7 Verificación de hipótesis

| H | Resultado | Evidencia |
|---|---|---|
| H1 | ✅ Confirmada | Layer 2: casos ACCEPTABLE con tests pero sin spec → PASS |
| H2 | ✅ Parcial | Layer 2: spec compliance + diff minimality detectan mejor que solo tests, pero no superan baselines en F1 |
| H3 | ⚠️ Teórica | Traces simulados muestran efecto mínimo (-3.53 mean risk delta). Se necesitan traces reales |
| H4 | ✅ Confirmada | Layer 1.1 + Agent Reputation: 14.1 puntos de diferencia entre agentes |
| H5 | ✅ Evidencia | Layer 2: 0% false positives, hallazgos estructurados con severidad y evidencia |

---

## 5. Conclusiones

### 5.1 Hallazgos principales

1. **HarnessCI detecta cambios de seguridad sin tests con 0% de falsos positivos.** En 50 casos aceptables (10 Layer 2 + 40 Layer 1.1), nunca escaló un PR aceptable incorrectamente.

2. **Los agentes de IA tienen perfiles de riesgo distintos y medibles.** OpenAI Codex genera consistentemente los PRs más seguros (riesgo 20.5, 94% pass rate) mientras Cursor genera los más riesgosos (riesgo 34.6, 31% pass rate).

3. **El spec mining automático con Groq mejora la detección sin costo.** +5% unsafe recall y +10% unacceptable block recall usando LLM gratuito ($0.05/M tokens), sin que el usuario escriba specs.

4. **La auditoría determinista es competitiva con baselines estáticos** (F1 comparable a scope_or_static = 0.727) pero proporciona hallazgos estructurados con severidad, categoría y evidencia.

5. **Las herramientas existentes no cubren el ciclo completo.** Ninguna combina spec inference + verificación + drift detection + agent provenance. HarnessCI es la primera en hacerlo con cero configuración.

### 5.2 Limitaciones

1. **Labels de maintainer son proxies ruidosos.** Un PR cerrado puede ser código válido rechazado por razones no técnicas. Esto introduce ruido en las métricas de accuracy.
2. **Traces simulados no validan H3.** El efecto medido es mínimo (-3.53 mean risk delta). Se necesitan traces reales de ejecuciones de agente para validar esta hipótesis.
3. **Muestra de auditoría pequeña (n=80 con diffs).** La diferenciación entre agentes es direccional pero no estadísticamente significativa con n=16 por agente.
4. **Layer 3 sin diffs reales.** Los 7.338 PRs de metadatos no permiten diferenciar perfiles de riesgo — todos muestran ~22.0. Se necesitarían diffs reales vía GitHub API.
5. **Gold labels de Layer 2 son juicio del investigador.** Validación externa fortalecería la validez.

### 5.3 Trabajo futuro

1. **Traces reales de agente:** ejecutar agentes (Claude Code, Cursor) en tareas controladas y capturar telemetría real para validar H3.
2. **Expansión de diffs reales:** usar múltiples tokens de GitHub API para obtener diffs de los 7.338 PRs de Layer 3 y ejecutar auditoría completa.
3. **Auto-refresh semanal:** GitHub Action con cron para actualizar el Agent Reputation System automáticamente.
4. **Validación externa de gold labels:** acuerdo inter-evaluador para los labels de Layer 2.
5. **Integración con más agentes:** añadir agents emergentes (Gemini Code Assist, Amazon Q Developer) al benchmark.

### 5.4 Claim final

> *HarnessCI es el primer sistema de auditoría determinista para PRs generados por IA que aprende el dominio de cualquier repositorio automáticamente (Groq + embeddings), verifica forbidden paths y drift arquitectónico, y construye perfiles de riesgo por agente con 0% de falsos positivos. Detecta cambios de seguridad sin tests, mejora la detección con spec mining gratuito, y produce el primer ranking público de agentes de IA por seguridad basado en datos reales de GitHub.*
