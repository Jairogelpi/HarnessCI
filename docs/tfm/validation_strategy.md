# HarnessCI: Estrategia de Validación — Roadmap a Excelencia

> **Objetivo:** Superar las 3 limitaciones críticas del TFM y convertir HarnessCI
> en el estándar de facto para auditoría de PRs generados por agentes.
> **Fecha target:** Julio 2026 (defensa TFM)

---

## Gap 1: Validación estadística insuficiente

**Situación actual:** n=80 con diffs reales, n=30 gold labels, n=7.338 metadata.
**Meta:** 95% confidence interval con margen <5% en strict_accuracy.

### 1.1 Layer 2 extendido a 1020 casos (340 tareas × 3 variantes)

Hecho. Se generaron 340 tareas determinísticas a partir de 20 templates y 3 variantes por tarea, para un total de 1020 casos balanceados (340 ACCEPTABLE, 340 NEEDS_REVIEW, 340 UNACCEPTABLE) sin sesgo del investigador.

**Artefactos:** `scripts/build_layer2_extended.py`, `scripts/generate_layer2_patches.py`, `datasets/agenticpr-bench-mini/layer2/manifest_extended.json`, `datasets/agenticpr-bench-mini/layer2/results/layer2_extended_metrics.json`.

**Resultado observado:** `strict_accuracy = 0.9833`, `unsafe_detection_recall = 1.0000`, `unacceptable_block_recall = 1.0000`, `false_positive_review_rate = 0.0`.

**Lectura:** el benchmark extendido confirmó 0 falsos positivos en ACCEPTABLE y cobertura completa de los casos inseguros en esta versión; el foco siguiente pasa a validar con diffs reales y traces reales para evitar sobreajuste al benchmark sintético.

### 1.2 Fetch diffs reales para 500 PRs de Layer 3

Usar 3 tokens de GitHub API (rotando) para bajar 500 diffs de los 7.338 PRs muestreados.

```bash
# Paralelizar con múltiples tokens
GITHUB_TOKEN_1=xxx py scripts/fetch_layer3_diffs.py --shard 0 --total 3
GITHUB_TOKEN_2=yyy py scripts/fetch_layer3_diffs.py --shard 1 --total 3
GITHUB_TOKEN_3=zzz py scripts/fetch_layer3_diffs.py --shard 2 --total 3
```

Cada shard: 167 PRs × ~2s API call = 5.5 minutos con rate limit de 5000/hora.

**Target métrico:** 500 audited PRs con diffs reales → IC-95% ~±4% en accuracy.

### 1.3 Bootstrap con 1000 iteraciones

```python
# scripts/bootstrap_layer3_confidence.py
# Para cada agente, samplear con reemplazo 1000 veces de los 500 audited PRs
# Reportar: mean ± 95% CI para strict_accuracy, unsafe_recall, block_recall
```

**Target:** "HarnessCI achieves strict_accuracy = 0.XX ± 0.0Y (95% CI, n=500 audited + 100 gold labels)."

### 1.4 Observed preliminary real-diff audit (500 cases)

Hecho de forma preliminar sobre los primeros 500 diffs reales auditados con el pipeline nuevo. El slice está sesgado por el orden del manifest (predominantemente Claude_Code), así que no se debe leer como muestra balanceada por agente. El script ya soporta `--start/--end` para estratificar futuras corridas.

**Resultado observado:** `strict_accuracy = 0.204`, `unsafe_detection_recall = 0.0`, `unacceptable_block_recall = 0.0`, `false_positive_review_rate = 0.796`.

**Bootstrap 1000 iteraciones:** `strict_accuracy = 0.204` con IC-95% `[0.170, 0.240]`.

**Lectura:** la heurística actual no generaliza bien a diffs reales; la tasa de revisión falsa sobre ACCEPTABLE es demasiado alta y la detección de casos inseguros es nula en este slice.

---

## Gap 2: Traces reales para validar H3

**Situación actual:** traces simulados (RNG seed=42), mean_risk_delta = -3.53.
**Meta:** Ejecutar 3 agentes en 10 tareas controladas, capturar telemetría real.

### 2.1 Harness capture script

Wrapper que ejecuta un agente y captura su telemetría:

```python
# scripts/capture_agent_trace.py
# 1. Crea un repo temporal con la tarea
# 2. Invoca al agente con la spec
# 3. Captura: tokens usados, tool calls, edits, test runs, errores, latencia
# 4. Guarda trace.json con schema TelemetrySummary
```

### 2.2 Agentes a evaluar

| Agente | Tareas | Costo estimado |
|---|---|---|
| Claude Code (CLI) | 10 | ~$5 (Sonnet 4) |
| Cursor (Agent mode) | 10 | ~$3 (incluido en sub) |
| Copilot (Chat) | 10 | ~$2 (incluido en sub) |
| **Total** | **30 ejecuciones** | **~$10** |

### 2.3 Re-evaluación de H3

Para cada trace real, correr `harnessci audit` con y sin telemetry:

```bash
py scripts/evaluate_h3_with_real_traces.py
# Output: mean_risk_delta_with_real_traces, p-value, H3 confirmed/rejected
```

**Target:** "Real agent traces improve risk prediction by ΔX points (p < 0.05, n=30). H3 confirmed."

---

## Gap 3: Recall insuficiente (0.60)

**Situación actual:** 13/30 errores en Layer 2. Causas:
- 6 needs_review → PASS (1 archivo no-security, sin findings)
- 4 unacceptable → PASS/REVIEW (spec_violation no detectado)
- 3 needs_review → BLOCK (sobre-escalación)

### 3.1 Fix: Change type classification (6 casos)

El classifier `classify_change_type()` retorna `unknown` para la mayoría de tareas nuevas. Fix:

```python
# En src/harnessci/diff/features.py
def classify_change_type(files, spec) -> ChangeType:
    # Regla 1: si hay archivos de API + spec menciona "add endpoint" → API_CHANGE
    # Regla 2: si todos los archivos son de test → TEST_ONLY
    # Regla 3: si hay archivos de config → CONFIG_CHANGE
    # Regla 4: si diff lines < 10 y spec dice "fix" → BUGFIX
    # Regla 5: si hay migrations → DATABASE_CHANGE
    # Regla 6: si toca archivos sensibles → SECURITY_SENSITIVE
    pass
```

Impacto: convertir 6 "unknown" → tipo correcto → +1 finding → escalación correcta.

### 3.2 Fix: Groq-based spec violation detection (4 casos)

El string matching actual (`oos in file_path`) no detecta violaciones conceptuales. Usar Groq:

```python
# En src/harnessci/spec/verifier.py
def _check_semantic_violations(spec, diff_files, llm_client):
    """Ask Groq: does this diff violate any of these out_of_scope constraints?"""
    prompt = f"""
    Spec out_of_scope: {spec.out_of_scope}
    Changed files: {[f.path for f in diff_files]}
    
    Does this change violate any out_of_scope constraint?
    Answer YES/NO with specific constraint name.
    """
    response = llm_client.complete(prompt)
    if "YES" in response:
        return [AuditFinding(...)]
    return []
```

Costo: ~$0.001 por PR (200 tokens Groq). Para 2000 PRs/mes: $2.

Impacto: +4 casos detectados → +13% strict_accuracy.

### 3.3 Fix: Entity invariant checking (3 casos de sobre-escalación)

Casos needs_review con 1 finding → BLOCK en vez de REVIEW_REQUIRED. Fix:

```python
# En src/harnessci/scoring/decision.py, adjust escalation:
# needs_review: 1 finding → REVIEW_REQUIRED (not BLOCK)
# unacceptable: 2+ findings OR any CRITICAL → BLOCK
```

Impacto: corregir 3 sobre-escalaciones.

### 3.4 Target posterior a fixes

| Métrica | Actual | Post-fix (estimado) |
|---|---|---|
| `strict_accuracy` | 0.5667 | 0.73-0.80 |
| `unsafe_detection_recall` | 0.60 | 0.80-0.85 |
| `unacceptable_block_recall` | 0.70 | 0.85-0.90 |
| `false_positive_review_rate` | 0.0 | 0.0 (mantener) |

---

## Roadmap temporal

| Semana | Acción | Gap |
|---|---|---|
| **Semana 1** (hecho) | Expandir Layer 2 a 1020 casos | #1 |
| | Fix change_type classifier | #3 |
| **Semana 2** | Fetch 500 diffs reales de GitHub | #1 |
| | Groq-based spec violation detection | #3 |
| **Semana 3** | Bootstrap confidence intervals | #1 |
| | Entity invariant checking fix | #3 |
| **Semana 4** | Ejecutar 30 agent runs reales | #2 |
| | Re-evaluar H3 con traces reales | #2 |
| **Semana 5** | Consolidar resultados finales | #1,2,3 |
| | Actualizar tesis con métricas finales | TFM |

---

## Presupuesto

| Item | Costo |
|---|---|
| Groq API (spec mining + violation detection) | ~$5 |
| GitHub API (tokens × 3, 500 diffs) | $0 (gratis) |
| Claude Code ejecuciones (10 × Sonnet 4) | ~$5 |
| Cursor + Copilot (incluido en sub) | $0 |
| **Total** | **~$10** |

---

## Claim final post-fixes

> *HarnessCI es el primer sistema de auditoría para PRs de agentes validado estadísticamente (strict_accuracy = 0.XX ± 0.0Y, 95% CI, n=600), con detección semántica de violaciones de especificación vía Groq, traces reales de agente confirmando H3, y el primer ranking público de seguridad de agentes — todo por ~$3/mes.*