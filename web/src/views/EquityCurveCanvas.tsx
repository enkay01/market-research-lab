import { useState } from "react";
import { Card, HStack, Text, VStack } from "@astryxdesign/core";
import type { VerdictEquityPoint } from "../api/client";

interface EquityCurveCanvasProps {
  points: VerdictEquityPoint[];
  title?: string;
  subtitle?: string;
  isHoldoutPassing?: boolean;
}

export function EquityCurveCanvas({
  points,
  title = "Portfolio Equity vs. SPY Benchmark",
  subtitle = "Net asset value progression over in-sample training and out-of-sample holdout",
  isHoldoutPassing = true,
}: EquityCurveCanvasProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (points.length < 2) return null;

  const width = 860;
  const height = 240;
  const paddingLeft = 80;
  const paddingRight = 28;
  const paddingYTop = 32;
  const paddingYBottom = 30;

  const allStrat = points.map((p) => p.strategy_equity);
  const allBench = points.map((p) => p.benchmark_equity);
  const minVal = Math.min(...allStrat, ...allBench);
  const maxVal = Math.max(...allStrat, ...allBench);
  const valRange = maxVal - minVal || 1;
  const availableH = height - paddingYTop - paddingYBottom;
  const availableW = width - paddingLeft - paddingRight;

  // Split index where is_holdout becomes true
  const splitIndex = points.findIndex((p) => p.is_holdout);
  const hasHoldout = splitIndex >= 0;
  const splitRatio = hasHoldout ? splitIndex / points.length : 0.75;
  const splitX = hasHoldout
    ? paddingLeft + (splitIndex / (points.length - 1)) * availableW
    : paddingLeft + availableW * 0.75;

  const isPct = Math.round(splitRatio * 100);
  const oosPct = 100 - isPct;

  const stratPoints = points
    .map((p, i) => {
      const x = paddingLeft + (i / (points.length - 1)) * availableW;
      const y = height - paddingYBottom - ((p.strategy_equity - minVal) / valRange) * availableH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const benchPoints = points
    .map((p, i) => {
      const x = paddingLeft + (i / (points.length - 1)) * availableW;
      const y = height - paddingYBottom - ((p.benchmark_equity - minVal) / valRange) * availableH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const hoveredPoint = hoverIndex !== null ? points[hoverIndex] : points[points.length - 1];

  // Y-axis levels (100%, 75%, 50%, 25%, 0%)
  const yTicks = [
    { ratio: 1.0, val: maxVal, y: paddingYTop },
    { ratio: 0.75, val: minVal + valRange * 0.75, y: paddingYTop + availableH * 0.25 },
    { ratio: 0.5, val: minVal + valRange * 0.5, y: paddingYTop + availableH * 0.5 },
    { ratio: 0.25, val: minVal + valRange * 0.25, y: paddingYTop + availableH * 0.75 },
    { ratio: 0.0, val: minVal, y: height - paddingYBottom },
  ];

  // X-axis date milestones
  const xTicks = [
    { label: points[0].session_date, x: paddingLeft },
    {
      label: points[Math.floor(points.length * 0.33)].session_date,
      x: paddingLeft + availableW * 0.33,
    },
    {
      label: points[Math.floor(points.length * 0.66)].session_date,
      x: paddingLeft + availableW * 0.66,
    },
    { label: points[points.length - 1].session_date, x: width - paddingRight },
  ];

  return (
    <Card padding={3}>
      <VStack gap={3}>
        {/* Header with Title and Top Legend */}
        <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "8px" }}>
          <VStack gap={0}>
            <Text weight="bold">{title}</Text>
            <Text size="sm" type="supporting">
              {subtitle}
            </Text>
          </VStack>

          {/* Integrated Clean Top Legend */}
          <HStack gap={4} align="center">
            <HStack gap={1} align="center">
              <svg width="16" height="4" style={{ display: "inline-block" }}>
                <rect width="16" height="4" rx="2" fill="var(--color-icon-blue)" />
              </svg>
              <Text size="sm" weight="bold">
                Strategy Portfolio
              </Text>
            </HStack>

            <HStack gap={1} align="center">
              <svg width="16" height="4" style={{ display: "inline-block" }}>
                <rect width="16" height="4" rx="2" fill="var(--color-icon-orange)" />
              </svg>
              <Text size="sm" type="supporting">
                SPY Benchmark
              </Text>
            </HStack>

            <HStack gap={1} align="center">
              <svg width="16" height="12" style={{ display: "inline-block" }}>
                <line
                  x1="8"
                  y1="0"
                  x2="8"
                  y2="12"
                  stroke="var(--color-border-emphasized)"
                  strokeWidth="2"
                  strokeDasharray="3 3"
                />
              </svg>
              <Text size="sm" type="supporting">
                Holdout Cutoff
              </Text>
            </HStack>
          </HStack>
        </HStack>

        {/* Live Hover Inspection Bar */}
        <Card
          padding={2}
          style={{
            backgroundColor: "var(--color-background-muted)",
            border: "1px solid var(--color-border)",
          }}
        >
          <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "8px" }}>
            <HStack gap={2} align="center">
              <Text size="sm" weight="bold">
                {hoveredPoint.session_date}
              </Text>
              <Text size="sm" type="supporting">
                • {hoveredPoint.is_holdout ? `Out-of-Sample Holdout (${oosPct}%)` : `In-Sample Training (${isPct}%)`}
              </Text>
            </HStack>

            <HStack gap={4} align="center">
              <Text size="sm" style={{ color: "var(--color-text-blue)", fontWeight: "bold" }}>
                Strategy: ${Math.round(hoveredPoint.strategy_equity).toLocaleString()}
              </Text>
              <Text size="sm" style={{ color: "var(--color-text-orange)" }}>
                Benchmark: ${Math.round(hoveredPoint.benchmark_equity).toLocaleString()}
              </Text>
              <Text
                size="sm"
                style={{
                  color:
                    hoveredPoint.drawdown_pct < -10
                      ? "var(--color-text-red)"
                      : "var(--color-text-secondary)",
                }}
              >
                Drawdown: {hoveredPoint.drawdown_pct.toFixed(1)}%
              </Text>
            </HStack>
          </HStack>
        </Card>

        {/* SVG Equity Canvas with Shading */}
        <HStack style={{ width: "100%", overflowX: "auto" }}>
          <svg
            viewBox={`0 0 ${width} ${height + 24}`}
            style={{
              width: "100%",
              height: "264px",
              backgroundColor: "var(--color-background-muted, #0f172a)",
              borderRadius: "var(--radius-container, 8px)",
            }}
            onMouseLeave={() => setHoverIndex(null)}
          >
            {/* Axis Label: Y-axis title */}
            <text
              x={paddingLeft - 8}
              y={16}
              textAnchor="end"
              fill="var(--color-text-secondary)"
              fontSize="10"
              fontWeight="bold"
            >
              PORTFOLIO VALUE (USD)
            </text>

            {/* Y-axis grid lines and formatted price ticks */}
            {yTicks.map((t, idx) => (
              <g key={idx}>
                <line
                  x1={paddingLeft}
                  y1={t.y}
                  x2={width - paddingRight}
                  y2={t.y}
                  stroke="var(--color-border)"
                  strokeDasharray={idx === 0 || idx === 4 ? undefined : "2 4"}
                />
                <text
                  x={paddingLeft - 8}
                  y={t.y + 4}
                  textAnchor="end"
                  fill="var(--color-text-secondary)"
                  fontSize="10"
                  fontFamily="var(--font-mono, monospace)"
                >
                  ${Math.round(t.val).toLocaleString()}
                </text>
              </g>
            ))}

            {/* Vertical Y-axis spine */}
            <line
              x1={paddingLeft}
              y1={paddingYTop}
              x2={paddingLeft}
              y2={height - paddingYBottom}
              stroke="var(--color-border-emphasized)"
              strokeWidth="1"
            />

            {/* Horizontal X-axis spine */}
            <line
              x1={paddingLeft}
              y1={height - paddingYBottom}
              x2={width - paddingRight}
              y2={height - paddingYBottom}
              stroke="var(--color-border-emphasized)"
              strokeWidth="1"
            />

            {/* In-Sample vs Out-of-Sample Holdout Zone Background */}
            <rect
              x={splitX}
              y={paddingYTop}
              width={width - paddingRight - splitX}
              height={availableH}
              fill="var(--color-background-surface)"
              opacity={0.35}
            />

            {/* Split boundary vertical dashed line */}
            <line
              x1={splitX}
              y1={paddingYTop}
              x2={splitX}
              y2={height - paddingYBottom}
              stroke="var(--color-border-emphasized)"
              strokeWidth="2"
              strokeDasharray="4 4"
            />

            {/* Dynamic Partition Zone Watermark Labels */}
            <text
              x={paddingLeft + 12}
              y={paddingYTop + 20}
              fill="var(--color-text-secondary)"
              fontSize="11"
              fontWeight="bold"
              opacity={0.7}
            >
              IN-SAMPLE TRAINING ({isPct}%)
            </text>

            <text
              x={splitX + 12}
              y={paddingYTop + 20}
              fill={
                isHoldoutPassing
                  ? "var(--color-text-green)"
                  : "var(--color-text-red)"
              }
              fontSize="11"
              fontWeight="bold"
              opacity={0.85}
            >
              HOLDOUT EVALUATION ({oosPct}%)
            </text>

            {/* Benchmark Equity Polyline */}
            <polyline
              fill="none"
              stroke="var(--color-icon-orange)"
              strokeWidth="2"
              strokeDasharray="4 3"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={benchPoints}
              opacity={0.8}
            />

            {/* Strategy Equity Polyline */}
            <polyline
              fill="none"
              stroke="var(--color-icon-blue)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={stratPoints}
            />

            {/* X-axis date milestone ticks */}
            {xTicks.map((xt, idx) => (
              <g key={idx}>
                <line
                  x1={xt.x}
                  y1={height - paddingYBottom}
                  x2={xt.x}
                  y2={height - paddingYBottom + 4}
                  stroke="var(--color-border-emphasized)"
                />
                <text
                  x={xt.x}
                  y={height - paddingYBottom + 16}
                  textAnchor={idx === 0 ? "start" : idx === 3 ? "end" : "middle"}
                  fill="var(--color-text-secondary)"
                  fontSize="10"
                  fontFamily="var(--font-mono, monospace)"
                >
                  {xt.label}
                </text>
              </g>
            ))}

            {/* X-axis title */}
            <text
              x={paddingLeft + availableW / 2}
              y={height + 18}
              textAnchor="middle"
              fill="var(--color-text-secondary)"
              fontSize="10"
              fontWeight="bold"
            >
              SESSION DATE
            </text>

            {/* Interactive hover overlay lines and touch targets */}
            {points.map((_, i) => {
              const x = paddingLeft + (i / (points.length - 1)) * availableW;
              const colWidth = availableW / (points.length - 1);
              return (
                <rect
                  key={i}
                  x={x - colWidth / 2}
                  y={paddingYTop}
                  width={colWidth}
                  height={availableH}
                  fill="transparent"
                  style={{ cursor: "crosshair" }}
                  onMouseEnter={() => setHoverIndex(i)}
                />
              );
            })}

            {/* Active hover crosshair line */}
            {hoverIndex !== null && (
              <line
                x1={paddingLeft + (hoverIndex / (points.length - 1)) * availableW}
                y1={paddingYTop}
                x2={paddingLeft + (hoverIndex / (points.length - 1)) * availableW}
                y2={height - paddingYBottom}
                stroke="var(--color-border-emphasized)"
                strokeWidth="1.5"
                strokeDasharray="2 2"
              />
            )}
          </svg>
        </HStack>
      </VStack>
    </Card>
  );
}
