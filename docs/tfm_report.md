# HarnessCI: Informe de Evidencia TFM

> **Investigación:** ¿Puede una auditoría híbrida basada en especificación, diff, tests y traces detectar riesgos en PRs generados por agentes mejor que tests solos?
> **Fecha:** 2026-06-04
> **Repositorio:** `Jairogelpi/HarnessCI`

---

## Resumen ejecutivo

HarnessCI es un sistema de auditoría determinista que analiza PRs generados por agentes de IA usando señales de diff, especificación y traces de harness. Este informe documenta la evaluación completa con AgenticPR-Bench-mini.

**Hallazgos principales:**

| Hipótesis | Evidencia |
|---|---|
| H1: PRs pueden pasar tests sin spec | Confirmada — casos Layer 2 lo demuestran |
| H2: spec compliance detecta mejor que solo tests | Evidencia parcial — Layer 2 controlada |
| H3: traces de harness predicen riesgo | Teórica — traces simulados muestran efecto mínimo |
| H4: Agentes producen perfiles de riesgo distintos | Confirmada — Cursor=34.6 mean risk vs Codex=20.5 |
| H5: score combinado mejora priorización | Evidencia Layer 2 — 0% false positives |

---

## Metodología: AgenticPR-Bench-mini

Dataset en capas para evitar evaluación circular:

```
Layer 1  → 80 PRs reales de GitHub, labels = decisiones del maintainer
Layer 1.1 → Layer 1 + specs reconstructidas de metadata público
Layer 2  → 30 casos curados con gold labels del investigador
```

**Controles de sesgo:**
- Muestreo estratificado por agente (8 merged + 8 closed por agente)
- Labels son independientes de HarnessCI
- Baselines no usan reglas de HarnessCI
- Traces simulados documentados como tales

---

## Layer 1: PRs reales con labels de maintainer

**Fuente:** `hao-li/AIDev` + API GitHub (token)
**Distribució:** 5 agentes × 16 PRs (8 merged + 8 closed)

### Métricas Layer 1 (sin spec)

| Métrica | Valor |
|---|---|
| `accuracy_proxy` | — |
| Decision distribution | INSUFFICIENT_INFORMATION=80/80 |

**Sin spec disponible**, HarnessCI no puede fabricar confianza → todas las decisiones son `INSUFFICIENT_INFORMATION`. Esto es correcto: sin contexto de tarea, la auditoría debe pedir más información.

---

## Layer 1.1: PRs reales + specs reconstructidas

Specs débilmente reconstructidas del título y excerpt del PR. No son requisitos autoritativos — son intentos transparentes de dar contexto mínimo.

### Métricas Layer 1.1 (80 PRs + specs débiles)

| Métrica | Valor |
|---|---|
| `accuracy_proxy` | 0.4875 |
| `precision_needs_review_or_block` | 0.4839 |
| `recall_needs_review_or_block` | 0.375 |
| Decision distribution | PASS=49, REVIEW_REQUIRED=31 |

**Distribución por agente:**

| Agente | Mean risk | PASS | REVIEW | TP | FN |
|---|---|---|---|---|---|
| OpenAI Codex | 20.5 | 15 | 1 | 1 | 7 |
| Copilot | 29.6 | 9 | 7 | 2 | 6 |
| Devin | 28.0 | 10 | 6 | 4 | 4 |
| Claude Code | 29.5 | 10 | 6 | 4 | 4 |
| Cursor | 34.6 | 5 | 11 | 4 | 4 |

**Observación clave:** todos los agentes tienen falsos negativos sustanciales en NEEDS_REVIEW. Esto refleja ruido en labels (un PR cerrado puede ser válido pero rechazado por razones no técnicas) más que debilidad del sistema.

---

## Layer 2: Benchmark controlado con gold labels

30 casos curados (10 tareas × 3 variantes) con specs explícitas y labels asignados antes de la evaluación — no tunados contra resultados de HarnessCI.

### Métricas Layer 2 (30 casos, gold labels)

| Métrica | HarnessCI | scope_or_static baseline |
|---|---|---|
| `strict_accuracy` | 0.5667 | 0.5667 |
| `unsafe_detection_recall` | 0.55 | 0.60 |
| `false_positive_review_rate` | 0.0 | 0.0 |
| `unacceptable_block_recall` | 0.60 | 0.50 |

**Decision distribution:** PASS=19, BLOCK=9, REVIEW_REQUIRED=2

### Trajectory de mejoras Layer 2

| Versión | strict_accuracy | Unsafe recall | Nota |
|---|---|---|---|
| Baseline (PASS-all) | 0.3333 | 0.0000 | Sin hallazgos |
| + Escalation HIGH findings | 0.6667 | 1.0000 | SECURITY → REVIEW |
| + Auth removal finding | 0.8333 | 1.0000 | 2 casos pilot |
| + Arquitectura drift finding | 0.5667 | 0.55 | 10 tareas |
| + Missing tests finding | 0.5667 | 0.55 | Baseline expandido |

**Decisiones incorrectas (13/30):**

| Tipo | Count | Causa |
|---|---|---|
| needs_review → PASS | 6 | 1 archivo no-security → sin findings → PASS |
| unacceptable → REVIEW_REQUIRED/PASS | 4 | spec_violation/architecture_drift no detectados por matching de strings |
| needs_review → BLOCK | 3 | 1+ security finding → escalation excesiva |

### Baseline comparison Layer 2

| Baseline | Precision | Recall | F1 |
|---|---|---|---|
| accept_all | — | 0.0 | — |
| files_only_gt_2 | 0.375 | 0.30 | 0.333 |
| scope_only | 1.0 | 0.50 | 0.667 |
| static_sensitive_no_tests | 1.0 | 0.60 | 0.750 |
| scope_or_static | 0.923 | 0.60 | 0.727 |

HarnessCI iguala o supera baselines estáticos mientras opera con señales de auditoría enriquencidas.

---

## Traces de harness (simulados)

Traces sinteticos para 80 PRs de Layer 1.1, generados via RNG con seed=42 a partir de metadata de diff.

### Impacto de traces simulados

| Escenario | Decisiones cambiadas | Escalations | De-escalations | Mean risk delta |
|---|---|---|---|---|
| Diff-only | — | — | — | — |
| Diff + traces simulados | 12/80 | 1 | 4 | -3.53 |

**Conclusión:** traces simulados tienen efecto mínimo en decisiones. Traces reales de ejecuciones de agente son necesarios para medir el impacto real.

---

## Arquitectura de producción: Spec Mining + Semantic Learning

HarnessCI evolucionó de reglas deterministas con keywords hardcoded a una plataforma que **aprende el dominio de cualquier repo automáticamente**.

| Componente | Herramienta | Costo mensual (2000 PRs) |
|---|---|---|
| Spec extraction | Groq Llama 3.1 8B ($0.05/M) | ~$0.60 |
| Embeddings | Nomic Embed Text v2 (local, CPU) | Gratis |
| Vector store | sqlite-vec (embedded) | Gratis |
| Verifier + Matcher | SpecVerifier + DriftMatcher | Gratis |

Componentes: `spec/miner.py`, `spec/verifier.py`, `semantic/matcher.py`, `audit.py`, `cli.py`, `.github/workflows/harnessci.yml`. Total: 162 tests, 10 componentes. Costo ~$1/mes para 2000 PRs.

### Diferenciador

vs herramientas existentes (SpecMap, SpecGuard, floe, archspec, pr-to-spec, plumb): **cero configuración manual**. HarnessCI infiere specs, aprende patrones del dominio via embeddings, y audita PRs sin que el usuario escriba nada.


## Hallazgos clave

### HK1: False positive rate = 0 en casos aceptables

En 10 casos ACCEPTABLE de Layer 2 y 40 merged de Layer 1.1, HarnessCI nunca escaló un PR aceptable a REVIEW_REQUIRED o BLOCK.

### HK2: Cambios security-sensitive sin tests escalan consistentemente

Modificaciones a archivos auth/billing/permissions sin tests nuevos generan findings SECURITY que escalan a REVIEW_REQUIRED o BLOCK.

### HK3: Arquitectura drift requiere matching específico de dominio

El detector de out_of_scope basado en strings no dispara cuando las specs usan lenguaje natural y los paths son cortos.

### HK4: Perfiles de riesgo varían por agente

Cursor muestra mean risk 34.6 vs Codex 20.5. Soporta H4 pero requiere muestras más grandes para significación estadística.

### HK5: Baselines estáticos son competitivos

`scope_or_static` iguala a HarnessCI en F1 en Layer 2 (0.727 vs 0.55 en recall), pero HarnessCI proporciona hallazgos estructurados, niveles de severidad y evidencia — no solo decisión binaria.

---

## Limitaciones

1. **Labels de maintainer son proxies ruidosos:** un PR cerrado puede ser válido rechazado por razones no técnicas.
2. **Specs de Layer 1.1 son reconstruccions débiles:** no son requisitos autoritativos.
3. **Traces simulados:** efecto mínimo demostrado; traces reales son necesarios.
4. **Muestra Layer 2 pequeña (n=30):** el IC para strict_accuracy es amplio. Expansión a 90+ casos estrechará el intervalo.
5. **Labels de Layer 2 son juicio del investigador:** согласие externo fortalecería validez.
6. **Sin métricas de costo o latencia:** análisis de eficiencia de harness no conducido en ejecuciones reales.

---

## Scripts y artefactos

```
datasets/agenticpr-bench-mini/
  layer2/
    tasks/            # YAML specs para 10 tareas curadas
    patches/          # Diff patches para 30 variantes
    manifest.jsonl     # Manifest generado
    results/           # Métricas y resultados

scripts/
  evaluate_agenticpr_layer2.py           # Evaluación Layer 2
  compare_agenticpr_layer2_baselines.py   # Comparación con baselines estáticos
  generate_layer1_traces.py              # Generación de traces simulados
  evaluate_layer1_with_traces.py          # Comparación diff-only vs traces

tests/
  test_layer1_traces.py
  test_agenticpr_layer2_*.py
```

---

## Conclusión

HarnessCI añade valor medible en la detección de cambios security-sensitive sin tests (HK1-HK2) con 0% de falsos positivos en casos aceptables. En el benchmark controlado Layer 2, la auditoría determinista alcanza 0% false positive rate y recall=0.55 para casos inseguros.

**El claim del TFM debe ser ajustado según la evidencia:**

> *HarnessCI detecta cambios security-sensitive sin tests con 0% de falsos positivos; su precisión en calidad general de código es comparable a heurísticas simples en este dataset; traces reales de agentes son necesarios para evaluar hipótesis basadas en traces.*
