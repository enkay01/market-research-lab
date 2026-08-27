import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { Card, HStack, Text, VStack } from "@astryxdesign/core";
import type { OptionsSpreadPosition } from "../api/client";

interface InteractiveCandlestickChartProps {
  position: OptionsSpreadPosition;
}

interface HoverState {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  spreadWorst?: number;
  spreadBest?: number;
  stopLevel?: number;
  delta?: number;
}

function chartTime(value: string): Time {
  const timestamp = Date.parse(value);
  // SAFETY: API timestamps are ISO values and Lightweight Charts accepts Unix seconds.
  return Math.floor(timestamp / 1000) as Time;
}

export function InteractiveCandlestickChart({ position }: InteractiveCandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const cssColor = (name: string) => getComputedStyle(container).getPropertyValue(name).trim();
    const borderColor = cssColor("--color-border");
    const primaryText = cssColor("--color-text-primary");
    const mutedBackground = cssColor("--color-background-muted");
    const green = cssColor("--color-icon-green");
    const red = cssColor("--color-icon-red");
    const orange = cssColor("--color-icon-orange");
    const blue = cssColor("--color-icon-blue");
    const chart = createChart(container, {
      width: container.clientWidth || 860,
      height: 320,
      layout: { background: { type: ColorType.Solid, color: mutedBackground }, textColor: primaryText, fontSize: 11 },
      grid: { vertLines: { color: borderColor, style: LineStyle.Dotted }, horzLines: { color: borderColor, style: LineStyle.Dotted } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor, timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;
    const series = chart.addSeries(CandlestickSeries, {
      upColor: green,
      downColor: red,
      borderVisible: false,
      wickUpColor: green,
      wickDownColor: red,
    });
    const candles = position.candles.map((candle) => ({
      time: chartTime(candle.date),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    }));
    if (candles.length > 0) series.setData(candles);
    series.createPriceLine({ price: position.short_strike, color: orange, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `Short $${position.short_strike}` });
    series.createPriceLine({ price: position.long_strike, color: blue, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: `Long $${position.long_strike}` });
    if (candles.length > 0) {
      const entry = candles.find((candle) => candle.time === chartTime(position.open_timestamp))?.time ?? candles[0].time;
      const exit = position.close_timestamp
        ? candles.find((candle) => candle.time === chartTime(position.close_timestamp))?.time ?? candles[candles.length - 1].time
        : candles[candles.length - 1].time;
      const markers: SeriesMarker<Time>[] = [
        { time: entry, position: "belowBar", color: blue, ["shape"]: "arrowUp", text: "Entry" },
        { time: exit, position: "aboveBar", color: position.worst_net_pnl < 0 ? red : green, ["shape"]: "arrowDown", text: "Exit" },
      ];
      createSeriesMarkers(series, markers);
    }
    chart.subscribeCrosshairMove((param) => {
      const raw = param.seriesData?.get(series);
      if (!param.time || !raw || !("open" in raw)) {
        setHover(null);
        return;
      }
      // SAFETY: CandlestickSeries data always has OHLC fields after the guard above.
      const bar = raw as { open: number; high: number; low: number; close: number };
      const minute = String(param.time);
      const point = position.trajectory_points.find((item) => String(chartTime(item.minute)) === minute);
      setHover({ time: minute, open: bar.open, high: bar.high, low: bar.low, close: bar.close, spreadWorst: point?.spread_worst, spreadBest: point?.spread_best, stopLevel: point?.stop_level, delta: position.short_delta });
    });
    chart.timeScale().fitContent();
    const resize = () => chart.applyOptions({ width: container.clientWidth });
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
    };
  }, [position]);

  return (
    <VStack gap={2} style={{ width: "100%" }}>
      <Card padding={2}>
        <HStack justify="between" align="center" wrap gap={2}>
          <Text size="sm" type="supporting">{hover?.time ?? "Hover a candlestick to inspect the market state"}</Text>
          {hover && <HStack gap={3} wrap><Text size="sm">O {hover.open.toFixed(2)}</Text><Text size="sm">H {hover.high.toFixed(2)}</Text><Text size="sm">L {hover.low.toFixed(2)}</Text><Text size="sm">C {hover.close.toFixed(2)}</Text><Text size="sm">Spread worst {hover.spreadWorst?.toFixed(2) ?? "n/a"}</Text><Text size="sm">Spread best {hover.spreadBest?.toFixed(2) ?? "n/a"}</Text><Text size="sm">Stop {hover.stopLevel?.toFixed(2) ?? "n/a"}</Text><Text size="sm">Delta {hover.delta?.toFixed(3) ?? "n/a"}</Text></HStack>}
        </HStack>
      </Card>
      <Card ref={containerRef} padding={0} style={{ width: "100%", height: "320px", overflow: "hidden", border: "1px solid var(--color-border)" }} />
      <HStack justify="between" wrap gap={2}>
        <HStack gap={3}><Text size="sm" type="supporting">↑ Entry</Text><Text size="sm" type="supporting">Short ${position.short_strike}</Text><Text size="sm" type="supporting">Long ${position.long_strike}</Text><Text size="sm" type="supporting">↓ Exit</Text></HStack>
        <Text size="sm" type="supporting">Scroll to zoom · drag to pan</Text>
      </HStack>
    </VStack>
  );
}
