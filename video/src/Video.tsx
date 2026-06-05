import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  AbsoluteFill,
  Sequence,
} from "remotion";
import { colors, FPS } from "./theme";
import { DATA } from "./data";

// ── Helpers ──────────────────────────────────────────────────────────────
const fadeIn = (frames: number, fps: number) =>
  interpolate(frames, [0, 1.5 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const slideUp = (frames: number, fps: number, delay = 0) =>
  interpolate(Math.max(0, frames - delay), [0, fps], [40, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

const scaleIn = (frames: number, fps: number, delay = 0) =>
  interpolate(Math.max(0, frames - delay), [0, fps], [0.85, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

const delay = (n: number) => n * FPS;

// ── Background ────────────────────────────────────────────────────────────

// ── Slide wrapper ────────────────────────────────────────────────────────
const Slide = ({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) => (
  <AbsoluteFill style={{ background: colors.bg, padding: "80px", ...style }}>
    {children}
  </AbsoluteFill>
);

// ── Title slide ──────────────────────────────────────────────────────────
const TitleSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = fadeIn(frame, fps);
  const titleY = slideUp(frame, fps);
  const subtitleY = slideUp(frame, fps, delay(2));
  const subtitleOpacity = fadeIn(Math.max(0, frame - delay(2)), fps);
  const metaOpacity = fadeIn(Math.max(0, frame - delay(4)), fps);

  return (
    <Slide>
      {/* Gradient accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "12px",
          height: "100%",
          background: `linear-gradient(to bottom, ${colors.accent}, ${colors.green})`,
          opacity: titleOpacity,
        }}
      />

      {/* Logo / Title */}
      <div
        style={{
          position: "absolute",
          top: "15%",
          left: "50%",
          transform: `translateX(-50%) translateY(${titleY}px)`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: "Arial Black, Arial, sans-serif",
            fontSize: "140px",
            fontWeight: 900,
            color: colors.white,
            letterSpacing: "-4px",
            opacity: titleOpacity,
          }}
        >
          HarnessCI
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "28px",
            color: colors.accent,
            marginTop: "12px",
            fontWeight: 600,
            letterSpacing: "4px",
            opacity: titleOpacity,
          }}
        >
          AUDITORÍA DETERMINISTA
        </div>
      </div>

      {/* Subtitle */}
      <div
        style={{
          position: "absolute",
          top: "52%",
          left: "50%",
          transform: `translateX(-50%) translateY(${subtitleY}px)`,
          textAlign: "center",
          width: "75%",
          opacity: subtitleOpacity,
        }}
      >
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "34px",
            color: colors.gray1,
            lineHeight: 1.5,
          }}
        >
          para Pull Requests generados por Inteligencia Artificial
        </div>
      </div>

      {/* Meta info */}
      <div
        style={{
          position: "absolute",
          bottom: "15%",
          left: "50%",
          transform: "translateX(-50%)",
          textAlign: "center",
          opacity: metaOpacity,
        }}
      >
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "22px",
            color: colors.gray2,
            marginBottom: "8px",
          }}
        >
          {DATA.author} · {DATA.tutors}
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "18px",
            color: colors.gray3,
          }}
        >
          {DATA.master}
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "18px",
            color: colors.accent,
            marginTop: "8px",
          }}
        >
          {DATA.date}
        </div>
      </div>

      {/* Decorative circuit lines */}
      <svg
        style={{ position: "absolute", bottom: 0, right: 0, opacity: 0.08 }}
        width="600"
        height="400"
        viewBox="0 0 600 400"
      >
        <path
          d="M0 200 L150 200 L200 150 L400 150 L450 200 L600 200 M200 150 L200 350 L600 350"
          stroke={colors.accent}
          strokeWidth="2"
          fill="none"
        />
        <circle cx="200" cy="150" r="6" fill={colors.accent} />
        <circle cx="400" cy="150" r="6" fill={colors.accent} />
        <circle cx="600" cy="200" r="6" fill={colors.accent} />
        <circle cx="200" cy="350" r="6" fill={colors.accent} />
        <circle cx="600" cy="350" r="6" fill={colors.accent} />
      </svg>
    </Slide>
  );
};

// ── Problem slide ────────────────────────────────────────────────────────
const ProblemSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);
  const linesOpacity = fadeIn(Math.max(0, frame - delay(2)), fps);

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        {/* Header */}
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.red,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.problem.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.red,
            marginBottom: "60px",
            opacity: headOpacity,
          }}
        />

        {/* Stats row */}
        <div
          style={{
            display: "flex",
            gap: "32px",
            marginBottom: "60px",
            opacity: linesOpacity,
          }}
        >
          {[
            { num: "932K", label: "PRs generados\npor IA" },
            { num: "1.7×", label: "más issues que\ncódigo humano" },
            { num: "75%", label: "más errores de\nlógica" },
          ].map((s, i) => (
            <div
              key={i}
              style={{
                background: colors.surface,
                border: `1px solid ${colors.border}`,
                borderRadius: "12px",
                padding: "28px 36px",
                textAlign: "center",
                flex: 1,
              }}
            >
              <div
                style={{
                  fontFamily: "Arial Black, Arial, sans-serif",
                  fontSize: "64px",
                  color: colors.red,
                  fontWeight: 900,
                }}
              >
                {s.num}
              </div>
              <div
                style={{
                  fontFamily: "Arial, sans-serif",
                  fontSize: "16px",
                  color: colors.gray2,
                  marginTop: "8px",
                  whiteSpace: "pre-line",
                }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>

        {/* Bullet points */}
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {DATA.problem.lines.map((line, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "20px",
                opacity: interpolate(linesOpacity, [0, 1], [0, 1]),
                transform: `translateY(${slideUp(Math.max(0, frame - delay(3 + i * 1.5)), fps * 0.5)}px)`,
              }}
            >
              <div
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "50%",
                  background: colors.red,
                  flexShrink: 0,
                }}
              />
              <div
                style={{
                  fontFamily: "Arial, sans-serif",
                  fontSize: "24px",
                  color: colors.gray1,
                }}
              >
                {line}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Slide>
  );
};

// ── Solution slide ───────────────────────────────────────────────────────
const SolutionSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const items = DATA.solution.lines;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.green,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.solution.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.green,
            marginBottom: "60px",
            opacity: headOpacity,
          }}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
          {items.map((line, i) => {
            const itemOpacity = fadeIn(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            const itemY = slideUp(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "20px",
                  opacity: itemOpacity,
                  transform: `translateY(${itemY}px)`,
                }}
              >
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    background: colors.green2,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <span style={{ color: colors.white, fontSize: "20px", fontWeight: 700 }}>
                    {i + 1}
                  </span>
                </div>
                <div
                  style={{
                    fontFamily: "Arial, sans-serif",
                    fontSize: "24px",
                    color: colors.gray1,
                    borderLeft: `3px solid ${colors.green}`,
                    paddingLeft: "20px",
                  }}
                >
                  {line}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Slide>
  );
};

// ── Pipeline / Architecture slide ────────────────────────────────────────
const PipelineSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const stages = DATA.pipeline.stages;
  const stageWidth = 340;
  const arrowWidth = 80;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.accent,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.pipeline.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.accent,
            marginBottom: "80px",
            opacity: headOpacity,
          }}
        />

        {/* Pipeline stages */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 0,
          }}
        >
          {stages.map((stage, i) => {
            const stageOpacity = fadeIn(Math.max(0, frame - delay(2 + i * 2)), fps);
            const stageY = slideUp(Math.max(0, frame - delay(2 + i * 2)), fps);
            const stageScale = scaleIn(Math.max(0, frame - delay(2 + i * 2)), fps);
            const color = colors[stage.color as keyof typeof colors];

            return (
              <div key={i} style={{ display: "flex", alignItems: "center" }}>
                {/* Stage box */}
                <div
                  style={{
                    width: `${stageWidth}px`,
                    opacity: stageOpacity,
                    transform: `translateY(${stageY}px) scale(${stageScale})`,
                  }}
                >
                  <div
                    style={{
                      background: colors.surface,
                      border: `2px solid ${color}`,
                      borderRadius: "16px",
                      padding: "32px 24px",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "Arial, sans-serif",
                        fontSize: "36px",
                        fontWeight: 900,
                        color,
                        marginBottom: "16px",
                        letterSpacing: "2px",
                      }}
                    >
                      {stage.label}
                    </div>
                    {stage.desc.split("\n").map((d, j) => (
                      <div
                        key={j}
                        style={{
                          fontFamily: "Courier New, monospace",
                          fontSize: "15px",
                          color: colors.gray2,
                          marginBottom: "6px",
                        }}
                      >
                        → {d}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Arrow */}
                {i < stages.length - 1 && (
                  <div
                    style={{
                      width: `${arrowWidth}px`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      opacity: fadeIn(Math.max(0, frame - delay(3 + i * 2)), fps),
                    }}
                  >
                    <svg width={arrowWidth} height="24" viewBox="0 0 80 24">
                      <line
                        x1="0" y1="12" x2="60" y2="12"
                        stroke={colors.accent}
                        strokeWidth="2"
                      />
                      <polygon
                        points="60,4 80,12 60,20"
                        fill={colors.accent}
                      />
                    </svg>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Cost badge */}
        <div
          style={{
            marginTop: "80px",
            textAlign: "center",
            opacity: fadeIn(Math.max(0, frame - delay(10)), fps),
          }}
        >
          <span
            style={{
              background: colors.green2,
              borderRadius: "999px",
              padding: "16px 40px",
              fontFamily: "Arial, sans-serif",
              fontSize: "28px",
              color: colors.white,
              fontWeight: 700,
            }}
          >
            💰 Costo operativo: ~$1/mes para 2.000 PRs
          </span>
        </div>
      </div>
    </Slide>
  );
};

// ── Results Layer 2 slide ────────────────────────────────────────────────
const ResultsL2Slide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const metrics = [
    { label: "Strict Accuracy", value: DATA.results.layer2.strictAcc, color: colors.green },
    { label: "Falsos Positivos", value: DATA.results.layer2.fp, color: colors.green },
    { label: "Unsafe Recall", value: DATA.results.layer2.recall, color: colors.green },
  ];

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.green,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.results.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.green,
            marginBottom: "20px",
            opacity: headOpacity,
          }}
        />

        {/* Layer 2 badge */}
        <div
          style={{
            display: "inline-block",
            background: colors.green2,
            borderRadius: "8px",
            padding: "10px 24px",
            marginBottom: "40px",
            opacity: fadeIn(Math.max(0, frame - delay(2)), fps),
          }}
        >
          <span
            style={{
              fontFamily: "Arial, sans-serif",
              fontSize: "22px",
              fontWeight: 700,
              color: colors.white,
            }}
          >
            {DATA.results.layer2.label}
          </span>
          <span
            style={{
              fontFamily: "Courier New, monospace",
              fontSize: "18px",
              color: colors.gray1,
              marginLeft: "16px",
            }}
          >
            {DATA.results.layer2.n}
          </span>
        </div>

        {/* Big metrics */}
        <div
          style={{
            display: "flex",
            gap: "40px",
            marginBottom: "40px",
          }}
        >
          {metrics.map((m, i) => {
            const op = fadeIn(Math.max(0, frame - delay(3 + i * 1.5)), fps);
            const sc = scaleIn(Math.max(0, frame - delay(3 + i * 1.5)), fps);
            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  background: colors.surface,
                  border: `2px solid ${m.color}`,
                  borderRadius: "16px",
                  padding: "40px 32px",
                  textAlign: "center",
                  opacity: op,
                  transform: `scale(${sc})`,
                }}
              >
                <div
                  style={{
                    fontFamily: "Arial Black, Arial, sans-serif",
                    fontSize: "96px",
                    fontWeight: 900,
                    color: m.color,
                  }}
                >
                  {m.value}
                </div>
                <div
                  style={{
                    fontFamily: "Arial, sans-serif",
                    fontSize: "22px",
                    color: colors.gray2,
                    marginTop: "8px",
                  }}
                >
                  {m.label}
                </div>
              </div>
            );
          })}
        </div>

        {/* Note */}
        <div
          style={{
            fontFamily: "Courier New, monospace",
            fontSize: "20px",
            color: colors.gray3,
            opacity: fadeIn(Math.max(0, frame - delay(8)), fps),
          }}
        >
          # {DATA.results.layer2.note}
        </div>

        {/* Comparison bar */}
        <div
          style={{
            marginTop: "40px",
            opacity: fadeIn(Math.max(0, frame - delay(9)), fps),
          }}
        >
          <div
            style={{
              fontFamily: "Arial, sans-serif",
              fontSize: "18px",
              color: colors.gray2,
              marginBottom: "12px",
            }}
          >
            vs CodeRabbit (benchmark AIMultiple Mar 2026): F1=51.5%, FP≈50%
          </div>
          <div style={{ display: "flex", height: "40px", gap: "8px" }}>
            <div
              style={{
                background: colors.green,
                borderRadius: "8px",
                width: "98.33%",
                display: "flex",
                alignItems: "center",
                paddingLeft: "16px",
                fontFamily: "Arial, sans-serif",
                fontSize: "14px",
                color: colors.white,
                fontWeight: 700,
              }}
            >
              HarnessCI 98.33%
            </div>
          </div>
        </div>
      </div>
    </Slide>
  );
};

// ── Results Layer 3 Multi-metric slide ──────────────────────────────────
const ResultsL3Slide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const metrics = DATA.results.layer3.metrics;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.accent,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.results.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.accent,
            marginBottom: "12px",
            opacity: headOpacity,
          }}
        />

        {/* Layer 3 badge */}
        <div
          style={{
            display: "inline-block",
            background: colors.accent2,
            borderRadius: "8px",
            padding: "10px 24px",
            marginBottom: "40px",
            opacity: fadeIn(Math.max(0, frame - delay(2)), fps),
          }}
        >
          <span
            style={{
              fontFamily: "Arial, sans-serif",
              fontSize: "22px",
              fontWeight: 700,
              color: colors.white,
            }}
          >
            {DATA.results.layer3.label}
          </span>
        </div>

        {/* Metric bars */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {metrics.map((m, i) => {
            const op = fadeIn(Math.max(0, frame - delay(3 + i * 1.5)), fps);
            const barWidth = interpolate(
              Math.max(0, frame - delay(3 + i * 1.5 + 1)),
              [0, fps * 2],
              [0, m.bar * 100],
              { extrapolateLeft: "clamp", easing: Easing.out(Easing.cubic) }
            );
            const isGood = m.name.includes("Block") ? m.bar < 0.05 : m.bar >= 0.75;
            const barColor = isGood ? colors.green : m.bar >= 0.65 ? colors.yellow : colors.red;

            return (
              <div key={i} style={{ opacity: op }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: "6px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "Arial, sans-serif",
                      fontSize: "18px",
                      color: colors.gray1,
                    }}
                  >
                    {m.name}
                  </span>
                  <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
                    <span
                      style={{
                        fontFamily: "Arial Black, Arial, sans-serif",
                        fontSize: "22px",
                        color: barColor,
                        fontWeight: 900,
                      }}
                    >
                      {m.value}
                    </span>
                    <span
                      style={{
                        fontFamily: "Courier New, monospace",
                        fontSize: "14px",
                        color: isGood ? colors.green : colors.gray3,
                        background: isGood ? `${colors.green}22` : colors.surface,
                        borderRadius: "4px",
                        padding: "2px 8px",
                      }}
                    >
                      {m.target}
                    </span>
                  </div>
                </div>
                {/* Bar */}
                <div
                  style={{
                    height: "20px",
                    background: colors.surface,
                    borderRadius: "10px",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${barWidth}%`,
                      background: barColor,
                      borderRadius: "10px",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Key insight */}
        <div
          style={{
            marginTop: "40px",
            background: colors.surface,
            border: `1px solid ${colors.green}`,
            borderRadius: "12px",
            padding: "20px 28px",
            opacity: fadeIn(Math.max(0, frame - delay(12)), fps),
          }}
        >
          <div
            style={{
              fontFamily: "Arial, sans-serif",
              fontSize: "18px",
              color: colors.green,
              fontWeight: 700,
              marginBottom: "8px",
            }}
          >
            💡 Clave
          </div>
          <div
            style={{
              fontFamily: "Courier New, monospace",
              fontSize: "15px",
              color: colors.gray2,
            }}
          >
            El teto de ~52% en strict_accuracy se explica por labels de
            maintainer ruidosos (~50/50 aleatorio).
            <br />
            Evaluado contra criterios propios, HarnessCI supera 75%+ en 4 métricas.
          </div>
        </div>
      </div>
    </Slide>
  );
};

// ── Competitive slide ────────────────────────────────────────────────────
const CompetitiveSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const items = DATA.competitive.items;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.yellow,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.competitive.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.yellow,
            marginBottom: "40px",
            opacity: headOpacity,
          }}
        />

        {/* Table */}
        <div>
          {/* Header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "2fr 1fr 1fr 1fr",
              gap: "0",
              marginBottom: "4px",
            }}
          >
            {["Aspecto", "CodeRabbit", "Copilot", "HarnessCI"].map((h, i) => (
              <div
                key={i}
                style={{
                  fontFamily: "Arial, sans-serif",
                  fontSize: "16px",
                  fontWeight: 700,
                  color: colors.gray2,
                  padding: "8px 16px",
                  textAlign: i === 0 ? "left" : "center",
                }}
              >
                {h}
              </div>
            ))}
          </div>

          {items.map((row, i) => {
            const op = fadeIn(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            const isHarnessciWin =
              row.label.includes("Costo") ||
              row.label.includes("Spec") ||
              row.label.includes("Pipeline") ||
              row.label.includes("Feedback");
            const harnessciColor = isHarnessciWin ? colors.green : colors.accent;

            return (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 1fr 1fr 1fr",
                  gap: "0",
                  background: colors.surface,
                  borderRadius: "8px",
                  marginBottom: "8px",
                  opacity: op,
                  border: `1px solid ${i % 2 === 0 ? colors.border : "transparent"}`,
                }}
              >
                {[
                  row.label,
                  row.codRabbit,
                  row.copilot,
                  row.harnessci,
                ].map((cell, j) => (
                  <div
                    key={j}
                    style={{
                      fontFamily: "Courier New, monospace",
                      color: j === 3 ? harnessciColor : colors.gray1,
                      fontWeight: j === 3 && isHarnessciWin ? 700 : 400,
                      padding: "16px 16px",
                      textAlign: j === 0 ? "left" : "center",
                      fontSize: j === 0 ? "17px" : "20px",
                    }}
                  >
                    {cell}
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {/* Bottom note */}
        <div
          style={{
            marginTop: "40px",
            textAlign: "center",
            opacity: fadeIn(Math.max(0, frame - delay(10)), fps),
          }}
        >
          <div
            style={{
              fontFamily: "Arial, sans-serif",
              fontSize: "28px",
              color: colors.green,
              fontWeight: 700,
            }}
          >
            1.000× más barato · 0% FP vs ~50% FP
          </div>
        </div>
      </div>
    </Slide>
  );
};

// ── Agent Ranking slide ─────────────────────────────────────────────────
const RankingSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const agents = DATA.agentRanking.agents;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.accent,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.agentRanking.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.accent,
            marginBottom: "50px",
            opacity: headOpacity,
          }}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {agents.map((agent, i) => {
            const op = fadeIn(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            const xOff = slideUp(Math.max(0, frame - delay(2 + i * 1.5)), fps * 0.3);
            const barWidth = interpolate(
              Math.max(0, frame - delay(3 + i * 1.5)),
              [0, fps * 2],
              [0, (parseFloat(agent.score) / 100) * 100],
              { extrapolateLeft: "clamp", easing: Easing.out(Easing.cubic) }
            );

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "20px",
                  opacity: op,
                  transform: `translateX(${xOff}px)`,
                }}
              >
                {/* Rank */}
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    background:
                      i === 0
                        ? colors.yellow
                        : i < 3
                        ? colors.gray4
                        : colors.gray4,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "Arial Black, Arial, sans-serif",
                    fontSize: "22px",
                    color: colors.white,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </div>

                {/* Name */}
                <div
                  style={{
                    width: "220px",
                    fontFamily: "Arial, sans-serif",
                    fontSize: "22px",
                    color: colors.gray1,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {agent.name}
                </div>

                {/* Bar */}
                <div
                  style={{
                    flex: 1,
                    height: "36px",
                    background: colors.surface,
                    borderRadius: "8px",
                    overflow: "hidden",
                    border: `1px solid ${colors.border}`,
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${barWidth}%`,
                      background:
                        i === 0
                          ? colors.green
                          : i < 3
                          ? colors.green2
                          : colors.accent2,
                      borderRadius: "8px",
                      display: "flex",
                      alignItems: "center",
                      paddingLeft: "12px",
                      fontFamily: "Arial Black, Arial, sans-serif",
                      fontSize: "18px",
                      color: colors.white,
                    }}
                  >
                    {agent.score}
                  </div>
                </div>

                {/* Risk */}
                <div
                  style={{
                    fontFamily: "Courier New, monospace",
                    fontSize: "18px",
                    color: colors.gray3,
                    width: "100px",
                    textAlign: "right",
                    flexShrink: 0,
                  }}
                >
                  risk {agent.risk}
                </div>

                {/* Badge */}
                <div
                  style={{
                    fontFamily: "Arial, sans-serif",
                    fontSize: "15px",
                    color: i < 3 ? colors.green : colors.yellow,
                    width: "80px",
                    flexShrink: 0,
                  }}
                >
                  {agent.badge}
                </div>
              </div>
            );
          })}
        </div>

        <div
          style={{
            marginTop: "50px",
            textAlign: "center",
            opacity: fadeIn(Math.max(0, frame - delay(10)), fps),
          }}
        >
          <div
            style={{
              fontFamily: "Courier New, monospace",
              fontSize: "18px",
              color: colors.gray3,
            }}
          >
            * Basado en 80 PRs auditados de Layer 1.1 — resultados direccionales
          </div>
        </div>
      </div>
    </Slide>
  );
};

// ── Conclusions slide ────────────────────────────────────────────────────
const ConclusionsSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const headOpacity = fadeIn(frame, fps);
  const headY = slideUp(frame, fps);

  const points = DATA.conclusions.points;

  return (
    <Slide>
      <div style={{ position: "absolute", top: 60, left: 80, right: 80 }}>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "52px",
            fontWeight: 700,
            color: colors.white,
            marginBottom: "8px",
            opacity: headOpacity,
            transform: `translateY(${headY}px)`,
          }}
        >
          {DATA.conclusions.headline}
        </div>
        <div
          style={{
            width: "80px",
            height: "4px",
            background: colors.white,
            marginBottom: "60px",
            opacity: headOpacity,
          }}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: "32px" }}>
          {points.map((point, i) => {
            const op = fadeIn(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            const sc = scaleIn(Math.max(0, frame - delay(2 + i * 1.5)), fps);
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "24px",
                  opacity: op,
                  transform: `scale(${sc})`,
                }}
              >
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "12px",
                    background: colors.green2,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <span style={{ color: colors.white, fontSize: "22px" }}>✓</span>
                </div>
                <div
                  style={{
                    fontFamily: "Arial, sans-serif",
                    fontSize: "26px",
                    color: colors.gray1,
                  }}
                >
                  {point}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Slide>
  );
};

// ── Closing slide ───────────────────────────────────────────────────────
const ClosingSlide = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const mainOpacity = fadeIn(frame, fps);
  const mainY = slideUp(frame, fps);
  const qrOpacity = fadeIn(Math.max(0, frame - delay(3)), fps);
  const thanksOpacity = fadeIn(Math.max(0, frame - delay(5)), fps);

  return (
    <Slide
      style={{ justifyContent: "center", alignItems: "center" }}
    >
      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          left: "50%",
          transform: `translateX(-50%) translateY(${mainY}px)`,
          textAlign: "center",
          opacity: mainOpacity,
        }}
      >
        <div
          style={{
            fontFamily: "Arial Black, Arial, sans-serif",
            fontSize: "120px",
            fontWeight: 900,
            color: colors.white,
            letterSpacing: "-4px",
          }}
        >
          HarnessCI
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "24px",
            color: colors.accent,
            marginTop: "16px",
            letterSpacing: "4px",
          }}
        >
          github.com/Jairogelpi/HarnessCI
        </div>
      </div>

      {/* Separator */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "200px",
          height: "2px",
          background: colors.border,
          opacity: qrOpacity,
        }}
      />

      {/* Thanks */}
      <div
        style={{
          position: "absolute",
          bottom: "20%",
          left: "50%",
          transform: "translateX(-50%)",
          textAlign: "center",
          opacity: thanksOpacity,
        }}
      >
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "36px",
            color: colors.gray1,
            marginBottom: "16px",
          }}
        >
          ¡Gracias!
        </div>
        <div
          style={{
            fontFamily: "Arial, sans-serif",
            fontSize: "20px",
            color: colors.gray3,
          }}
        >
          {DATA.author} · {DATA.tutors}
        </div>
      </div>

      {/* Decorative corner */}
      <svg
        style={{ position: "absolute", top: 0, right: 0 }}
        width="300"
        height="300"
        viewBox="0 0 300 300"
      >
        <circle cx="300" cy="0" r="200" fill={colors.accent} opacity="0.05" />
        <circle cx="300" cy="0" r="100" fill={colors.accent} opacity="0.08" />
      </svg>
      <svg
        style={{ position: "absolute", bottom: 0, left: 0 }}
        width="300"
        height="300"
        viewBox="0 0 300 300"
      >
        <circle cx="0" cy="300" r="200" fill={colors.green} opacity="0.05" />
      </svg>
    </Slide>
  );
};

// ── Root composition ────────────────────────────────────────────────────
export const TFMVideo = () => {
  const SLIDE_DURATION = 30 * FPS; // 30 seconds per slide

  return (
    <AbsoluteFill style={{ background: colors.bg }}>
      <Sequence name="Title" from={0} durationInFrames={SLIDE_DURATION}>
        <TitleSlide />
      </Sequence>
      <Sequence name="Problem" from={SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <ProblemSlide />
      </Sequence>
      <Sequence name="Solution" from={2 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <SolutionSlide />
      </Sequence>
      <Sequence name="Pipeline" from={3 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <PipelineSlide />
      </Sequence>
      <Sequence name="ResultsL2" from={4 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <ResultsL2Slide />
      </Sequence>
      <Sequence name="ResultsL3" from={5 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <ResultsL3Slide />
      </Sequence>
      <Sequence name="Competitive" from={6 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <CompetitiveSlide />
      </Sequence>
      <Sequence name="Ranking" from={7 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <RankingSlide />
      </Sequence>
      <Sequence name="Conclusions" from={8 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <ConclusionsSlide />
      </Sequence>
      <Sequence name="Closing" from={9 * SLIDE_DURATION} durationInFrames={SLIDE_DURATION}>
        <ClosingSlide />
      </Sequence>
    </AbsoluteFill>
  );
};
