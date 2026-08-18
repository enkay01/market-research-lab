import { useEffect, useState, useMemo } from "react";
import {
  Layout,
  LayoutHeader,
  LayoutContent,
  LayoutPanel,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  VStack,
  HStack,
  Button,
  Heading,
  Text,
  Badge,
  Token,
  StatusDot,
  Banner,
  Selector,
  SegmentedControl,
  SegmentedControlItem,
  TextInput,
  Dialog,
  DialogHeader,
  EmptyState,
  Card,
} from "@astryxdesign/core";
import {
  api,
  type Project,
  type CoverageResponse,
  type IndicatorMetadata,
  type IndicatorSeries,
  type IndicatorPoint,
  type PredictiveModelMetadata,
  type PredictiveModelRun,
  type PredictiveModelRunRequest,
  type StrategyMetadata,
  type StrategyEvaluation,
  type StrategyEvaluateRequest,
} from "../api/client";

interface ModelsViewProps {
  project?: Project;
}

export function ModelsView({ project }: ModelsViewProps) {
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<"indicators" | "predictive" | "strategies">("indicators");

  // Datasets & Securities
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [symbols, setSymbols] = useState<string[]>(["AAPL"]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("AAPL");

  // Indicator Metadata & Selection
  const [indicators, setIndicators] = useState<IndicatorMetadata[]>([]);
  const [selectedIndicatorName, setSelectedIndicatorName] = useState<string>("moving_average_crossover");
  const [paramValues, setParamValues] = useState<Record<string, string | number>>({
    fast_period: 20,
    slow_period: 50,
    ma_type: "sma",
    period: 20,
  });

  // Calculation Results & State
  const [series, setSeries] = useState<IndicatorSeries | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Predictive Model Metadata, Parameters, and Results
  const [predictiveModels, setPredictiveModels] = useState<PredictiveModelMetadata[]>([]);
  const [selectedPredictiveModelName, setSelectedPredictiveModelName] = useState<string>(
    "momentum_return_regression",
  );
  const [predictiveParams, setPredictiveParams] = useState<Record<string, string | number>>({
    momentum_period: 20,
    training_window: 252,
  });
  const [predictiveResult, setPredictiveResult] = useState<PredictiveModelRun | null>(null);
  const [isPredictiveLoading, setIsPredictiveLoading] = useState<boolean>(false);
  const [predictiveError, setPredictiveError] = useState<string | null>(null);

  // Hover state for interactive chart
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Save Revision Dialog State
  const [isSaveOpen, setIsSaveOpen] = useState<boolean>(false);
  const [definitionName, setDefinitionName] = useState<string>("ma_crossover_strategy");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Strategy State
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([]);
  const [selectedStrategyName, setSelectedStrategyName] = useState<string>("long_flat_moving_average");
  const [strategyParams, setStrategyParams] = useState<Record<string, string | number>>({
    fast_period: 20,
    slow_period: 50,
    ma_type: "sma",
  });
  const [strategyResult, setStrategyResult] = useState<StrategyEvaluation | null>(null);
  const [isStrategyLoading, setIsStrategyLoading] = useState<boolean>(false);
  const [strategyError, setStrategyError] = useState<string | null>(null);
  const [strategySaveSuccess, setStrategySaveSuccess] = useState<string | null>(null);

  // Load available datasets and indicators on mount
  useEffect(() => {
    void Promise.all([
      api.listDatasets(),
      api.listIndicators(),
      api.listPredictiveModels(),
      api.listStrategies(),
    ])
      .then(([allDatasets, allIndicators, allPredictiveModels, allStrategies]) => {
        // Filter daily bars datasets
        const barDatasets = allDatasets.filter(
          (d) => d.dataset_type === "daily_bars" || (!d.is_fundamentals && !d.is_corporate_actions),
        );
        setDatasets(barDatasets);
        if (barDatasets.length > 0) {
          setSelectedDatasetId(barDatasets[0].id);
        }
        setIndicators(allIndicators);
        setPredictiveModels(allPredictiveModels);
        setStrategies(allStrategies);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load indicator metadata.");
      });
  }, []);

  // When selected dataset changes, load available symbols
  useEffect(() => {
    if (!selectedDatasetId) return;
    void api
      .getPreview(selectedDatasetId)
      .then((rows) => {
        const foundSymbols = Array.from(
          new Set(
            rows
              .map((r) => String(r.symbol || r.ticker || ""))
              .filter((s) => s.length > 0),
          ),
        );
        setSymbols(foundSymbols);
        if (foundSymbols.length > 0 && (!selectedSymbol || !foundSymbols.includes(selectedSymbol))) {
          setSelectedSymbol(foundSymbols[0]);
        }
      })
      .catch(() => {
        // Fallback default
        if (!selectedSymbol) setSelectedSymbol("AAPL");
      });
  }, [selectedDatasetId]);

  // Reload the latest saved Predictive Model Run when the active Project changes.
  useEffect(() => {
    setPredictiveResult(null);
    setPredictiveError(null);
    if (!project) {
      return;
    }
    void api
      .listPredictiveModelRuns(project.id)
      .then((runs) => {
        if (runs.length > 0) {
          const latestRun = runs[0];
          setPredictiveResult(latestRun);
          setSelectedPredictiveModelName(latestRun.model_name);
          setSelectedSymbol(latestRun.symbol);
          const restoredParameters: Record<string, string | number> = {};
          for (const [name, value] of Object.entries(latestRun.parameters)) {
            if (typeof value === "string" || typeof value === "number") {
              restoredParameters[name] = value;
            }
          }
          setPredictiveParams((previous) => ({ ...previous, ...restoredParameters }));
        }
      })
      .catch((err: unknown) => {
        setPredictiveError(err instanceof Error ? err.message : "Failed to load saved model runs.");
      });
  }, [project]);

  const currentIndicator = useMemo(
    () => indicators.find((ind) => ind.name === selectedIndicatorName),
    [indicators, selectedIndicatorName],
  );

  const currentStrategy = useMemo(
    () => strategies.find((strat) => strat.name === selectedStrategyName),
    [strategies, selectedStrategyName],
  );

  const currentPredictiveModel = useMemo(
    () => predictiveModels.find((model) => model.name === selectedPredictiveModelName),
    [predictiveModels, selectedPredictiveModelName],
  );

  // Update default param values when indicator changes
  useEffect(() => {
    if (!currentIndicator) return;
    const defaults: Record<string, string | number> = {};
    for (const p of currentIndicator.parameters) {
      defaults[p.name] = (p.default as string | number) ?? (p.param_type === "int" ? 20 : "sma");
    }
    setParamValues((prev) => ({ ...defaults, ...prev }));
  }, [currentIndicator]);

  // Update default strategy param values when strategy changes
  useEffect(() => {
    if (!currentStrategy) return;
    const defaults: Record<string, string | number> = {};
    for (const p of currentStrategy.parameters) {
      defaults[p.name] = (p.default as string | number) ?? (p.param_type === "int" ? 20 : "sma");
    }
    setStrategyParams((prev) => ({ ...defaults, ...prev }));
  }, [currentStrategy]);

  useEffect(() => {
    if (!currentPredictiveModel) return;
    const defaults: Record<string, string | number> = {};
    for (const parameter of currentPredictiveModel.parameters) {
      if (typeof parameter.default === "string" || typeof parameter.default === "number") {
        defaults[parameter.name] = parameter.default;
      }
    }
    setPredictiveParams((previous) => ({ ...defaults, ...previous }));
  }, [currentPredictiveModel]);

  async function handleCalculate() {
    if (!selectedDatasetId || !selectedSymbol || !selectedIndicatorName) {
      setError("Please select a dataset and symbol.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setSaveSuccess(null);

    const typedParams: Record<string, unknown> = {};
    if (currentIndicator) {
      for (const p of currentIndicator.parameters) {
        const raw = paramValues[p.name];
        if (p.param_type === "int") {
          typedParams[p.name] = parseInt(String(raw), 10) || (p.default as number);
        } else if (p.param_type === "float") {
          typedParams[p.name] = parseFloat(String(raw)) || (p.default as number);
        } else {
          typedParams[p.name] = raw || p.default;
        }
      }
    }

    try {
      const result = await api.calculateIndicator({
        name: selectedIndicatorName,
        dataset_version_id: selectedDatasetId,
        symbol: selectedSymbol,
        parameters: typedParams,
        price_field: "close",
      });
      setSeries(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to calculate indicator.");
      setSeries(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSaveRevision() {
    if (!project || !series) return;
    setIsSaving(true);
    setError(null);
    try {
      const sanitizedName = definitionName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "_");
      await api.saveDefinition(project.id, {
        kind: "indicator",
        name: sanitizedName,
        definition: {
          indicator: series.indicator_name,
          symbol: series.symbol,
          dataset_version_id: series.dataset_version_id,
          parameters: series.parameters,
          saved_at: new Date().toISOString(),
        },
      });
      setSaveSuccess(`Successfully saved revision for '${sanitizedName}'.`);
      setIsSaveOpen(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save revision.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleEvaluateStrategy() {
    if (!selectedDatasetId || !selectedSymbol || !selectedStrategyName) {
      setStrategyError("Please select a dataset and symbol.");
      return;
    }

    setIsStrategyLoading(true);
    setStrategyError(null);
    setStrategySaveSuccess(null);

    const typedParams: Record<string, unknown> = {};
    if (currentStrategy) {
      for (const p of currentStrategy.parameters) {
        const raw = strategyParams[p.name];
        if (p.param_type === "int") {
          typedParams[p.name] = parseInt(String(raw), 10) || (p.default as number);
        } else {
          typedParams[p.name] = raw || p.default;
        }
      }
    }

    const request: StrategyEvaluateRequest = {
      name: selectedStrategyName,
      dataset_version_id: selectedDatasetId,
      symbol: selectedSymbol,
      parameters: typedParams,
      price_field: "close",
    };

    try {
      const result = await api.evaluateStrategy(request);
      setStrategyResult(result);
    } catch (err: unknown) {
      setStrategyError(err instanceof Error ? err.message : "Failed to evaluate strategy.");
      setStrategyResult(null);
    } finally {
      setIsStrategyLoading(false);
    }
  }

  async function handleRunPredictiveModel() {
    if (!selectedDatasetId || !selectedSymbol || !selectedPredictiveModelName) {
      setPredictiveError("Please select a dataset and symbol.");
      return;
    }

    setIsPredictiveLoading(true);
    setPredictiveError(null);
    const typedParams: Record<string, number | string | boolean | null> = {};
    if (currentPredictiveModel) {
      for (const parameter of currentPredictiveModel.parameters) {
        const raw = predictiveParams[parameter.name];
        if (parameter.param_type === "int") {
          const fallback = typeof parameter.default === "number" ? parameter.default : 0;
          typedParams[parameter.name] = Number.parseInt(String(raw), 10) || fallback;
        } else if (parameter.param_type === "float") {
          const fallback = typeof parameter.default === "number" ? parameter.default : 0;
          typedParams[parameter.name] = Number.parseFloat(String(raw)) || fallback;
        } else {
          typedParams[parameter.name] = raw ?? parameter.default;
        }
      }
    }

    const request: PredictiveModelRunRequest = {
      name: selectedPredictiveModelName,
      dataset_version_id: selectedDatasetId,
      symbol: selectedSymbol,
      parameters: typedParams,
    };

    try {
      const result = project
        ? await api.runPredictiveModel(project.id, request)
        : await api.previewPredictiveModel(request);
      setPredictiveResult(result);
    } catch (err: unknown) {
      setPredictiveError(err instanceof Error ? err.message : "Failed to run Predictive Model.");
      setPredictiveResult(null);
    } finally {
      setIsPredictiveLoading(false);
    }
  }

  async function handleSaveStrategyRevision() {
    if (!project || !strategyResult) return;
    setIsSaving(true);
    setStrategyError(null);
    setStrategySaveSuccess(null);
    const request: StrategyEvaluateRequest = {
      name: selectedStrategyName,
      dataset_version_id: strategyResult.dataset_version_id,
      symbol: strategyResult.symbol,
      parameters: strategyResult.parameters,
      price_field: "close",
    };
    try {
      const saved = await api.saveStrategyEvaluation(project.id, request);
      setStrategySaveSuccess(
        `Saved revision '${saved.revision}' (${saved.strategy_revision}).`,
      );
    } catch (err: unknown) {
      setStrategyError(err instanceof Error ? err.message : "Failed to save strategy revision.");
    } finally {
      setIsSaving(false);
    }
  }

  // Summary statistics calculation
  const latestPoint = useMemo(() => {
    if (!series || series.points.length === 0) return null;
    return series.points[series.points.length - 1];
  }, [series]);

  const latestState = useMemo(() => {
    if (!latestPoint) return null;
    return String(latestPoint.values["state"] || "");
  }, [latestPoint]);

  // Chart computation geometry
  const chartPoints = useMemo(() => {
    if (!series || series.points.length === 0) return null;
    const pts = series.points;
    const n = pts.length;

    let minVal = Infinity;
    let maxVal = -Infinity;

    for (const p of pts) {
      if (p.price < minVal) minVal = p.price;
      if (p.price > maxVal) maxVal = p.price;
      if (typeof p.values["fast_ma"] === "number") {
        minVal = Math.min(minVal, p.values["fast_ma"]);
        maxVal = Math.max(maxVal, p.values["fast_ma"]);
      }
      if (typeof p.values["slow_ma"] === "number") {
        minVal = Math.min(minVal, p.values["slow_ma"]);
        maxVal = Math.max(maxVal, p.values["slow_ma"]);
      }
      if (typeof p.values["sma"] === "number") {
        minVal = Math.min(minVal, p.values["sma"]);
        maxVal = Math.max(maxVal, p.values["sma"]);
      }
      if (typeof p.values["ema"] === "number") {
        minVal = Math.min(minVal, p.values["ema"]);
        maxVal = Math.max(maxVal, p.values["ema"]);
      }
    }

    const padding = (maxVal - minVal) * 0.08 || 5;
    const yMin = Math.max(0, minVal - padding);
    const yMax = maxVal + padding;
    const yRange = yMax - yMin || 1;

    const width = 800;
    const height = 300;
    const chartMargin = { top: 20, right: 30, bottom: 30, left: 60 };
    const innerW = width - chartMargin.left - chartMargin.right;
    const innerH = height - chartMargin.top - chartMargin.bottom;

    const getX = (idx: number) => chartMargin.left + (n > 1 ? (idx / (n - 1)) * innerW : innerW / 2);
    const getY = (val: number) => chartMargin.top + innerH - ((val - yMin) / yRange) * innerH;

    // Price path
    const pricePath = pts
      .map((p, i) => `${i === 0 ? "M" : "L"} ${getX(i).toFixed(1)} ${getY(p.price).toFixed(1)}`)
      .join(" ");

    // Fast MA / SMA path
    const fastMaPts = pts.map((p, i) => {
      const v = (p.values["fast_ma"] ?? p.values["sma"] ?? p.values["ema"]) as number | undefined;
      return typeof v === "number" ? { x: getX(i), y: getY(v), idx: i } : null;
    }).filter(Boolean) as { x: number; y: number; idx: number }[];

    const fastMaPath = fastMaPts
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ");

    // Slow MA path
    const slowMaPts = pts.map((p, i) => {
      const v = p.values["slow_ma"] as number | undefined;
      return typeof v === "number" ? { x: getX(i), y: getY(v), idx: i } : null;
    }).filter(Boolean) as { x: number; y: number; idx: number }[];

    const slowMaPath = slowMaPts
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ");

    // Warmup rectangle width
    const warmupW = series.warmup_period > 0 && n > 1
      ? Math.max(0, getX(Math.min(series.warmup_period, n - 1)) - chartMargin.left)
      : 0;

    return {
      width,
      height,
      chartMargin,
      innerW,
      innerH,
      yMin,
      yMax,
      getX,
      getY,
      pricePath,
      fastMaPath,
      slowMaPath,
      warmupW,
    };
  }, [series]);

  const activeHoveredPoint = hoveredIndex !== null && series ? series.points[hoveredIndex] : null;

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Indicators & Predictive Models</Heading>
              <SegmentedControl
                label="Workspace Mode"
                value={activeWorkspaceTab}
                onChange={(val) => setActiveWorkspaceTab(val as "indicators" | "predictive" | "strategies")}
              >
                <SegmentedControlItem value="indicators" label="Technical Indicators" />
                <SegmentedControlItem value="predictive" label="Predictive Models" />
                <SegmentedControlItem value="strategies" label="Strategies" />
              </SegmentedControl>
            </HStack>

            <HStack gap={2} align="center">
              {project && <Badge label={`Project: ${project.name}`} variant="purple" />}
              {series && project && (
                <Button
                  label="Save Revision"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsSaveOpen(true)}
                />
              )}
              {activeWorkspaceTab === "indicators" && (
                <Button
                  label="Calculate Indicator"
                  variant="primary"
                  size="sm"
                  onClick={handleCalculate}
                  isLoading={isLoading}
                />
              )}
              {activeWorkspaceTab === "predictive" && (
                <Button
                  label={project ? "Run & Save Model" : "Run Model"}
                  variant="primary"
                  size="sm"
                  onClick={handleRunPredictiveModel}
                  isLoading={isPredictiveLoading}
                />
              )}
              {activeWorkspaceTab === "strategies" && (
                <Button
                  label="Evaluate Strategy"
                  variant="primary"
                  size="sm"
                  onClick={handleEvaluateStrategy}
                  isLoading={isStrategyLoading}
                />
              )}
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            {error && (
              <Banner status="error" title="Calculation Error">
                {error}
              </Banner>
            )}

            {saveSuccess && (
              <Banner status="success" title="Revision Saved">
                {saveSuccess}
              </Banner>
            )}

            {activeWorkspaceTab === "indicators" ? (
              series && chartPoints ? (
                <VStack gap={4}>
                  {/* Summary Bar */}
                  <HStack justify="between" align="center" style={{ flexWrap: "wrap" }}>
                    <VStack gap={0}>
                      <Heading level={3}>
                        {currentIndicator?.display_name || series.indicator_name} ({series.symbol})
                      </Heading>
                      <Text type="supporting">
                        Time-aligned deterministic series over {series.total_bars} daily sessions.
                      </Text>
                    </VStack>

                    <HStack gap={2} align="center">
                      <Token label={`${series.total_bars} Sessions`} color="blue" />
                      <Token label={`${series.warmup_period} Warm-up Bars`} color="orange" />
                      <Token label={`${series.valid_bars} Valid Bars`} color="green" />
                      {latestState && latestState !== "warmup" && (
                        <Token
                          label={
                            latestState === "bullish_cross"
                              ? "Bullish Crossover"
                              : latestState === "bearish_cross"
                                ? "Bearish Crossover"
                                : latestState === "bullish_above"
                                  ? "Fast > Slow"
                                  : latestState === "bearish_below"
                                    ? "Fast < Slow"
                                    : "Neutral"
                          }
                          color={
                            latestState.includes("bullish")
                              ? "green"
                              : latestState.includes("bearish")
                                ? "red"
                                : "grey"
                          }
                        />
                      )}
                    </HStack>
                  </HStack>

                  {/* SVG Chart */}
                  <VStack
                    gap={2}
                    style={{
                      border: "1px solid var(--color-border)",
                      borderRadius: "var(--radius-element)",
                      backgroundColor: "var(--color-background-surface)",
                      padding: "16px",
                    }}
                  >
                    <HStack justify="between" align="center">
                      <Text weight="bold">Time-Series Alignment & Trend Preview</Text>
                      <HStack gap={3} align="center">
                        <HStack gap={1} align="center">
                          <StatusDot variant="neutral" label="Price" />
                          <Text type="supporting">Close Price</Text>
                        </HStack>
                        <HStack gap={1} align="center">
                          <StatusDot variant="primary" label="Fast" />
                          <Text type="supporting">
                            Fast Trend ({String(series.parameters.fast_period || series.parameters.period || "")})
                          </Text>
                        </HStack>
                        {series.parameters.slow_period && (
                          <HStack gap={1} align="center">
                            <StatusDot variant="purple" label="Slow" />
                            <Text type="supporting">
                              Slow Trend ({String(series.parameters.slow_period)})
                            </Text>
                          </HStack>
                        )}
                        <HStack gap={1} align="center">
                          <StatusDot variant="warning" label="Warm-up" />
                          <Text type="supporting">Warm-up Window</Text>
                        </HStack>
                      </HStack>
                    </HStack>

                    <svg
                      viewBox={`0 0 ${chartPoints.width} ${chartPoints.height}`}
                      style={{ width: "100%", height: "280px", overflow: "visible" }}
                      onMouseLeave={() => setHoveredIndex(null)}
                    >
                      {/* Grid Lines */}
                      <line
                        x1={chartPoints.chartMargin.left}
                        y1={chartPoints.chartMargin.top}
                        x2={chartPoints.width - chartPoints.chartMargin.right}
                        y2={chartPoints.chartMargin.top}
                        stroke="var(--color-border)"
                        strokeDasharray="3 3"
                      />
                      <line
                        x1={chartPoints.chartMargin.left}
                        y1={chartPoints.chartMargin.top + chartPoints.innerH / 2}
                        x2={chartPoints.width - chartPoints.chartMargin.right}
                        y2={chartPoints.chartMargin.top + chartPoints.innerH / 2}
                        stroke="var(--color-border)"
                        strokeDasharray="3 3"
                      />
                      <line
                        x1={chartPoints.chartMargin.left}
                        y1={chartPoints.chartMargin.top + chartPoints.innerH}
                        x2={chartPoints.width - chartPoints.chartMargin.right}
                        y2={chartPoints.chartMargin.top + chartPoints.innerH}
                        stroke="var(--color-border)"
                      />

                      {/* Y-Axis Labels */}
                      <text
                        x={chartPoints.chartMargin.left - 8}
                        y={chartPoints.chartMargin.top + 4}
                        textAnchor="end"
                        fontSize="11"
                        fill="var(--color-text-supporting)"
                      >
                        ${chartPoints.yMax.toFixed(2)}
                      </text>
                      <text
                        x={chartPoints.chartMargin.left - 8}
                        y={chartPoints.chartMargin.top + chartPoints.innerH / 2 + 4}
                        textAnchor="end"
                        fontSize="11"
                        fill="var(--color-text-supporting)"
                      >
                        ${((chartPoints.yMax + chartPoints.yMin) / 2).toFixed(2)}
                      </text>
                      <text
                        x={chartPoints.chartMargin.left - 8}
                        y={chartPoints.chartMargin.top + chartPoints.innerH + 4}
                        textAnchor="end"
                        fontSize="11"
                        fill="var(--color-text-supporting)"
                      >
                        ${chartPoints.yMin.toFixed(2)}
                      </text>

                      {/* Warmup Period Shading */}
                      {chartPoints.warmupWidth > 0 && (
                        <rect
                          x={chartPoints.chartMargin.left}
                          y={chartPoints.chartMargin.top}
                          width={chartPoints.warmupWidth}
                          height={chartPoints.innerH}
                          fill="var(--color-background-wash, rgba(255, 255, 255, 0.04))"
                          stroke="var(--color-border)"
                          strokeDasharray="2 2"
                        />
                      )}

                      {/* Series Lines */}
                      <path
                        d={chartPoints.pricePath}
                        fill="none"
                        stroke="var(--color-text-supporting)"
                        strokeWidth="1.5"
                      />
                      {chartPoints.slowMaPath && (
                        <path
                          d={chartPoints.slowMaPath}
                          fill="none"
                          stroke="var(--color-icon-purple)"
                          strokeWidth="2.5"
                        />
                      )}
                      {chartPoints.fastMaPath && (
                        <path
                          d={chartPoints.fastMaPath}
                          fill="none"
                          stroke="var(--color-icon-blue)"
                          strokeWidth="2.5"
                        />
                      )}

                      {/* Interactive Hover Vertical Line */}
                      {hoveredIndex !== null && (
                        <line
                          x1={chartPoints.getX(hoveredIndex)}
                          y1={chartPoints.chartMargin.top}
                          x2={chartPoints.getX(hoveredIndex)}
                          y2={chartPoints.chartMargin.top + chartPoints.innerH}
                          stroke="var(--color-border)"
                          strokeDasharray="2 2"
                        />
                      )}

                      {/* Transparent Hover Hit Zones */}
                      {series.points.map((_, idx) => {
                        const x = chartPoints.getX(idx);
                        const step = chartPoints.innerW / Math.max(1, series.points.length - 1);
                        return (
                          <rect
                            key={idx}
                            x={x - step / 2}
                            y={chartPoints.chartMargin.top}
                            width={step}
                            height={chartPoints.innerH}
                            fill="transparent"
                            style={{ cursor: "pointer" }}
                            onMouseEnter={() => setHoveredIndex(idx)}
                          />
                        );
                      })}
                    </svg>

                    {/* Active Hover Inspection Info */}
                    {activeHoveredPoint && (
                      <HStack
                        justify="between"
                        align="center"
                        style={{
                          backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.08))",
                          padding: "8px 12px",
                          borderRadius: "var(--radius-inner)",
                        }}
                      >
                        <HStack gap={3}>
                          <Text weight="bold">Date: {activeHoveredPoint.session_date}</Text>
                          <Text>Price: ${activeHoveredPoint.price.toFixed(2)}</Text>
                          {activeHoveredPoint.values["fast_ma"] !== undefined && (
                            <Text>
                              Fast MA:{" "}
                              {activeHoveredPoint.values["fast_ma"] !== null
                                ? `$${Number(activeHoveredPoint.values["fast_ma"]).toFixed(2)}`
                                : "None (Warm-up)"}
                            </Text>
                          )}
                          {activeHoveredPoint.values["slow_ma"] !== undefined && (
                            <Text>
                              Slow MA:{" "}
                              {activeHoveredPoint.values["slow_ma"] !== null
                                ? `$${Number(activeHoveredPoint.values["slow_ma"]).toFixed(2)}`
                                : "None (Warm-up)"}
                            </Text>
                          )}
                          {activeHoveredPoint.values["spread"] !== undefined &&
                            activeHoveredPoint.values["spread"] !== null && (
                              <Text weight="medium">
                                Spread: {Number(activeHoveredPoint.values["spread"]) > 0 ? "+" : ""}
                                ${Number(activeHoveredPoint.values["spread"]).toFixed(2)}
                              </Text>
                            )}
                        </HStack>

                        <Token
                          label={activeHoveredPoint.is_warmup ? "Warm-up" : "Valid Observation"}
                          color={activeHoveredPoint.is_warmup ? "orange" : "green"}
                        />
                      </HStack>
                    )}
                  </VStack>

                  {/* Aligned Output Table */}
                  <VStack gap={2}>
                    <Heading level={3}>Aligned Indicator Output Series</Heading>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Session Date</TableHeaderCell>
                          <TableHeaderCell>Close Price</TableHeaderCell>
                          <TableHeaderCell>Fast Trend</TableHeaderCell>
                          {series.parameters.slow_period && <TableHeaderCell>Slow Trend</TableHeaderCell>}
                          {series.parameters.slow_period && <TableHeaderCell>Spread</TableHeaderCell>}
                          <TableHeaderCell>Indicator State</TableHeaderCell>
                          <TableHeaderCell>Provenance / Alignment</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {series.points.map((pt, idx) => {
                          const fastVal = (pt.values["fast_ma"] ?? pt.values["sma"] ?? pt.values["ema"]) as
                            | number
                            | null
                            | undefined;
                          const slowVal = pt.values["slow_ma"] as number | null | undefined;
                          const spreadVal = pt.values["spread"] as number | null | undefined;
                          const stateStr = String(pt.values["state"] || "");

                          return (
                            <TableRow key={idx}>
                              <TableCell>
                                <Text weight="medium">{pt.session_date}</Text>
                              </TableCell>
                              <TableCell>${pt.price.toFixed(2)}</TableCell>
                              <TableCell>
                                {fastVal !== null && fastVal !== undefined ? (
                                  `$${fastVal.toFixed(2)}`
                                ) : (
                                  <Text type="supporting">None (warmup)</Text>
                                )}
                              </TableCell>
                              {series.parameters.slow_period && (
                                <TableCell>
                                  {slowVal !== null && slowVal !== undefined ? (
                                    `$${slowVal.toFixed(2)}`
                                  ) : (
                                    <Text type="supporting">None (warmup)</Text>
                                  )}
                                </TableCell>
                              )}
                              {series.parameters.slow_period && (
                                <TableCell>
                                  {spreadVal !== null && spreadVal !== undefined ? (
                                    <Text
                                      weight="medium"
                                      style={{
                                        color:
                                          spreadVal > 0
                                            ? "var(--color-text-green)"
                                            : spreadVal < 0
                                              ? "var(--color-text-red)"
                                              : "inherit",
                                      }}
                                    >
                                      {spreadVal > 0 ? "+" : ""}
                                      ${spreadVal.toFixed(2)}
                                    </Text>
                                  ) : (
                                    <Text type="supporting">—</Text>
                                  )}
                                </TableCell>
                              )}
                              <TableCell>
                                {pt.is_warmup ? (
                                  <Token label="Warm-up" color="orange" />
                                ) : stateStr === "bullish_cross" ? (
                                  <Token label="Bullish Cross" color="green" />
                                ) : stateStr === "bearish_cross" ? (
                                  <Token label="Bearish Cross" color="red" />
                                ) : stateStr === "bullish_above" ? (
                                  <Token label="Bullish Above" color="green" />
                                ) : stateStr === "bearish_below" ? (
                                  <Token label="Bearish Below" color="red" />
                                ) : (
                                  <Token label="Neutral" color="grey" />
                                )}
                              </TableCell>
                              <TableCell>
                                <HStack gap={1} align="center">
                                  <StatusDot variant={pt.is_warmup ? "warning" : "success"} />
                                  <Text type="supporting">
                                    {pt.is_warmup ? "Incomplete lookback" : "Aligned eligible bar"}
                                  </Text>
                                </HStack>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </VStack>
                </VStack>
              ) : (
                <EmptyState
                  title="No Indicator Series Calculated"
                  description="Select an available dataset version, target symbol, and parameters in the right panel, then click Calculate Indicator to preview the time-aligned series."
                  primaryAction={{
                    label: "Calculate Default Indicator",
                    onClick: handleCalculate,
                  }}
                />
              )
            ) : activeWorkspaceTab === "strategies" ? (
              <VStack gap={4}>
                {strategyError && (
                  <Banner status="error" title="Strategy Error">
                    {strategyError}
                  </Banner>
                )}

                {strategySaveSuccess && (
                  <Banner status="success" title="Revision Saved">
                    {strategySaveSuccess}
                  </Banner>
                )}

                {strategyResult ? (
                  <VStack gap={4}>
                    <HStack justify="between" align="center" style={{ flexWrap: "wrap" }}>
                      <VStack gap={0}>
                        <Heading level={3}>
                          {currentStrategy?.display_name || strategyResult.strategy_name} ({strategyResult.symbol})
                        </Heading>
                        <Text type="supporting">
                          Desired target weights emitted at the decision time; never an order or a fill.
                        </Text>
                      </VStack>

                      <HStack gap={2} align="center">
                        {strategyResult.targets.map((target, idx) => (
                          <Token
                            key={idx}
                            label={target.weight > 0 ? "LONG (100%)" : "FLAT (0%)"}
                            color={target.weight > 0 ? "green" : "purple"}
                          />
                        ))}
                        {strategyResult.indicator_name && (
                          <Token label={strategyResult.indicator_name} color="blue" />
                        )}
                      </HStack>
                    </HStack>

                    {strategyResult.targets.map((target, idx) => (
                      <Card key={idx} padding={4}>
                        <VStack gap={3}>
                          <HStack justify="between" align="center">
                            <Text weight="bold">Target Weight</Text>
                            <Token
                              label={`${(target.weight * 100).toFixed(0)}%`}
                              color={target.weight > 0 ? "green" : "purple"}
                            />
                          </HStack>
                          <Text>{target.rationale}</Text>
                          <HStack gap={3} style={{ flexWrap: "wrap" }}>
                            <Text type="supporting">Decision time: {target.decision_time}</Text>
                            {target.indicator_state && (
                              <Text type="supporting">Indicator state: {target.indicator_state}</Text>
                            )}
                            {strategyResult.latest_session_date && (
                              <Text type="supporting">Latest eligible session: {strategyResult.latest_session_date}</Text>
                            )}
                          </HStack>
                        </VStack>
                      </Card>
                    ))}

                    {project && (
                      <HStack justify="end">
                        <Button
                          label="Save Revision"
                          variant="secondary"
                          size="sm"
                          onClick={handleSaveStrategyRevision}
                          isLoading={isSaving}
                        />
                      </HStack>
                    )}
                  </VStack>
                ) : (
                  <EmptyState
                    title="No Strategy Evaluated"
                    description="Select a strategy, dataset, and symbol in the right panel, then click Evaluate Strategy to emit target weights and rationale."
                    primaryAction={{
                      label: "Evaluate Strategy",
                      onClick: handleEvaluateStrategy,
                    }}
                  />
                )}
              </VStack>
            ) : activeWorkspaceTab === "predictive" ? (
              <VStack gap={4}>
                {predictiveError && (
                  <Banner status="error" title="Predictive Model Error">
                    {predictiveError}
                  </Banner>
                )}

                {predictiveResult ? (
                  <VStack gap={4}>
                    <HStack justify="between" align="center" style={{ flexWrap: "wrap" }}>
                      <VStack gap={0}>
                        <Heading level={3}>
                          {predictiveResult.display_name} ({predictiveResult.symbol})
                        </Heading>
                        <Text type="supporting">
                          Python calculated the fitted artifact and timestamped predictions. The browser only displays the result.
                        </Text>
                        <Text type="supporting">
                          {predictiveResult.status === "completed"
                            ? `Saved Run ${predictiveResult.run_id ?? "(ID unavailable)"} completed ${predictiveResult.completed_at ?? "at an unknown time"}.`
                            : "Preview Run only; select a Project to persist this result."}
                        </Text>
                      </VStack>
                      <HStack gap={2} align="center" style={{ flexWrap: "wrap" }}>
                        <Token
                          label={predictiveResult.status === "completed" ? "Saved Run" : "Preview Run"}
                          color={predictiveResult.status === "completed" ? "green" : "orange"}
                        />
                        <Token
                          label={`${predictiveResult.artifact.training_observations} Training Observations`}
                          color="blue"
                        />
                        <Token
                          label={`In-Sample R² ${predictiveResult.metrics.in_sample_r2.toFixed(3)}`}
                          color="green"
                        />
                        <Token
                          label={`Chronological ${predictiveResult.evaluation_mode} evaluation`}
                          color="orange"
                        />
                      </HStack>
                    </HStack>

                    <Card padding={4}>
                      <VStack gap={3}>
                        <Heading level={4}>Predictive Model Contract</Heading>
                        <Text>{predictiveResult.description}</Text>
                        <HStack gap={3} style={{ flexWrap: "wrap" }}>
                          <Text type="supporting">Target: {predictiveResult.target}</Text>
                          <Text type="supporting">Horizon: {predictiveResult.horizon} session</Text>
                          <Text type="supporting">Feature: {predictiveResult.features.join(", ")}</Text>
                          <Text type="supporting">Training window: {predictiveResult.training_window}</Text>
                        </HStack>
                        <Text type="supporting">
                          Training range: {predictiveResult.training_start} to {predictiveResult.training_end}. Model revision: {predictiveResult.model_revision || "preview"}.
                        </Text>
                      </VStack>
                    </Card>

                    <VStack gap={3}>
                      <Heading level={4}>Chronological Evaluation</Heading>
                      <Text type="supporting">
                        The initial fit uses training observations only. Each later fold uses only data available before its target date. Metric scope: training is in-sample; validation and out-of-sample are held out. Warnings: none recorded.
                      </Text>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Period</TableHeaderCell>
                            <TableHeaderCell>Target Dates</TableHeaderCell>
                            <TableHeaderCell>Feature Dates</TableHeaderCell>
                            <TableHeaderCell>Observations</TableHeaderCell>
                            <TableHeaderCell>RMSE</TableHeaderCell>
                            <TableHeaderCell>R²</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(predictiveResult.splits ?? []).map((split) => {
                            const metrics = (predictiveResult.period_metrics ?? []).find(
                              (item) => item.period === split.period,
                            )?.metrics;
                            return (
                              <TableRow key={split.period}>
                                <TableCell>{split.period === "test" ? "out-of-sample" : split.period}</TableCell>
                                <TableCell>{split.start} to {split.end}</TableCell>
                                <TableCell>{split.feature_start} to {split.feature_end}</TableCell>
                                <TableCell>{split.observations}</TableCell>
                                <TableCell>{metrics?.rmse?.toFixed(6) ?? "Not available"}</TableCell>
                                <TableCell>{metrics?.r2?.toFixed(3) ?? "Not available"}</TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </VStack>

                    {(predictiveResult.folds ?? []).length > 0 && (
                      <VStack gap={3}>
                        <Heading level={4}>Walk-forward Folds</Heading>
                        <Text type="supporting">
                          Each fold stores the fitted artifact, the prediction it produced, and the
                          training observations eligible before that prediction session.
                        </Text>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHeaderCell>Fold</TableHeaderCell>
                              <TableHeaderCell>Period</TableHeaderCell>
                              <TableHeaderCell>Prediction Session</TableHeaderCell>
                              <TableHeaderCell>Target Date</TableHeaderCell>
                              <TableHeaderCell>Training Range</TableHeaderCell>
                              <TableHeaderCell>Observations</TableHeaderCell>
                              <TableHeaderCell>MAE</TableHeaderCell>
                              <TableHeaderCell>RMSE</TableHeaderCell>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {predictiveResult.folds.map((fold) => (
                              <TableRow key={fold.fold_index}>
                                <TableCell>{fold.fold_index}</TableCell>
                                <TableCell>{fold.period === "test" ? "out-of-sample" : fold.period}</TableCell>
                                <TableCell>{fold.prediction_session_date}</TableCell>
                                <TableCell>{fold.target_date ?? "Not available"}</TableCell>
                                <TableCell>{fold.training_start} to {fold.training_end}</TableCell>
                                <TableCell>{fold.training_observations}</TableCell>
                                <TableCell>{fold.metrics["mae"]?.toFixed(6) ?? "Not available"}</TableCell>
                                <TableCell>{fold.metrics["rmse"]?.toFixed(6) ?? "Not available"}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </VStack>
                    )}

                    <VStack gap={2}>
                      <Heading level={4}>Timestamped Model Output</Heading>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Session Date</TableHeaderCell>
                            <TableHeaderCell>Period</TableHeaderCell>
                            <TableHeaderCell>Target Date</TableHeaderCell>
                            <TableHeaderCell>Momentum Feature</TableHeaderCell>
                            <TableHeaderCell>Predicted Next Return</TableHeaderCell>
                            <TableHeaderCell>Actual Next Return</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {predictiveResult.predictions.map((prediction) => (
                            <TableRow key={prediction.session_date}>
                              <TableCell>{prediction.session_date}</TableCell>
                              <TableCell>
                                {prediction.period === "test"
                                  ? "out-of-sample"
                                  : prediction.period ?? "Not labelled"}
                              </TableCell>
                              <TableCell>{prediction.target_date ?? "Not available"}</TableCell>
                              <TableCell>{prediction.feature_value.toFixed(6)}</TableCell>
                              <TableCell>
                                <Token label={prediction.predicted_value.toFixed(6)} color="blue" />
                              </TableCell>
                              <TableCell>
                                {prediction.actual_target == null
                                  ? "Not available yet"
                                  : prediction.actual_target.toFixed(6)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </VStack>
                  </VStack>
                ) : (
                  <EmptyState
                    title="No Predictive Model Run"
                    description="Select a real Market Dataset and symbol, inspect the typed model contract, then run the Predictive Model. A Project saves the fitted artifact and predictions automatically."
                    primaryAction={{
                      label: project ? "Run & Save Model" : "Run Model",
                      onClick: handleRunPredictiveModel,
                    }}
                  />
                )}
              </VStack>
            ) : null}
          </VStack>
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={360}
          hasDivider
          isScrollable
          label={
            activeWorkspaceTab === "strategies"
              ? "Strategy Parameters"
              : activeWorkspaceTab === "predictive"
                ? "Predictive Model Parameters"
                : "Indicator Parameters"
          }
        >
          <VStack gap={4} style={{ padding: "16px" }}>
            <Heading level={3}>Configuration</Heading>

            {/* Dataset Selection */}
            <VStack gap={1}>
              <Text weight="medium">Market Dataset</Text>
              {datasets.length > 0 ? (
                <Selector
                  label="Dataset Version"
                  isLabelHidden
                  options={datasets.map((d) => ({
                    value: d.id,
                    label: `${d.source} (${d.row_count} rows)`,
                  }))}
                  value={selectedDatasetId}
                  onChange={(val) => setSelectedDatasetId(val)}
                />
              ) : (
                <Text type="supporting">No datasets found. Import data in Market Data tab.</Text>
              )}
            </VStack>

            {/* Target Symbol */}
            <VStack gap={1}>
              <Text weight="medium">Target Security Symbol</Text>
              <TextInput
                label="Security Symbol"
                isLabelHidden
                value={selectedSymbol}
                onChange={(val) => setSelectedSymbol(typeof val === "string" ? val.toUpperCase() : "")}
                placeholder="e.g. AAPL"
              />
            </VStack>

            {activeWorkspaceTab === "strategies" ? (
              <>
                {/* Strategy Selection */}
                <VStack gap={1}>
                  <Text weight="medium">Strategy Technique</Text>
                  <Selector
                    label="Strategy"
                    isLabelHidden
                    options={strategies.map((strat) => ({
                      value: strat.name,
                      label: strat.display_name,
                    }))}
                    value={selectedStrategyName}
                    onChange={(val) => setSelectedStrategyName(val)}
                  />
                  {currentStrategy && (
                    <Text type="supporting">{currentStrategy.description}</Text>
                  )}
                </VStack>

                {/* Strategy Parameters */}
                {currentStrategy && currentStrategy.parameters.length > 0 && (
                  <VStack gap={3}>
                    <Heading level={4}>Parameters</Heading>
                    {currentStrategy.parameters.map((param) => {
                      if (param.options && param.options.length > 0) {
                        return (
                          <VStack gap={1} key={param.name}>
                            <Text weight="medium">{param.name}</Text>
                            <SegmentedControl
                              label={param.name}
                              value={String(strategyParams[param.name] || param.default)}
                              onChange={(val) =>
                                setStrategyParams((prev) => ({ ...prev, [param.name]: val }))
                              }
                            >
                              {param.options.map((opt) => (
                                <SegmentedControlItem key={opt} value={opt} label={opt.toUpperCase()} />
                              ))}
                            </SegmentedControl>
                            <Text type="supporting">{param.description}</Text>
                          </VStack>
                        );
                      }

                      return (
                        <VStack gap={1} key={param.name}>
                          <TextInput
                            label={`${param.name} (${param.param_type})`}
                            value={String(strategyParams[param.name] ?? param.default ?? "")}
                            onChange={(val) =>
                              setStrategyParams((prev) => ({
                                ...prev,
                                [param.name]: typeof val === "string" ? val : "",
                              }))
                            }
                          />
                          <Text type="supporting">
                            {param.description}
                            {param.min_value !== null ? ` (min: ${param.min_value}` : ""}
                            {param.max_value !== null ? `, max: ${param.max_value})` : param.min_value !== null ? ")" : ""}
                          </Text>
                        </VStack>
                      );
                    })}
                  </VStack>
                )}

                <Button
                  label="Evaluate Strategy"
                  variant="primary"
                  onClick={handleEvaluateStrategy}
                  isLoading={isStrategyLoading}
                />
              </>
            ) : activeWorkspaceTab === "predictive" ? (
              <>
                <VStack gap={1}>
                  <Text weight="medium">Predictive Model Technique</Text>
                  <Selector
                    label="Predictive Model"
                    isLabelHidden
                    options={predictiveModels.map((model) => ({
                      value: model.name,
                      label: model.display_name,
                    }))}
                    value={selectedPredictiveModelName}
                    onChange={(val) => setSelectedPredictiveModelName(val)}
                  />
                  {currentPredictiveModel && (
                    <Text type="supporting">{currentPredictiveModel.description}</Text>
                  )}
                </VStack>

                {currentPredictiveModel && (
                  <VStack gap={3}>
                    <Heading level={4}>Typed Parameters</Heading>
                    {currentPredictiveModel.parameters.map((parameter) => {
                      if (parameter.options && parameter.options.length > 0) {
                        return (
                          <VStack gap={1} key={parameter.name}>
                            <Text weight="medium">{parameter.name}</Text>
                            <SegmentedControl
                              label={parameter.name}
                              value={String(predictiveParams[parameter.name] ?? parameter.default)}
                              onChange={(val) =>
                                setPredictiveParams((previous) => ({
                                  ...previous,
                                  [parameter.name]: val,
                                }))
                              }
                            >
                              {parameter.options.map((option) => (
                                <SegmentedControlItem
                                  key={option}
                                  value={option}
                                  label={option.toUpperCase()}
                                />
                              ))}
                            </SegmentedControl>
                            <Text type="supporting">{parameter.description}</Text>
                          </VStack>
                        );
                      }

                      return (
                        <VStack gap={1} key={parameter.name}>
                          <TextInput
                            label={`${parameter.name} (${parameter.param_type})`}
                            value={String(predictiveParams[parameter.name] ?? parameter.default ?? "")}
                            onChange={(val) =>
                              setPredictiveParams((previous) => ({
                                ...previous,
                                [parameter.name]: typeof val === "string" ? val : "",
                              }))
                            }
                          />
                          <Text type="supporting">
                            {parameter.description}
                            {parameter.min_value !== null ? ` (min: ${parameter.min_value}` : ""}
                            {parameter.max_value !== null
                              ? `, max: ${parameter.max_value})`
                              : parameter.min_value !== null
                                ? ")"
                                : ""}
                          </Text>
                        </VStack>
                      );
                    })}
                  </VStack>
                )}

                {currentPredictiveModel && (
                  <Card padding={3}>
                    <VStack gap={2}>
                      <Text weight="bold">Declared Contract</Text>
                      <Text type="supporting">Target: {currentPredictiveModel.target}</Text>
                      <Text type="supporting">Horizon: {currentPredictiveModel.horizon} session</Text>
                      <Text type="supporting">
                        Features: {currentPredictiveModel.features.join(", ")}
                      </Text>
                      <Text type="supporting">
                        Output: {currentPredictiveModel.output_meaning}
                      </Text>
                    </VStack>
                  </Card>
                )}

                <Button
                  label={project ? "Run & Save Model" : "Run Model"}
                  variant="primary"
                  onClick={handleRunPredictiveModel}
                  isLoading={isPredictiveLoading}
                />
              </>
            ) : (
              <>
                {/* Indicator Selection */}
                <VStack gap={1}>
                  <Text weight="medium">Indicator Technique</Text>
                  <Selector
                    label="Indicator"
                    isLabelHidden
                    options={indicators.map((ind) => ({
                      value: ind.name,
                      label: ind.display_name,
                    }))}
                    value={selectedIndicatorName}
                    onChange={(val) => setSelectedIndicatorName(val)}
                  />
                  {currentIndicator && (
                    <Text type="supporting">{currentIndicator.description}</Text>
                  )}
                </VStack>

                {/* Dynamic Typed Parameters */}
                {currentIndicator && currentIndicator.parameters.length > 0 && (
                  <VStack gap={3}>
                    <Heading level={4}>Parameters</Heading>
                    {currentIndicator.parameters.map((param) => {
                      if (param.options && param.options.length > 0) {
                        return (
                          <VStack gap={1} key={param.name}>
                            <Text weight="medium">{param.name}</Text>
                            <SegmentedControl
                              label={param.name}
                              value={String(paramValues[param.name] || param.default)}
                              onChange={(val) =>
                                setParamValues((prev) => ({ ...prev, [param.name]: val }))
                              }
                            >
                              {param.options.map((opt) => (
                                <SegmentedControlItem key={opt} value={opt} label={opt.toUpperCase()} />
                              ))}
                            </SegmentedControl>
                            <Text type="supporting">{param.description}</Text>
                          </VStack>
                        );
                      }

                      return (
                        <VStack gap={1} key={param.name}>
                          <TextInput
                            label={`${param.name} (${param.param_type})`}
                            value={String(paramValues[param.name] ?? param.default ?? "")}
                            onChange={(val) =>
                              setParamValues((prev) => ({
                                ...prev,
                                [param.name]: typeof val === "string" ? val : "",
                              }))
                            }
                          />
                          <Text type="supporting">
                            {param.description}
                            {param.min_value !== null ? ` (min: ${param.min_value}` : ""}
                            {param.max_value !== null ? `, max: ${param.max_value})` : param.min_value !== null ? ")" : ""}
                          </Text>
                        </VStack>
                      );
                    })}
                  </VStack>
                )}

                <Button
                  label="Calculate Preview"
                  variant="primary"
                  onClick={handleCalculate}
                  isLoading={isLoading}
                />
              </>
            )}
          </VStack>
        </LayoutPanel>
      }
    >
      {/* Save Revision Dialog */}
      <Dialog
        isOpen={isSaveOpen}
        onOpenChange={(open) => {
          if (!open) setIsSaveOpen(false);
        }}
      >
        <DialogHeader
          title="Save Indicator Definition Revision"
          subtitle="Save an immutable sequentially numbered definition revision (e.g. v1, v2) to the active project."
        />
        <VStack gap={4} style={{ padding: "16px" }}>
          <VStack gap={1}>
            <TextInput
              label="Definition Name"
              value={definitionName}
              onChange={(val) => setDefinitionName(typeof val === "string" ? val : "")}
              placeholder="e.g. aapl_trend_crossover"
              isRequired
            />
            <Text type="supporting">
              Definition will record indicator '{series?.indicator_name}', symbol '{series?.symbol}', parameters, and dataset provenance.
            </Text>
          </VStack>

          <HStack justify="end" gap={2}>
            <Button
              label="Cancel"
              variant="secondary"
              onClick={() => setIsSaveOpen(false)}
              isDisabled={isSaving}
            />
            <Button
              label="Save Revision"
              variant="primary"
              onClick={handleSaveRevision}
              isLoading={isSaving}
            />
          </HStack>
        </VStack>
      </Dialog>
    </Layout>
  );
}
