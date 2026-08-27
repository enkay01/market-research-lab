import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  LineStyle,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { Card, HStack, Text, VStack } from "@astryxdesign/core";
import type { SpreadPositionDetail } from "../views/optionsDesigns/designData";

interface InteractiveCandlestickChartProps {
  position: SpreadPositionDetail;
}

interface HoverState {
  time: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  spreadWorst?: number;
  spreadBest?: number;
  stopLevel?: number;
  delta?: number;
  iv?: number;
}

export function InteractiveCandlestickChart({ position }: InteractiveCandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [hoverData, setHoverData] = useState<HoverState | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    // Clean, disciplined dark-mode theme
    const chart = createChart(container, {
      width: container.clientWidth || 860,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: "#0d1117" },
        textColor: "#8b949e",
        fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: "#161b22", style: LineStyle.Dotted },
        horzLines: { color: "#161b22", style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#58a6ff", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1f6feb" },
        horzLine: { color: "#58a6ff", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1f6feb" },
      },
      rightPriceScale: {
        borderColor: "#21262d",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: "#21262d",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#238636",
      downColor: "#da3633",
      borderVisible: false,
      wickUpColor: "#238636",
      wickDownColor: "#da3633",
    });

    seriesRef.current = candleSeries;

    const candleData = position.candles.map((c) => {
      const fullDate = c.date.startsWith("2024") ? c.date : `2024-${c.date}`;
      // SAFETY: ISO date string format conforms to Lightweight Charts Time definition
      const timeVal = fullDate as Time;
      return {
        time: timeVal,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      };
    });

    candleSeries.setData(candleData);

    // Labeled Horizontal Strike Lines
    candleSeries.createPriceLine({
      price: position.short_strike,
      color: "#d29922",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `Short $${position.short_strike}`,
    });

    candleSeries.createPriceLine({
      price: position.long_strike,
      color: "#8957e5",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `Long $${position.long_strike}`,
    });

    // Trade Markers
    const entryDate = position.candles[0]?.date.startsWith("2024")
      ? position.candles[0]?.date
      : `2024-${position.candles[0]?.date}`;

    const exitIdx = Math.min(4, position.candles.length - 1);
    const exitDate = position.candles[exitIdx]?.date.startsWith("2024")
      ? position.candles[exitIdx]?.date
      : `2024-${position.candles[exitIdx]?.date}`;

    // SAFETY: ISO date strings conform to Lightweight Charts Time definition
    const entryTime = entryDate as Time;
    // SAFETY: ISO date strings conform to Lightweight Charts Time definition
    const exitTime = exitDate as Time;

    const markers: SeriesMarker<Time>[] = [
      {
        time: entryTime,
        position: "belowBar",
        color: "#58a6ff",
        ["shape"]: "arrowUp",
        text: `Entry ($${position.entry_credit.toFixed(2)})`,
      },
      {
        time: exitTime,
        position: "aboveBar",
        color: position.worst_net_pnl >= 0 ? "#238636" : "#da3633",
        ["shape"]: "arrowDown",
        text: `Exit ($${position.worst_net_pnl > 0 ? "+" : ""}${position.worst_net_pnl.toFixed(0)})`,
      },
    ];

    createSeriesMarkers(candleSeries, markers);

    chart.subscribeCrosshairMove((param) => {
      if (
        !param.time ||
        !param.seriesData ||
        !param.seriesData.get(candleSeries)
      ) {
        setHoverData(null);
        return;
      }

      // SAFETY: Price series data payload is typed from Candlestick data
      const bar = param.seriesData.get(candleSeries) as {
        open: number;
        high: number;
        low: number;
        close: number;
      };

      const timeStr = String(param.time);
      const trajPoint = position.trajectory_points.find((t) =>
        timeStr.includes(t.minute),
      );

      setHoverData({
        time: timeStr,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        spreadWorst: trajPoint?.spread_worst ?? position.entry_credit,
        spreadBest: trajPoint?.spread_best ?? position.entry_credit,
        stopLevel: trajPoint?.stop_level ?? position.stop_movements[0]?.new_stop,
        delta: position.short_delta,
        iv: position.implied_volatility,
      });
    });

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [position]);

  return (
    <VStack gap={2} style={{ width: "100%" }}>
      {/* 1. DISCIPLINED CROSSHAIR HUD (CLEAN MONOCHROME TYPOGRAPHY) */}
      <Card padding={2} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
        <HStack justify="between" align="center" wrap gap={2}>
          <HStack align="center" gap={3}>
            <Text size="sm" type="supporting" style={{ color: "#8b949e", fontVariantNumeric: "tabular-nums" }}>
              {hoverData ? hoverData.time : "Hover chart to inspect bar prices and Greeks"}
            </Text>
            {hoverData && (
              <HStack gap={3} align="center">
                <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                  O: <span style={{ color: "#c9d1d9" }}>${hoverData.open?.toFixed(2)}</span>
                </Text>
                <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                  H: <span style={{ color: "#c9d1d9" }}>${hoverData.high?.toFixed(2)}</span>
                </Text>
                <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                  L: <span style={{ color: "#c9d1d9" }}>${hoverData.low?.toFixed(2)}</span>
                </Text>
                <Text
                  size="sm"
                  style={{
                    fontVariantNumeric: "tabular-nums",
                    color: (hoverData.close || 0) >= (hoverData.open || 0) ? "#3fb950" : "#f85149",
                  }}
                >
                  C: ${hoverData.close?.toFixed(2)}
                </Text>
              </HStack>
            )}
          </HStack>

          {hoverData && (
            <HStack align="center" gap={4}>
              <Text size="sm" type="supporting" style={{ fontVariantNumeric: "tabular-nums" }}>
                Spread Debit: <span style={{ color: "#c9d1d9" }}>${hoverData.spreadWorst?.toFixed(2)}</span>
              </Text>
              <Text size="sm" type="supporting" style={{ fontVariantNumeric: "tabular-nums" }}>
                Ratchet Stop: <span style={{ color: "#f85149" }}>${hoverData.stopLevel?.toFixed(2)}</span>
              </Text>
              <Text size="sm" type="supporting" style={{ fontVariantNumeric: "tabular-nums" }}>
                Short Delta: <span style={{ color: "#c9d1d9" }}>{hoverData.delta?.toFixed(2)} Δ</span>
              </Text>
            </HStack>
          )}
        </HStack>
      </Card>

      {/* 2. TRADINGVIEW CANVAS */}
      <div
        ref={chartContainerRef}
        style={{
          width: "100%",
          height: "300px",
          borderRadius: "4px",
          overflow: "hidden",
          border: "1px solid #30363d",
        }}
      />

      {/* 3. SUBTLE CHART LEGEND */}
      <HStack justify="between" align="center" style={{ width: "100%" }}>
        <HStack gap={3} align="center">
          <Text size="sm" type="supporting" style={{ color: "#58a6ff" }}>
            ↑ Entry
          </Text>
          <Text size="sm" type="supporting" style={{ color: "#d29922" }}>
            - - Short (${position.short_strike})
          </Text>
          <Text size="sm" type="supporting" style={{ color: "#8957e5" }}>
            - - Long (${position.long_strike})
          </Text>
          <Text size="sm" type="supporting" style={{ color: position.worst_net_pnl >= 0 ? "#238636" : "#da3633" }}>
            ↓ Exit
          </Text>
        </HStack>
        <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
          Scroll to zoom • Drag to pan • Hover to seek
        </Text>
      </HStack>
    </VStack>
  );
}
