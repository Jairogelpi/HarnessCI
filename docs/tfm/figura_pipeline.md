# Pipeline de evaluación Layer 3 — HarnessCI

```mermaid
flowchart TD
    A["AIDev Dataset<br/>932.791 PRs, 11.152 repos"] --> B["Muestreo estratificado<br/>7.338 PRs, 5 agentes"]
    B --> C["Fetch de diffs<br/>711 diffs recuperados"]
    C --> D["Auditoría rules-only<br/>686 casos válidos<br/>~7s total"]

    D --> E["Pipeline de auditoría"]
    
    E --> F["Spec mining<br/>Groq Llama 3.1 8B"]
    E --> G["Reglas deterministas<br/>Forbidden paths, naming, capas"]
    E --> H["Análisis AST<br/>Null derefs, logic errors"]
    E --> I["LLM Refiner (opcional)<br/>Groq, ~0.43s/caso"]

    F --> J["Hallazgos estructurados<br/>severidad + categoría + evidencia"]
    G --> J
    H --> J
    I --> J

    J --> K["Decisión<br/>PASS / REVIEW / BLOCK"]
    K --> L["Evaluación multi-métrica"]

    L --> M1["M1 Escalation Correct Rate<br/>35.42% — diagnóstico externo"]
    L --> M2["M2 Unsafe Detection Recall<br/>81.14% ✅"]
    L --> M3["M3 Findings Consistency<br/>78.43% ✅"]
    L --> M4["M4 False Block Rate<br/>2.77% ✅"]
    L --> M7["M7 Primary Review Composite<br/>85.60% ✅"]

    style M2 fill:#1a6b1a,color:#fff
    style M3 fill:#1a6b1a,color:#fff
    style M4 fill:#1a6b1a,color:#fff
    style M7 fill:#1a6b1a,color:#fff
    style M1 fill:#6b1a1a,color:#fff
```

## Resultados clave

| Estrategia | Valor | Target |
|---|---|---|
| M2 Unsafe Detection Recall | **81.14%** | ✅ 75%+ |
| M3 Findings Consistency | **78.43%** | ✅ 75%+ |
| M4 False Block Rate | **2.77%** | ✅ <3% |
| M7 Primary Review Composite | **85.60%** | ✅ 75%+ |
| Approach 1 Primary Composite | **85.60%** | ✅ 75%+ |
| Approach 2 Primary Composite | **93.71%** | ✅ 75%+ |

## Ranking por agente

| Agente | n | Primary Composite |
|---|---|---:|
| Devin | 179 | **91.01%** |
| Cursor | 119 | **88.17%** |
| Claude_Code | 141 | **82.75%** |
| OpenAI_Codex | 130 | **82.33%** |
| Copilot | 117 | **81.00%** |
