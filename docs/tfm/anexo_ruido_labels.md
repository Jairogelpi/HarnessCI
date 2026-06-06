# Anexo: Ruido en labels de maintainer de Layer 3

## El problema

Layer 3 evalúa HarnessCI sobre 686 diffs reales de 5 agentes de IA, con la
decisión del maintainer como label proxy (`merged` / `closed`). Sin embargo,
esta etiqueta **no equivale a calidad técnica del código**.

## Causas de ruido

Un diff `closed` (PR cerrado sin merge) puede deberse a:

- **Prioridad o roadmap:** el cambio era técnicamente correcto pero no urgente.
- **PR duplicado:** otro contribuyente ya resolvió el mismo problema.
- **Abandono:** el autor no respondió a revisiones o el PR quedó olvidado.
- **Factor humano:** el maintainer拒绝了 por estilo personal, falta de
  familiaridad con el área, o sesgo inconsciente.
- **Cambio en requisitos:** el problema ya no aplica al estado actual del
  proyecto.

Un diff `merged` tampoco garantiza código perfecto:

- **PR mergeado con bugs:** ocurre en todos los proyectos reales.
- **PR mergeado por presión:** releases urgentes, cambios triviales sin revisión.
- **PR mergeado sin tests:** el revisor confió en el autor.

## Impacto en la evaluación

En Layer 3, el **split entre ACCEPTABLE y NEEDS_REVIEW es ~50/50** y las
features observadas en los diffs son prácticamente idénticas entre ambos
grupos. Esto produce un techo de ~52% en strict accuracy contra labels de
maintainer — no por fallo del detector, sino porque la variable dependiente
(labels) no es consistente con la variable que se quiere predecir (calidad
técnica).

## Mitigación

Por eso Layer 3 separa:

| Tipo | Métricas | Rol |
|---|---|---|
| **Diagnósticas externas** | M1, M5, M6 | Correlación con maintainer — informativa |
| **Primarias de revisión** | M2, M3, M4, M7 | Calidad técnica — defensible |

Las métricas primarias (M2 unsafe recall, M3 findings consistency, M4 false
block rate, M7 primary review composite) miden directamente lo que importa en
un sistema de revisión de código: detección de señales inseguras, consistencia
interna y control de falsos bloqueos.
