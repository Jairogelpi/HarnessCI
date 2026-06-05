// All TFM content: numbers, text, structure

export const DATA = {
  title: "HarnessCI",
  subtitle: "Auditoría Determinista para Pull Requests\nGenerados por Inteligencia Artificial",
  author: "Jairo Gelpi",
  tutors: "Carlos Ortega · Santiago Mota",
  master: "Máster en Big Data, Business Analytics y Data Science",
  date: "Junio 2026",

  problem: {
    headline: "El Problema",
    lines: [
      "932.791 Pull Requests generados por IA en GitHub (2026)",
      "1.7× más issues de calidad que código humano",
      "75% más errores de lógica y corrección",
      "Herramientas existentes: ~50% falsos positivos",
      "Costo de herramientas líderes: hasta $960/mes",
    ],
  },

  solution: {
    headline: "HarnessCI: La Solución",
    lines: [
      "Pipeline híbrido: reglas deterministas + AST + LLM Groq",
      "Spec mining automático — deduce specs desde código sin configuración",
      "Detecta bugs genéricos: SQL injection, command injection," +
      " hardcoded secrets, XSS, race conditions",
      "Aprende de feedback del equipo — adapta thresholds automáticamente",
      "Soporte multi-plataforma: GitHub, GitLab, Bitbucket, Azure DevOps",
    ],
  },

  pipeline: {
    headline: "Arquitectura del Pipeline",
    stages: [
      { label: "REGLAS", desc: "Forbidden paths\nNaming conventions\nArchitecture layers", color: "accent" },
      { label: "AST", desc: "Null derefs\nLogic errors\nResource leaks", color: "accent2" },
      { label: "GROQ LLM", desc: "Valida hallazgos\nDescubre semantic bugs\nEscalación", color: "green2" },
      { label: "DECISIÓN", desc: "PASS\nREVIEW_REQUIRED\nBLOCK", color: "yellow" },
    ],
  },

  results: {
    headline: "Resultados Experimentales",
    layer2: {
      label: "Layer 2 — Benchmark Controlado",
      n: "1.020 casos",
      strictAcc: "98.33%",
      fp: "0.00%",
      recall: "100%",
      note: "Gold labels pre-asignados — zero falsos positivos",
    },
    layer3: {
      label: "Layer 3 — Diffs Reales",
      n: "686 diffs auditados",
      metrics: [
        { name: "Unsafe Detection Recall", value: "81.04%", bar: 0.81, target: "75%+" },
        { name: "Findings Consistency", value: "78.43%", bar: 0.78, target: "75%+" },
        { name: "Composite Score (Approach 2)", value: "88.08%", bar: 0.88, target: "75%+" },
        { name: "False Block Rate", value: "2.77%", bar: 0.03, target: "<3%" },
        { name: "Escalation Correct Rate", value: "70.41%", bar: 0.70, target: "75%+" },
      ],
    },
  },

  competitive: {
    headline: "Comparativa con la Competencia",
    items: [
      { label: "Falsos Positivos", codRabbit: "~50%", copilot: "~43%", harnessci: "0%", unit: "%" },
      { label: "Costo Mensual", codRabbit: "$960", copilot: "$760", harnessci: "$1", unit: "" },
      { label: "Spec Mining Automático", codRabbit: "❌", copilot: "❌", harnessci: "✅", unit: "" },
      { label: "Pipeline Híbrido", codRabbit: "❌", copilot: "❌", harnessci: "✅", unit: "" },
      { label: "Feedback Learning", codRabbit: "❌", copilot: "❌", harnessci: "✅", unit: "" },
    ],
  },

  agentRanking: {
    headline: "Ranking de Agentes por Seguridad",
    agents: [
      { name: "OpenAI Codex", score: "91.2", risk: "20.5", badge: "🟢 Safe" },
      { name: "Devin", score: "81.3", risk: "28.0", badge: "🟢 Safe" },
      { name: "Claude Code", score: "80.3", risk: "29.5", badge: "🟢 Safe" },
      { name: "GitHub Copilot", score: "79.0", risk: "29.6", badge: "🟡 Trusted" },
      { name: "Cursor", score: "71.2", risk: "34.6", badge: "🟡 Trusted" },
    ],
  },

  conclusions: {
    headline: "Conclusiones",
    points: [
      "0% falsos positivos en benchmark controlado (n=1.020)",
      "75%+ en 4 métricas independientes en diffs reales",
      "Costo 1.000× menor que la competencia ($1 vs $960/mes)",
      "Primer pipeline híbrido rules+AST+LLM del mercado",
      "Spec mining automático sin configuración manual",
    ],
  },
};
