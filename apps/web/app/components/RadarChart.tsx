import { Box, InlineStack, Text } from "@shopify/polaris";
import type { ComponentComparison, FunnelSnapshot } from "@/lib/contracts";
import { messages } from "@/lib/messages";

interface RadarChartProps {
  target: FunnelSnapshot;
  benchmark: FunnelSnapshot;
  componentComparisons: ComponentComparison[];
}

interface DimensionScore {
  label: string;
  value: number;
  tone: "success" | "warning" | "critical";
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function safeDivide(a: number, b: number): number {
  return b === 0 ? 0 : a / b;
}

function computeScores(
  target: FunnelSnapshot,
  benchmark: FunnelSnapshot,
  componentComparisons: ComponentComparison[],
): DimensionScore[] {
  const viewScore = clamp(safeDivide(target.views, benchmark.views) * 50, 0, 100);

  const targetAtcRate = safeDivide(target.add_to_carts, target.views);
  const benchAtcRate = safeDivide(benchmark.add_to_carts, benchmark.views);
  const addToCartScore = clamp(safeDivide(targetAtcRate, benchAtcRate) * 50, 0, 100);

  const targetOrderRate = safeDivide(target.orders, target.add_to_carts);
  const benchOrderRate = safeDivide(benchmark.orders, benchmark.add_to_carts);
  const orderScore = clamp(safeDivide(targetOrderRate, benchOrderRate) * 50, 0, 100);

  let ctrScore = 50;
  if (componentComparisons.length > 0) {
    const ratioSum = componentComparisons.reduce(
      (sum, c) => sum + safeDivide(c.target_ctr, c.benchmark_ctr),
      0,
    );
    ctrScore = clamp((ratioSum / componentComparisons.length) * 50, 0, 100);
  }

  const targetConversion = safeDivide(target.orders, target.views);
  const benchConversion = safeDivide(benchmark.orders, benchmark.views);
  const conversionScore = clamp(safeDivide(targetConversion, benchConversion) * 50, 0, 100);

  function scoreTone(score: number): "success" | "warning" | "critical" {
    if (score >= 60) return "success";
    if (score >= 35) return "warning";
    return "critical";
  }

  return [
    { label: messages.analysis.dimensionViews, value: Math.round(viewScore), tone: scoreTone(viewScore) },
    { label: messages.analysis.dimensionAddToCart, value: Math.round(addToCartScore), tone: scoreTone(addToCartScore) },
    { label: messages.analysis.dimensionOrders, value: Math.round(orderScore), tone: scoreTone(orderScore) },
    { label: messages.analysis.dimensionCtr, value: Math.round(ctrScore), tone: scoreTone(ctrScore) },
    { label: messages.analysis.dimensionConversion, value: Math.round(conversionScore), tone: scoreTone(conversionScore) },
  ];
}

const CX = 100;
const CY = 100;
const RADIUS = 75;
const LEVELS = 4;

function polarToCartesian(angleDeg: number, radius: number): [number, number] {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return [CX + radius * Math.cos(angleRad), CY + radius * Math.sin(angleRad)];
}

function polygonPoints(values: number[], maxValue: number): string {
  const angleStep = 360 / values.length;
  return values
    .map((v, i) => {
      const r = (v / maxValue) * RADIUS;
      const [x, y] = polarToCartesian(i * angleStep, r);
      return `${x},${y}`;
    })
    .join(" ");
}

function RadarSvg({ scores }: { scores: DimensionScore[] }) {
  const n = scores.length;
  const angleStep = 360 / n;

  const gridLevels = Array.from({ length: LEVELS }, (_, i) =>
    ((i + 1) / LEVELS) * RADIUS,
  );

  return (
    <svg viewBox="0 0 200 200" style={{ width: "100%", maxWidth: 220, height: "auto" }}>
      {gridLevels.map((r) => (
        <polygon
          key={r}
          points={Array.from({ length: n }, (_, i) => {
            const [x, y] = polarToCartesian(i * angleStep, r);
            return `${x},${y}`;
          }).join(" ")}
          fill="none"
          stroke="#e0e0e0"
          strokeWidth="0.5"
        />
      ))}

      {scores.map((_, i) => {
        const [x, y] = polarToCartesian(i * angleStep, RADIUS);
        return <line key={i} x1={CX} y1={CY} x2={x} y2={y} stroke="#e0e0e0" strokeWidth="0.5" />;
      })}

      <polygon
        points={polygonPoints(scores.map((s) => s.value), 100)}
        fill="rgba(212, 56, 13, 0.12)"
        stroke="#d4380d"
        strokeWidth="1.5"
      />

      {scores.map((s, i) => {
        const r = (s.value / 100) * RADIUS;
        const [x, y] = polarToCartesian(i * angleStep, r);
        return <circle key={`dot-${i}`} cx={x} cy={y} r="3" fill="#d4380d" />;
      })}

      {scores.map((s, i) => {
        const [x, y] = polarToCartesian(i * angleStep, RADIUS + 14);
        return (
          <text
            key={`label-${i}`}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="9"
            fill="#666"
          >
            {s.label}
          </text>
        );
      })}
    </svg>
  );
}

const TONE_COLORS: Record<string, string> = {
  success: "#52c41a",
  warning: "#faad14",
  critical: "#f5222d",
};

function ScoreBar({ score }: { score: DimensionScore }) {
  const color = TONE_COLORS[score.tone] ?? TONE_COLORS.warning;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <span style={{ width: 80, fontSize: 13, color: "#666", flexShrink: 0 }}>{score.label}</span>
      <div style={{ flex: 1, height: 8, background: "#f0f0f0", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${score.value}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.3s" }} />
      </div>
      <span style={{ width: 30, textAlign: "right", fontSize: 13, fontWeight: "bold", color }}>{score.value}</span>
    </div>
  );
}

export function RadarChart({ target, benchmark, componentComparisons }: RadarChartProps) {
  const scores = computeScores(target, benchmark, componentComparisons);

  return (
    <Box>
      <Box paddingBlockEnd="300">
        <Text as="h2" variant="headingMd">{messages.analysis.scoringHeading}</Text>
      </Box>
      <InlineStack gap="600" wrap={false} blockAlign="center">
        <div style={{ flexShrink: 0 }}>
          <RadarSvg scores={scores} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {scores.map((score) => (
            <ScoreBar key={score.label} score={score} />
          ))}
        </div>
      </InlineStack>
    </Box>
  );
}
