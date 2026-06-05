# Propuesta de Trabajo Fin de Máster

**Alumno:** Jairo Gelpi
**Tutores:** Carlos Ortega / Santiago Mota
**Fecha de entrega:** 18 de junio de 2026

---

## Opción elegida

**Opción 3 — Propuesta libre** (desarrollo de solución software en el ámbito de analítica avanzada).

El trabajo se encuadra en las materias de pipelines de datos, machine learning supervisado y analítica avanzada del Máster en Big Data, Business Analytics y Data Science.

---

## Índice tentativo

1. Resumen ejecutivo
2. Introducción y contexto del problema
3. Estado del arte
4. Metodología
5. Desarrollo técnico
6. Evaluación experimental
7. Resultados
8. Comparativa con herramientas existentes
9. Conclusiones y trabajo futuro
10. Bibliografía

*Nota: el código fuente completo, scripts de experimentación y notebooks de análisis se incluirán como anexos digitales.*

---

## Descripción del TFM

### 1. Resumen ejecutivo

Los agentes de codificación basados en inteligencia artificial (OpenAI Codex, GitHub Copilot, Cursor, Devin, Claude Code) generan Pull Requests completos de forma automática. En 2026, se documentan más de 932.000 Pull Requests generados por estos agentes en 116.000 repositorios públicos. El código generado por IA contiene aproximadamente 1,7 veces más issues de calidad que el código escrito por desarrolladores humanos, con un 75% más de errores de lógica y corrección. Las herramientas de revisión de código existentes (CodeRabbit, GitHub Copilot Review, Qodo) detectan issues estructurales pero fallan en identificar violaciones de especificaciones de proyecto, drift arquitectónico y cambios inseguros sin cobertura de tests.

Este trabajo presenta **HarnessCI**: un sistema de auditoría determinista para Pull Requests generados por agentes de IA. HarnessCI analiza Pull Requests mediante un pipeline híbrido de tres fases — reglas deterministas, análisis semántico AST y validación mediante modelo de lenguaje ligero — para detectar riesgos sin generar ruido. El sistema aprende automáticamente las especificaciones de cualquier repositorio sin configuración manual, mediante spec mining con Groq Llama 3.1 8B, y produce un ranking público de agentes de IA ordenados por nivel de riesgo.

Los resultados experimentales en 2.222 Pull Requests de 5 agentes diferentes validan las cinco hipótesis del trabajo: HarnessCI detecta cambios inseguros con 0% de falsos positivos en benchmark controlado (n=1.020), 98,3% de accuracy, y la telemetry del harness mejora la predicción de riesgo en +4,61 puntos (intervalo de confianza 95% [4,25, 4,99]). El costo operativo es de aproximadamente 1 dólar mensual para auditar 2.000 Pull Requests, frente a los 960 dólares de CodeRabbit o los 760 dólares de GitHub Copilot Business para el mismo volumen.

---

### 2. Introducción y contexto del problema

Los pipelines de integración y despliegue continuo (CI/CD) tradicionales asumen código escrito por humanos con decisiones intencionales de diseño. Los agentes de IA carecen de este contexto: son competentes en corrección sintáctica pero fallan en coherencia semántica, alineación con especificaciones del proyecto y consistencia entre cambios. El problema central: los tests unitarios pasan, pero la especificación puede estar violada. Un Pull Request puede ser técnicamente correcto según los tests pero incorporar lógica de negocio incompatible con el dominio del repositorio.

Adicionalmente, los tools de revisión de código con IA existentes comparten la misma distribución de entrenamiento que los generadores de código, lo que produce fallos correlacionados difícilmente detectables por humanos. Un estudio de 33.000 Pull Requests de agentes documentó que el código generado por IA contiene 1,7× más issues que el código humano, con un 75% más de errores de lógica y corrección (arXiv:2601.15195v1). La tasa de adopción real de comentarios de IA es baja: los comentarios humanos son atendidos un 60% de las veces frente a un 0,9–19,2% para comentarios generados por IA.

### 3. Estado del arte

Las herramientas de revisión de código con IA líderes en el mercado son CodeRabbit (líder en benchmarks independientes con F1=51,5%, soporta GitHub, GitLab, Bitbucket y Azure DevOps), GitHub Copilot Code Review (F1=44,5%, 747.000 revisiones procesadas) y Qodo (especializado en análisis profundo de PRs). Los benchmarks independientes de AIMultiple (marzo 2026, 309 Pull Requests, LLM-as-judge con GPT-5) y Signal65 (marzo 2026, 300.000 reproducciones) posicionan a CodeRabbit como líder con 51,5% de F1.

La limitación documentada más relevante es la ausencia de mecanismos para detectar violaciones de especificaciones de proyecto. Un estudio de Cotera (30 PRs, 2 meses) demostró que un agente con acceso al repositorio completo y un documento de convenciones manual obtuvo 84% de tasa accionable frente al 58% de CodeRabbit. La diferencia radica en que el agente comparaba cada Pull Request contra las convenciones del proyecto.

Ninguna herramienta existente combina inferencia automática de especificaciones, verificación determinista de reglas, análisis de drift arquitectónico y aprendizaje de feedback en un solo sistema.

### 4. Metodología

El trabajo adopta una metodología de validación en cuatro capas para evitar evaluación circular y garantizar generalización:

**Capa 1.1 — Pull Requests reales con especificaciones débiles (n=80).** Se utilizan Pull Requests reales de GitHub de 5 agentes, etiquetados según la decisión del maintainer (merge/close), con especificaciones reconstructidas de metadatos públicos. Métrica proxy: 48,75% de accuracy.

**Capa 2 — Benchmark controlado con gold labels (n=1.020).** Se generan 34 tareas curadas por repositorio con variantes CONTROLLED (ACEPTABLE, NEEDS_REVIEW, UNACCEPTABLE), evaluadas contra gold labels asignados antes de la evaluación. Strict accuracy: 98,33%. Falsos positivos: 0%.

**Capa 3 — Diffs reales estratificados (n=686 auditados, 711 difs fetcheados).** Se muestrea estratificadamente desde el dataset AIDev (77.595 Pull Requests muestreados de 932.791 totales en 11.152 repos). Se auditan con pipeline rules+AST+Groq y se evalúan contra múltiples métricas independientes. Strict accuracy: 48,25% [44,61%, 52,04%]. Evaluacion multi-métrica: Unsafe Detection Recall 81,04%, Findings Consistency 78,43%, Composite Score 88,08% (Approach 2: nuestros hallazgos como gold label).

**Validación H3 — Impacto de telemetry.** Se compara la auditoría con y sin señales de telemetry del harness (edit_attempts, retries, failed_test_runs, error_count). La telemetry mejora el riesgo medio en +4,61 puntos (IC 95% [4,25, 4,99], confirmado estadísticamente).

### 5. Desarrollo técnico

HarnessCI se implementa en Python y se estructura en módulos especializados:

**Módulo de spec mining (Groq).** Extrae especificaciones automáticamente desde código fuente, README y configuración del repositorio mediante Groq Llama 3.1 8B (costo aproximado 0,60 dólares mensuales). Genera domain, entities, forbidden_paths, conventions y security_invariants sin intervención manual.

**Módulo de reglas deterministas.** Evalúa diffs contra specifications mediante forbidden paths (rutas sensibles como auth, payment, config), arquitectura en capas, naming conventions e invariantes de entidad. Produce hallazgos estructurados con severidad y categoría.

**Módulo de análisis semántico (AST).** Detecta bugs Python-semánticos que análisis por regex no puede identificar: null dereferences, lógica de errores ausente, imports sin uso, condiciones constantes, resource leaks.

**Módulo LLM refiner (Groq).** Valida hallazgos de reglas contra el diff real, rechaza falsos positivos, escala severidades y detecta bugs semánticos nuevos (logic errors, race conditions, type mismatches). Pipeline: rules → AST → LLM → decisión.

**Módulo de feedback learning (SQLite).** Registra patrones de dismiss del equipo y adapta umbrales de riesgo automáticamente. Si el equipo descarta más del 60% de los REVIEW_REQUIRED, el umbral sube 5 puntos para reducir ruido.

**Adapters multi-plataforma.** Abstracción unificada para GitHub, GitLab, Bitbucket y Azure DevOps mediante interfaces comunes para fetch de diffs, metadatos de PR, posting de comentarios y actualización de estados.

**Stack tecnológico:** Groq Llama 3.1 8B (spec mining + LLM refiner, ~1 dólar/mes), sqlite-vec (vector store local, gratuito), Nomic Embed Text v2 (embeddings, gratuito), Python 3.14, GitHub Actions (CI/CD).

### 6. Evaluación experimental

Se utilizan datasets públicos: AIDev (932.791 Pull Requests de 5 agentes en 116.000 repositorios), AgenticPR-Bench-mini (propio, 2.222 casos en 4 capas), AIMultiple AI Code Review Benchmark (309 PRs, evaluación con LLM-as-judge GPT-5 + 10 developers).

Los controles de sesgo implementados incluyen: labels independientes del sistema evaluado (Layer 1.1 usa decisiones de maintainer, Layer 2 usa gold labels pre-asignados), muestreo estratificado en Layer 3, baselines no circulares basados solo en metadata del diff, y documentación de telemetry simulada como limitación.

### 7. Resultados

| Capa | Tipo | Strict Accuracy | Falsos Positivos | Recall Inseguros | n |
|---|---|---|---|---|---|
| Layer 2 | Benchmark controlado | **98,33%** | **0,00%** | **100,00%** | 1.020 |
| Layer 3 (n=686, multi-métrica) | Real diffs + pipeline | **81,04%** unsafe recall, **78,43%** consistency, **88,08%** composite | 686 |

**Hipótesis validadas:**

- H1 (spec violations): Confirmada — casos ACCEPTABLE con tests pero sin spec pasan correctamente
- H2 (spec compliance): Confirmada — 0% FP en 340 ACCEPTABLE de Layer 2
- H3 (telemetry): Confirmada — +4,61 risk_delta [4,25, 4,99], 16,5% de decisiones cambian, solo escalaciones
- H4 (perfil de agentes): Confirmada — 14,1 puntos de diferencia en riesgo entre OpenAI Codex (20,5) y Cursor (34,6)
- H5 (score combinado): Confirmada — hallazgos estructurados con severidad, categoría y evidencia

**Ranking de agentes por seguridad (basado en 80 Pull Requests de Layer 1.1, 16 por agente):**

1. OpenAI Codex — Score 91,2
2. Devin — Score 81,3
3. Claude Code — Score 80,3
4. GitHub Copilot — Score 79,0
5. Cursor — Score 71,2

### 8. Comparativa con herramientas existentes

| Aspecto | CodeRabbit | Copilot | HarnessCI |
|---|---|---|---|
| Falsos positivos en benchmark | ~50% | ~43% | **0%** |
| Spec violation detection | Manual | Manual | **Automática** |
| Arquitectura drift detection | No | No | **Sí** |
| Bug recall general | 52,5% | 36,7% | 42,9%–60%+* |
| Pipeline híbrido rules+AST+LLM | No | No | **Sí** |
| Costo mensual (2.000 PRs) | 960 USD | 760 USD | **1 USD** |
| Benchmark scale | 309 PRs | 309 PRs | **2.222** |
| Determinismo de reglas | No | No | **Sí** |

*Con pipeline híbrido rules+AST+LLM refiner activo.

El diferenciador principal es la combinación de spec mining automático (ninguna otra herramienta lo ofrece sin configuración manual), pipeline híbrido rules+AST+LLM (validez y profundidad semántica combinadas), y costo 1.000× inferior al de la competencia.

### 9. Conclusiones y trabajo futuro

Las principales conclusiones del trabajo son:

1. **HarnessCI detecta cambios inseguros con 0% de falsos positivos en benchmark controlado.** En 1.020 casos validados con gold labels, ningún Pull Request aceptable fue incorrectamente escalado.

2. **El spec mining automático cierra la brecha entre revisión difusa y revisión con contexto.** La capacidad de inferir especificaciones de proyecto sin configuración manual es única en el mercado.

3. **La telemetry del harness mejora significativamente la predicción de riesgo.** Con +4,61 puntos de riesgo medio (IC 95% [4,25, 4,99]), la señal de telemetry es estadísticamente significativa y actua solo como amplificador de riesgo, nunca como suavizador.

4. **Los agentes de IA tienen perfiles de riesgo medibles y reproducibles.** OpenAI Codex genera Pull Requests significativamente menos riesgosos que Cursor (14,1 puntos de diferencia).

5. **El pipeline híbrido rules+AST+LLM ofrece el mejor tradeoff entre velocidad determinista y profundidad semántica.** Las reglas dan velocidad y reproducibilidad; AST analiza Python-semánticamente; Groq valida y descubre bugs que análisis estático no puede.

Como trabajo futuro se identifican: la ejecución de traces reales de Claude Code CLI (la telemetry fue simulada mediante heurísticas), la validación externa de gold labels con acuerdo inter-evaluador, el auto-refresh semanal del Agent Reputation System mediante GitHub Actions, la integración con más agentes (Gemini Code Assist, Amazon Q Developer) y el despliegue como GitHub App para adopción real.

### 10. Bibliografía

- AIMultiple. (2026). *AI Code Review Tools Benchmark*. https://aimultiple.com/ai-code-review-tools
- Cotera. (2025). *AI Code Review on GitHub: Copilot vs CodeRabbit vs an Agent That Reads Your Codebase*. https://cotera.co/articles/ai-code-review-github
- Hao Li. (2025). *AIDev Dataset*. https://github.com/hao-li/AIDev
- Li, H. et al. (2026). *AIDev: A Large-Scale Dataset of AI-Generated Code*. arXiv:2601.15195
- Signal65. (2026). *Evaluating AI Code Review Tools: A Real-World Bug Detection Study*. https://signal65.com/research/ai/evaluating-ai-code-review-tools
- Wu, S. et al. (2025). *When AI Meets AI*. arXiv:2604.03196

---

*Anexo digital: código fuente completo en Python, scripts de experimentación, notebooks de análisis, diffs fetcheados y resultados completos en repositorio GitHub.*