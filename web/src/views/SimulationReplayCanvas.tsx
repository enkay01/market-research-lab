import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Divider,
  Grid,
  HStack,
  SegmentedControl,
  SegmentedControlItem,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  Token,
  VStack,
} from "@astryxdesign/core";
import type { ReplayTick } from "../api/client";

export type PlaybackSpeed = "0.5x" | "1x" | "2x" | "4x";

const SPEED_MS = {
  "0.5x": 1200,
  "1x": 600,
  "2x": 300,
  "4x": 150,
} as const satisfies Record<PlaybackSpeed, number>;

type ReplayFillAction = NonNullable<ReplayTick["fill_actions"]>[number];

const FILL_ACTION_PRESENTATION = {
  buy: {
    label: "▲ BUY",
    tokenColor: "green",
    textColor: "var(--color-text-green)",
    markerBelow: true,
  },
  exit: {
    label: "▼ EXIT",
    tokenColor: "red",
    textColor: "var(--color-text-red)",
    markerBelow: false,
  },
  short: {
    label: "▼ SHORT",
    tokenColor: "orange",
    textColor: "var(--color-text-orange)",
    markerBelow: false,
  },
} as const;

const NO_FILL_PRESENTATION = {
  label: "No fill",
  tokenColor: "blue",
  textColor: "var(--color-text-primary)",
} as const;

function fillActionLabel(actionType: ReplayFillAction["action_type"]): string {
  return FILL_ACTION_PRESENTATION[actionType].label;
}

function replayActionLabel(fillActions?: ReplayTick["fill_actions"]): string {
  if (!fillActions || fillActions.length === 0) {
    return NO_FILL_PRESENTATION.label;
  }

  return fillActions
    .map(
      (action) =>
        `${fillActionLabel(action.action_type)} ${action.quantity.toFixed(2)} @ $${action.execution_price.toFixed(2)}`,
    )
    .join("; ");
}

export interface SimulationReplayCanvasProps {
  ticks?: ReplayTick[];
  symbol?: string;
}

export function SimulationReplayCanvas({
  ticks = [],
  symbol = "PRIMARY SECURITY",
}: SimulationReplayCanvasProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>("1x");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Schedule one replay step at the selected cadence.
  useEffect(() => {
    if (!isPlaying || ticks.length === 0) return;

    const timer = window.setTimeout(() => {
      setCurrentIndex((prev) => {
        if (prev >= ticks.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, SPEED_MS[speed]);

    return () => clearTimeout(timer);
  }, [currentIndex, isPlaying, speed, ticks.length]);

  if (ticks.length === 0) {
    return (
      <Card padding={4}>
        <VStack gap={3} align="center" style={{ textAlign: "center", padding: "32px 16px" }}>
          <Token label="REPLAY READY" color="blue" />
          <Text weight="bold" size="lg">
            Interactive Simulation Replay Canvas
          </Text>
          <Text size="sm" type="supporting" style={{ maxWidth: "600px" }}>
            No backtest replay ticks available. Execute a strategy evaluation from the setup wizard
            to stream session price bars, fill actions, and portfolio ledger states.
          </Text>
        </VStack>
      </Card>
    );
  }

  const currentTick = ticks[Math.min(currentIndex, ticks.length - 1)] ?? ticks[0];
  const activeIndex = hoverIndex !== null ? hoverIndex : currentIndex;
  const inspectedTick = ticks[Math.min(activeIndex, ticks.length - 1)] ?? currentTick;

  // Chart layout dimensions
  const width = 860;
  const height = 260;
  const paddingLeft = 80;
  const paddingRight = 32;
  const paddingYTop = 36;
  const paddingYBottom = 36;

  const availableW = width - paddingLeft - paddingRight;
  const availableH = height - paddingYTop - paddingYBottom;

  const allPrices = ticks.map((t) => t.price);
  const rawMin = Math.min(...allPrices);
  const rawMax = Math.max(...allPrices);
  const priceMargin = (rawMax - rawMin) * 0.08 || 1.0;
  const minPrice = Math.max(0, rawMin - priceMargin);
  const maxPrice = rawMax + priceMargin;
  const priceRange = maxPrice - minPrice || 1.0;

  // Polyline for the entire price action (muted background path)
  const fullPathPoints = ticks
    .map((t, i) => {
      const x = paddingLeft + (i / Math.max(1, ticks.length - 1)) * availableW;
      const y = height - paddingYBottom - ((t.price - minPrice) / priceRange) * availableH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Polyline for replayed portion up to currentIndex
  const replayedPathPoints = ticks
    .slice(0, currentIndex + 1)
    .map((t, i) => {
      const x = paddingLeft + (i / Math.max(1, ticks.length - 1)) * availableW;
      const y = height - paddingYBottom - ((t.price - minPrice) / priceRange) * availableH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Current session cursor coordinates
  const currentX = paddingLeft + (currentIndex / Math.max(1, ticks.length - 1)) * availableW;
  const currentY =
    height - paddingYBottom - ((currentTick.price - minPrice) / priceRange) * availableH;

  // Y-axis price levels (5 evenly spaced ticks)
  const yTicks = [
    { ratio: 1.0, val: maxPrice, y: paddingYTop },
    { ratio: 0.75, val: minPrice + priceRange * 0.75, y: paddingYTop + availableH * 0.25 },
    { ratio: 0.5, val: minPrice + priceRange * 0.5, y: paddingYTop + availableH * 0.5 },
    { ratio: 0.25, val: minPrice + priceRange * 0.25, y: paddingYTop + availableH * 0.75 },
    { ratio: 0.0, val: minPrice, y: height - paddingYBottom },
  ];

  // X-axis timeline ticks
  const xTicks = [
    { label: ticks[0].date, x: paddingLeft },
    {
      label: ticks[Math.floor(ticks.length * 0.33)].date,
      x: paddingLeft + availableW * 0.33,
    },
    {
      label: ticks[Math.floor(ticks.length * 0.66)].date,
      x: paddingLeft + availableW * 0.66,
    },
    { label: ticks[ticks.length - 1].date, x: width - paddingRight },
  ];

  // Active allocation provided directly by backend domain calculation
  const allocationPct = currentTick.allocation_pct ?? 0;
  const currentFillActions = currentTick.fill_actions ?? [];
  const currentFill =
    currentFillActions.length > 0 ? currentFillActions[currentFillActions.length - 1] : undefined;
  const currentActionPresentation = currentFill
    ? FILL_ACTION_PRESENTATION[currentFill.action_type]
    : NO_FILL_PRESENTATION;
  const currentActionLabel = replayActionLabel(currentFillActions);

  // Flatten every typed fill action so reversals and short covers remain visible.
  const fillEvents = ticks.flatMap((tick, index) =>
    (tick.fill_actions ?? []).map((fill, fillIndex) => ({
      tick,
      index,
      fill,
      fillIndex,
    })),
  );

  return (
    <VStack gap={4} style={{ width: "100%" }}>
      {/* 1. ORDER TICKET BANNER (Surfaces live trade action, allocation, cash, and daily PnL) */}
      <Card
        padding={3}
        style={{
          backgroundColor: "var(--color-background-wash)",
          border: `1px solid ${currentFill ? currentActionPresentation.textColor : "var(--color-border-emphasized)"}`,
        }}
      >
        <VStack gap={2}>
          <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "8px" }}>
            <HStack gap={2} align="center">
              <Token
                label={currentFill ? `${currentActionPresentation.label} ACTION` : "NO FILL"}
                color={currentActionPresentation.tokenColor}
              />
              <Text weight="bold" size="lg">
                Order Ticket: {currentActionLabel}
              </Text>
            </HStack>

            <HStack gap={2} align="center">
              <Text size="sm" type="supporting">
                Session:
              </Text>
              <Text size="sm" weight="bold">
                {currentTick.date}
              </Text>
              <Text size="sm" type="supporting">
                ({currentIndex + 1}/{ticks.length})
              </Text>
            </HStack>
          </HStack>

          <Divider />

          {/* Dynamic Order Ticket Banner KPI Grid */}
          <Grid columns={{ minWidth: 160, repeat: "fit" }} gap={2}>
            {/* Current Trade Action */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Trade Action
                </Text>
                <Text
                  weight="bold"
                  size="lg"
                  style={{ color: currentActionPresentation.textColor }}
                >
                  {currentActionLabel}
                </Text>
              </VStack>
            </Card>

            {/* Active Allocation */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Active Allocation
                </Text>
                <Text weight="bold" size="lg">
                  {allocationPct.toFixed(1)}% (
                  {currentTick.position_shares >= 0 ? "+" : ""}
                  {currentTick.position_shares.toFixed(0)} shs)
                </Text>
              </VStack>
            </Card>

            {/* Cash Balance */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Cash Balance
                </Text>
                <Text weight="bold" size="lg">
                  ${Math.round(currentTick.cash).toLocaleString()}
                </Text>
              </VStack>
            </Card>

            {/* Daily Profit & Loss */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Daily PnL
                </Text>
                <Text
                  weight="bold"
                  size="lg"
                  style={{
                    color:
                      currentTick.daily_pnl >= 0
                        ? "var(--color-text-green)"
                        : "var(--color-text-red)",
                  }}
                >
                  {currentTick.daily_pnl >= 0 ? "+" : ""}
                  ${currentTick.daily_pnl.toFixed(2)}
                </Text>
              </VStack>
            </Card>

            {/* Close Price */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Close Price ({symbol})
                </Text>
                <Text weight="bold" size="lg">
                  ${currentTick.price.toFixed(2)}
                </Text>
              </VStack>
            </Card>

            {/* Portfolio Net Value */}
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">
                  Portfolio Valuation
                </Text>
                <Text weight="bold" size="lg">
                  ${Math.round(currentTick.portfolio_value).toLocaleString()}
                </Text>
              </VStack>
            </Card>
          </Grid>
        </VStack>
      </Card>

      {/* 2. REPLAY CONTROLS & TIMELINE SCRUBBER */}
      <Card padding={3}>
        <VStack gap={3}>
          {/* Controls Bar: Playback Buttons & Speed Toggles */}
          <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "12px" }}>
            {/* Play/Pause & Step Navigation */}
            <HStack gap={2} align="center">
              <Button
                label={isPlaying ? "⏸ Pause" : "▶ Play Replay"}
                variant={isPlaying ? "secondary" : "primary"}
                size="sm"
                onClick={() => {
                  if (currentIndex >= ticks.length - 1) {
                    setCurrentIndex(0);
                  }
                  setIsPlaying(!isPlaying);
                }}
              />
              <Button
                label="⏮ Step"
                variant="secondary"
                size="sm"
                isDisabled={currentIndex === 0}
                onClick={() => {
                  setIsPlaying(false);
                  setCurrentIndex((prev) => Math.max(0, prev - 1));
                }}
              />
              <Button
                label="⏭ Step"
                variant="secondary"
                size="sm"
                isDisabled={currentIndex >= ticks.length - 1}
                onClick={() => {
                  setIsPlaying(false);
                  setCurrentIndex((prev) => Math.min(ticks.length - 1, prev + 1));
                }}
              />
              <Button
                label="↺ Reset"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setIsPlaying(false);
                  setCurrentIndex(0);
                }}
              />
            </HStack>

            {/* Playback Speed Toggles */}
            <HStack gap={2} align="center">
              <Text size="sm" type="supporting">
                Speed:
              </Text>
              <SegmentedControl
                data-testid="playback-speed"
                data-cadence={SPEED_MS[speed]}
                label="Cadence"
                value={speed}
                onChange={(val: string) => {
                  // SAFETY: value is constrained to PlaybackSpeed options
                  setSpeed(val as PlaybackSpeed);
                }}
              >
                <SegmentedControlItem value="0.5x" label="0.5x" />
                <SegmentedControlItem value="1x" label="1x" />
                <SegmentedControlItem value="2x" label="2x" />
                <SegmentedControlItem value="4x" label="4x" />
              </SegmentedControl>
            </HStack>
          </HStack>

          {/* Timeline Scrubber Slider */}
          <VStack gap={1} style={{ width: "100%" }}>
            <HStack justify="between" align="center">
              <Text size="sm" weight="bold">
                Timeline Scrubber
              </Text>
              <Text size="sm" type="supporting">
                Drag slider to scrub simulation timeline ({currentTick.date})
              </Text>
            </HStack>

            <input
              type="range"
              min={0}
              max={ticks.length - 1}
              value={currentIndex}
              aria-label="Simulation Timeline Scrubber"
              data-testid="timeline-scrubber"
              onChange={(e) => {
                setIsPlaying(false);
                setCurrentIndex(Number(e.target.value));
              }}
              style={{
                width: "100%",
                height: "8px",
                cursor: "pointer",
                accentColor: "var(--color-icon-blue)",
              }}
            />

            <HStack justify="between" align="center">
              <Text size="sm" type="supporting" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                {ticks[0].date}
              </Text>
              <Text size="sm" weight="bold" style={{ color: "var(--color-text-blue)" }}>
                Active: {currentTick.date}
              </Text>
              <Text size="sm" type="supporting" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                {ticks[ticks.length - 1].date}
              </Text>
            </HStack>
          </VStack>
        </VStack>
      </Card>

      {/* 3. PRICE PATH CHART CANVAS WITH EXPLICIT LABELS & BUY/EXIT MARKERS */}
      <Card padding={3}>
        <VStack gap={2}>
          <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "8px" }}>
            <VStack gap={0}>
              <Text weight="bold">Simulation Replay Canvas: {symbol}</Text>
              <Text size="sm" type="supporting">
                Price action trajectory with dynamic buy and exit fill markers
              </Text>
            </VStack>

            {/* Legend */}
            <HStack gap={3} align="center">
              <HStack gap={1} align="center">
                <svg width="12" height="12">
                  <polygon points="6,2 11,10 1,10" fill="var(--color-text-green)" />
                </svg>
                <Text size="sm" weight="bold" style={{ color: "var(--color-text-green)" }}>
                  ▲ BUY Fill
                </Text>
              </HStack>

              <HStack gap={1} align="center">
                <svg width="12" height="12">
                  <polygon points="6,10 11,2 1,2" fill="var(--color-icon-orange)" />
                </svg>
                <Text size="sm" weight="bold" style={{ color: "var(--color-text-orange)" }}>
                  ▼ SHORT Fill
                </Text>
              </HStack>

              <HStack gap={1} align="center">
                <svg width="12" height="12">
                  <polygon points="6,10 11,2 1,2" fill="var(--color-text-red)" />
                </svg>
                <Text size="sm" weight="bold" style={{ color: "var(--color-text-red)" }}>
                  ▼ EXIT Fill
                </Text>
              </HStack>

              <HStack gap={1} align="center">
                <svg width="16" height="4">
                  <rect width="16" height="4" rx="2" fill="var(--color-icon-blue)" />
                </svg>
                <Text size="sm" type="supporting">
                  Replayed Path
                </Text>
              </HStack>
            </HStack>
          </HStack>

          {/* Inspection readout during chart hover */}
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
                  {inspectedTick.date}
                </Text>
                <Text size="sm" type="supporting">
                  • Price: ${inspectedTick.price.toFixed(2)}
                </Text>
              </HStack>

              <HStack gap={3} align="center">
                <Text size="sm">
                  Action:{" "}
                  <strong>
                    {replayActionLabel(inspectedTick.fill_actions)}
                  </strong>
                </Text>
                <Text size="sm" type="supporting">
                  Cash: ${Math.round(inspectedTick.cash).toLocaleString()}
                </Text>
                <Text
                  size="sm"
                  style={{
                    color:
                      inspectedTick.daily_pnl >= 0
                        ? "var(--color-text-green)"
                        : "var(--color-text-red)",
                    fontWeight: "bold",
                  }}
                >
                  Day PnL: {inspectedTick.daily_pnl >= 0 ? "+" : ""}
                  ${inspectedTick.daily_pnl.toFixed(2)}
                </Text>
              </HStack>
            </HStack>
          </Card>

          {/* SVG Price Chart */}
          <HStack style={{ width: "100%", overflowX: "auto" }}>
            <svg
              viewBox={`0 0 ${width} ${height + 28}`}
              style={{
                width: "100%",
                height: "288px",
                backgroundColor: "var(--color-background-muted)",
                borderRadius: "var(--radius-container)",
              }}
              onMouseLeave={() => setHoverIndex(null)}
            >
              {/* MANDATORY AXIS LABEL: Y-AXIS TITLE "PRICE (USD)" */}
              <text
                x={paddingLeft - 8}
                y={18}
                textAnchor="end"
                fill="var(--color-text-secondary)"
                fontSize="10"
                fontWeight="bold"
              >
                PRICE (USD)
              </text>

              {/* Y-axis grid lines and price ticks */}
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
                    ${t.val.toFixed(2)}
                  </text>
                </g>
              ))}

              {/* Y-axis spine */}
              <line
                x1={paddingLeft}
                y1={paddingYTop}
                x2={paddingLeft}
                y2={height - paddingYBottom}
                stroke="var(--color-border-emphasized)"
                strokeWidth="1"
              />

              {/* X-axis spine */}
              <line
                x1={paddingLeft}
                y1={height - paddingYBottom}
                x2={width - paddingRight}
                y2={height - paddingYBottom}
                stroke="var(--color-border-emphasized)"
                strokeWidth="1"
              />

              {/* Background Full Price Path (Muted) */}
              <polyline
                fill="none"
                stroke="var(--color-border-emphasized)"
                strokeWidth="1.5"
                strokeDasharray="3 3"
                opacity={0.5}
                points={fullPathPoints}
              />

              {/* Active Replayed Path up to Current Index (Vivid) */}
              <polyline
                fill="none"
                stroke="var(--color-icon-blue)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={replayedPathPoints}
              />

              {/* MANDATORY BUY, SHORT, AND EXIT MARKERS ON PRICE BARS */}
              {fillEvents.map(({ tick: t, index: idx, fill, fillIndex }) => {
                const tickX = paddingLeft + (idx / Math.max(1, ticks.length - 1)) * availableW;
                const tickY =
                  height - paddingYBottom - ((t.price - minPrice) / priceRange) * availableH;
                const fillPresentation = FILL_ACTION_PRESENTATION[fill.action_type];
                const markerColor = fillPresentation.textColor;
                const markerBelow = fillPresentation.markerBelow;
                const markerY = tickY + (markerBelow ? 16 : -16);
                const labelY = tickY + (markerBelow ? 28 : -20);
                const isCurrent = idx === currentIndex;

                return (
                  <g
                    key={`fill-${fill.source_fill_id}-${fill.source_fill_sequence}-${fillIndex}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentIndex(idx);
                    }}
                  >
                    <circle
                      cx={tickX}
                      cy={tickY}
                      r={isCurrent ? 5 : 4}
                      fill={markerColor}
                      stroke="var(--color-background-surface)"
                      strokeWidth="1.5"
                    />
                    <line
                      x1={tickX}
                      y1={tickY}
                      x2={tickX}
                      y2={markerY}
                      stroke={markerColor}
                      strokeWidth="1.5"
                    />
                    <text
                      x={tickX}
                      y={labelY}
                      textAnchor="middle"
                      fill={markerColor}
                      fontSize="11"
                      fontWeight="bold"
                      fontFamily="var(--font-mono, monospace)"
                    >
                      {fillActionLabel(fill.action_type)}
                    </text>
                  </g>
                );
              })}

              {/* Current Session Crosshair & Position Cursor */}
              <line
                x1={currentX}
                y1={paddingYTop}
                x2={currentX}
                y2={height - paddingYBottom}
                stroke="var(--color-border-emphasized)"
                strokeWidth="1.5"
                strokeDasharray="2 2"
              />
              <circle
                cx={currentX}
                cy={currentY}
                r={6}
                fill="var(--color-icon-blue)"
                stroke="var(--color-background-surface)"
                strokeWidth="2"
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

              {/* MANDATORY AXIS LABEL: X-AXIS TITLE "SESSION TIMELINE" */}
              <text
                x={paddingLeft + availableW / 2}
                y={height + 22}
                textAnchor="middle"
                fill="var(--color-text-secondary)"
                fontSize="10"
                fontWeight="bold"
              >
                SESSION TIMELINE
              </text>

              {/* Interactive touch targets along the timeline */}
              {ticks.map((_, i) => {
                const x = paddingLeft + (i / Math.max(1, ticks.length - 1)) * availableW;
                const colWidth = availableW / Math.max(1, ticks.length - 1);
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
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentIndex(i);
                    }}
                  />
                );
              })}
            </svg>
          </HStack>
        </VStack>
      </Card>

      {/* 4. TRADE ACTIONS EVENT LOG (Click any fill to jump replay directly to that point) */}
      {fillEvents.length > 0 && (
        <Card padding={3}>
          <VStack gap={2}>
            <HStack justify="between" align="center">
              <Text weight="bold">Recorded Trade Fill Actions</Text>
              <Text size="sm" type="supporting">
                Click any fill event to navigate replay directly to that session
              </Text>
            </HStack>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Session Date</TableHeaderCell>
                  <TableHeaderCell>Fill Action</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>Quantity</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>
                    Execution Price
                  </TableHeaderCell>
                  <TableHeaderCell>Source Fill</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>Position</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>Cash Balance</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>Day PnL</TableHeaderCell>
                  <TableHeaderCell style={{ textAlign: "end" }}>Action</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fillEvents.map(({ tick: fillTick, index: fillIdx, fill, fillIndex }) => {
                  const isCurrent = fillIdx === currentIndex;
                  const fillPresentation = FILL_ACTION_PRESENTATION[fill.action_type];
                  return (
                    <TableRow
                      key={`fill-${fill.source_fill_id}-${fill.source_fill_sequence}-${fillIndex}`}
                      style={{
                        backgroundColor: isCurrent ? "var(--color-background-surface)" : undefined,
                        cursor: "pointer",
                      }}
                      onClick={() => {
                        setIsPlaying(false);
                        setCurrentIndex(fillIdx);
                      }}
                    >
                      <TableCell>
                        <Text weight={isCurrent ? "bold" : "normal"}>{fillTick.date}</Text>
                      </TableCell>
                      <TableCell>
                        <Token
                          label={fillPresentation.label}
                          color={fillPresentation.tokenColor}
                        />
                      </TableCell>
                      <TableCell style={{ textAlign: "end" }}>
                        {fill.quantity.toFixed(2)} shs
                      </TableCell>
                      <TableCell style={{ textAlign: "end" }}>
                        ${fill.execution_price.toFixed(2)}
                      </TableCell>
                      <TableCell>
                        <Text size="sm">
                          {fill.source_fill_id} · #{fill.source_fill_sequence}
                        </Text>
                      </TableCell>
                      <TableCell style={{ textAlign: "end" }}>
                        {fillTick.position_shares.toFixed(0)} shs
                      </TableCell>
                      <TableCell style={{ textAlign: "end" }}>
                        ${Math.round(fillTick.cash).toLocaleString()}
                      </TableCell>
                      <TableCell
                        style={{
                          textAlign: "end",
                          color:
                            fillTick.daily_pnl >= 0
                              ? "var(--color-text-green)"
                              : "var(--color-text-red)",
                        }}
                      >
                        {fillTick.daily_pnl >= 0 ? "+" : ""}
                        ${fillTick.daily_pnl.toFixed(2)}
                      </TableCell>
                      <TableCell style={{ textAlign: "end" }}>
                        <Button
                          label={isCurrent ? "Active" : "Jump"}
                          variant={isCurrent ? "primary" : "secondary"}
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setIsPlaying(false);
                            setCurrentIndex(fillIdx);
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </VStack>
        </Card>
      )}
    </VStack>
  );
}
