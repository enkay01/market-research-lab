import { useEffect, useMemo, useState } from "react";
import {
  Banner,
  Button,
  Card,
  Divider,
  EmptyState,
  Grid,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  LayoutPanel,
  SegmentedControl,
  SegmentedControlItem,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  TextInput,
  Token,
  VStack,
} from "@astryxdesign/core";
import { Selector } from "@astryxdesign/core/Selector";
import {
  api,
  type BacktestResult,
  type CoverageResponse,
  type EquityPoint,
  type Project,
  type Security,
  type StrategyMetadata,
} from "../api/client";
import { OptionsBacktestView } from "./OptionsBacktestView";

interface BacktestViewProps {
  project?: Project;
}

function percentage(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function decimalFormat(value: number | null | undefined, digits: number = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

function currencyFormat(value: number | null | undefined, currency: string = "USD"): string {
  if (value === null || value === undefined) return "—";
  return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function signedCurrencyFormat(value: number | null | undefined, currency: string = "USD"): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${currencyFormat(value, currency)}`;
}

interface BacktestCostsManifest {
  commission?: number;
  slippage?: number;
  borrow_fees?: number;
  cash_interest?: number;
  portfolio_impact?: Record<string, number>;
  [key: string]: number | Record<string, number> | undefined;
}

interface BacktestManifestData {
  costs?: BacktestCostsManifest;
  dataset_versions?: string[];
  [key: string]: number | string | string[] | BacktestCostsManifest | undefined;
}

function manifestCost(result: BacktestResult | null, key: string): number {
  if (!result?.manifest) return 0;
  // SAFETY: Manifest payload is parsed into BacktestManifestData structure
  const manifest = result.manifest as BacktestManifestData;
  const costs = manifest.costs;
  if (!costs) return 0;
  const value = costs[key];
  return Number.isFinite(value) ? Number(value) : 0;
}

function manifestNumber(result: BacktestResult | null, key: string): number {
  if (!result?.manifest) return 0;
  // SAFETY: Manifest payload is parsed into BacktestManifestData structure
  const manifest = result.manifest as BacktestManifestData;
  const value = manifest[key];
  return Number.isFinite(value) ? Number(value) : 0;
}

function manifestPortfolioImpact(result: BacktestResult | null, key: string): number {
  if (!result?.manifest) return 0;
  // SAFETY: Manifest payload is parsed into BacktestManifestData structure
  const manifest = result.manifest as BacktestManifestData;
  const impact = manifest.costs?.portfolio_impact;
  if (!impact) return 0;
  const value = impact[key];
  return Number.isFinite(value) ? Number(value) : 0;
}

function KpiCard({
  label,
  value,
  subtext,
  valueColor,
}: {
  label: string;
  value: string;
  subtext?: string;
  valueColor?: string;
}) {
  return (
    <Card padding={3} style={{ flex: 1, minWidth: "160px" }}>
      <VStack gap={1}>
        <Text type="supporting">{label}</Text>
        <Heading level={3} style={{ color: valueColor }}>
          {value}
        </Heading>
        {subtext && <Text type="supporting">{subtext}</Text>}
      </VStack>
    </Card>
  );
}

function EquityDrawdownChart({
  equityCurve,
  drawdownCurve,
  benchmarkCurve,
}: {
  equityCurve?: EquityPoint[];
  drawdownCurve?: EquityPoint[];
  benchmarkCurve?: EquityPoint[];
}) {
  if (!equityCurve || equityCurve.length < 2) {
    return null;
  }

  const width = 800;
  const height = 200;
  const padding = 20;

  const allEquities = [
    ...equityCurve.map((p) => p.equity),
    ...(benchmarkCurve || []).map((p) => p.equity),
  ];
  const minEquity = Math.min(...allEquities);
  const maxEquity = Math.max(...allEquities);
  const rangeEquity = maxEquity - minEquity || 1;

  const equityPoints = equityCurve
    .map((p, i) => {
      const x = padding + (i / (equityCurve.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((p.equity - minEquity) / rangeEquity) * (height - 2 * padding);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const benchPoints =
    benchmarkCurve && benchmarkCurve.length === equityCurve.length
      ? benchmarkCurve
          .map((p, i) => {
            const x = padding + (i / (benchmarkCurve.length - 1)) * (width - 2 * padding);
            const y = height - padding - ((p.equity - minEquity) / rangeEquity) * (height - 2 * padding);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(" ")
      : "";

  const minDd =
    drawdownCurve && drawdownCurve.length > 0
      ? Math.min(...drawdownCurve.map((p) => p.drawdown))
      : 0;

  const ddPoints = (drawdownCurve || [])
    .map((p, i) => {
      const x = padding + (i / (drawdownCurve!.length - 1)) * (width - 2 * padding);
      const y =
        minDd < 0
          ? padding + (p.drawdown / minDd) * (height - 2 * padding)
          : padding;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <Card padding={4}>
      <VStack gap={3}>
        <HStack justify="between" align="center">
          <Heading level={3}>Portfolio &amp; Benchmark Equity Curve (Point-in-Time)</Heading>
          <HStack gap={2}>
            <Token label={`High: ${currencyFormat(maxEquity)}`} color="green" />
            <Token label={`Low: ${currencyFormat(minEquity)}`} color="purple" />
          </HStack>
        </HStack>

        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{
            width: "100%",
            height: "200px",
            overflow: "visible",
          }}
        >
          {/* Zero baseline */}
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="var(--color-border)"
            strokeWidth="1"
            strokeDasharray="4 4"
          />

          {/* Benchmark Polyline if available */}
          {benchPoints && (
            <polyline
              fill="none"
              stroke="var(--color-icon-orange)"
              strokeWidth="2"
              strokeDasharray="4 2"
              points={benchPoints}
            />
          )}

          {/* Portfolio Equity Polyline */}
          <polyline
            fill="none"
            stroke="var(--color-icon-blue)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={equityPoints}
          />

          {/* Drawdown Polyline if available */}
          {ddPoints && (
            <polyline
              fill="none"
              stroke="var(--color-icon-red)"
              strokeWidth="1.5"
              strokeDasharray="3 3"
              points={ddPoints}
            />
          )}
        </svg>
        <HStack justify="between">
          <Text type="supporting">{equityCurve[0]?.session_date}</Text>
          <HStack gap={3}>
            <Text type="supporting" style={{ color: "var(--color-text-blue)" }}>
              — Portfolio Equity
            </Text>
            {benchPoints && (
              <Text type="supporting" style={{ color: "var(--color-text-orange)" }}>
                - - Benchmark
              </Text>
            )}
            <Text type="supporting" style={{ color: "var(--color-text-red)" }}>
              --- Max Drawdown
            </Text>
          </HStack>
          <Text type="supporting">{equityCurve[equityCurve.length - 1]?.session_date}</Text>
        </HStack>
      </VStack>
    </Card>
  );
}

export function BacktestView({ project }: BacktestViewProps) {
  const [simulationType, setSimulationType] = useState<"standard" | "options">(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("mode") === "options" ? "options" : "standard";
  });
  const [activeTab, setActiveTab] = useState<
    "overview" | "trades" | "fills" | "ledger" | "rejections" | "manifest" | "compare"
  >("overview");

  // Datasets & Securities
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [, setSecurities] = useState<Security[]>([]);
  const [universeInput, setUniverseInput] = useState<string>("");
  const [benchmarkInput, setBenchmarkInput] = useState<string>("SPY");

  // Strategy & Execution Specification Inputs
  const [strategyName, setStrategyName] = useState<string>("long_flat_moving_average");
  const [strategyRevision, setStrategyRevision] = useState<string>("long_flat_moving_average:v1");
  const [startDate, setStartDate] = useState<string>("2024-01-02");
  const [endDate, setEndDate] = useState<string>("2024-06-28");
  const [startingCash, setStartingCash] = useState<string>("100000");
  const [fastPeriod, setFastPeriod] = useState<string>("2");
  const [slowPeriod, setSlowPeriod] = useState<string>("4");
  const [maType, setMaType] = useState<"sma" | "ema">("sma");
  const [commissionBps, setCommissionBps] = useState<string>("5.0");
  const [slippageBps, setSlippageBps] = useState<string>("2.0");
  const [allowShorting, setAllowShorting] = useState<boolean>(true);
  const [borrowFeeBps, setBorrowFeeBps] = useState<string>("0.0");
  const [cashInterestBps, setCashInterestBps] = useState<string>("0.0");
  const [unavailableBorrowInput, setUnavailableBorrowInput] = useState<string>("");
  const [maxLeverage, setMaxLeverage] = useState<string>("1.0");
  const [marginRequirement, setMarginRequirement] = useState<string>("100.0");
  const [maintenanceMargin, setMaintenanceMargin] = useState<string>("25.0");
  const [leverageMode, setLeverageMode] = useState<"reject" | "constrain">("reject");

  // Execution & Result state
  const [availableStrategies, setAvailableStrategies] = useState<StrategyMetadata[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoadingDatasets, setIsLoadingDatasets] = useState(true);
  const [currentResult, setCurrentResult] = useState<BacktestResult | null>(null);
  const [savedRuns, setSavedRuns] = useState<BacktestResult[]>([]);
  const [compareRunIds, setCompareRunIds] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [bannerType, setBannerType] = useState<"info" | "warning">("info");

  // Load datasets and securities
  useEffect(() => {
    async function initData() {
      setIsLoadingDatasets(true);
      try {
        const [dsList, secList, stratList] = await Promise.all([
          api.listDatasets(),
          api.listSecurities({ limit: 200 }),
          api.listStrategies(),
        ]);
        const dailyBarDatasets = dsList.filter((d: any) => d.dataset_type !== "corporate_actions");
        setDatasets(dailyBarDatasets);
        setSecurities(secList);
        setAvailableStrategies(stratList);
        if (stratList.length > 0) {
          setStrategyName(stratList[0].name);
          setStrategyRevision(`${stratList[0].name}:v1`);
        }
        if (dailyBarDatasets.length > 0) {
          const validDs = dailyBarDatasets.find((d: any) => (d.row_count ?? d.total_bars ?? 0) > 0) || dailyBarDatasets[0];
          setSelectedDatasetId(validDs.id);
          if (validDs.coverage_start && validDs.coverage_end) {
            setStartDate(validDs.coverage_start);
            setEndDate(validDs.coverage_end);
          }
        }
      } catch (err: unknown) {
        setMessage(err instanceof Error ? err.message : "Failed to load datasets.");
        setBannerType("warning");
      } finally {
        setIsLoadingDatasets(false);
      }
    }
    initData();
  }, []);

  // Reload saved runs for project
  const loadSavedRuns = () => {
    if (!project) return;
    api
      .listBacktests(project.id)
      .then((runs) => {
        setSavedRuns(runs);
        if (runs.length > 0 && !currentResult) {
          setCurrentResult(runs[0]);
        }
        if (runs.length >= 2 && compareRunIds.length === 0) {
          setCompareRunIds([runs[0].run_id || "", runs[1].run_id || ""]);
        } else if (runs.length === 1 && compareRunIds.length === 0) {
          setCompareRunIds([runs[0].run_id || ""]);
        }
      })
      .catch((cause: unknown) => {
        setMessage(cause instanceof Error ? cause.message : "Could not load saved Backtest runs.");
        setBannerType("warning");
      });
  };

  useEffect(() => {
    loadSavedRuns();
  }, [project?.id]);

  // When selected dataset changes, inspect dates
  const handleDatasetChange = async (dsId: string) => {
    setSelectedDatasetId(dsId);
    const match = datasets.find((d: any) => d.id === dsId);
    if (match?.coverage_start && match?.coverage_end) {
      setStartDate(match.coverage_start);
      setEndDate(match.coverage_end);
    } else {
      try {
        const preview = await api.getPreview(dsId);
        if (preview && preview.length > 0) {
          const first = preview[0];
          const last = preview[preview.length - 1];
          if (first?.date && last?.date) {
            setStartDate(String(first.date));
            setEndDate(String(last.date));
          }
        }
      } catch {
        // Keep defaults
      }
    }
  };

  // Parse symbols from input
  const symbolsList = useMemo(() => {
    return universeInput
      .split(/[,;\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0);
  }, [universeInput]);

  // Run Backtest
  async function handleRunBacktest() {
    if (!project) {
      setMessage("Open or create a Project before executing Backtest simulations.");
      setBannerType("warning");
      return;
    }
    if (!selectedDatasetId) {
      setMessage("Select a dataset version before running.");
      setBannerType("warning");
      return;
    }

    setIsRunning(true);
    setMessage(null);
    try {
      const unavailableList = unavailableBorrowInput
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);

      const res = await api.runBacktest(project.id, {
        strategy_name: strategyName,
        strategy_revision: strategyRevision,
        dataset_version_id: selectedDatasetId,
        symbols: symbolsList.length > 0 ? symbolsList : undefined,
        benchmark_symbol: benchmarkInput.trim() ? benchmarkInput.trim().toUpperCase() : undefined,
        start_date: startDate,
        end_date: endDate,
        starting_cash: parseFloat(startingCash) || 100000.0,
        price_field: "close",
        parameters: {
          fast_period: parseInt(fastPeriod, 10) || 2,
          slow_period: parseInt(slowPeriod, 10) || 4,
          ma_type: maType,
        },
        execution: {
          schedule: "daily",
          commission_rate: (parseFloat(commissionBps) || 0) / 10000,
          slippage_rate: (parseFloat(slippageBps) || 0) / 10000,
          allow_shorting: allowShorting,
          borrow_fee_rate: (parseFloat(borrowFeeBps) || 0) / 10000,
          cash_interest_rate: (parseFloat(cashInterestBps) || 0) / 10000,
          unavailable_borrow: unavailableList,
          max_leverage: parseFloat(maxLeverage) || 1.0,
          margin_requirement: (parseFloat(marginRequirement) || 100.0) / 100.0,
          maintenance_margin: (parseFloat(maintenanceMargin) || 25.0) / 100.0,
          leverage_mode: leverageMode,
        },
      });
      setCurrentResult(res);
      setMessage(`Backtest Run ${res.run_id} executed and persisted successfully.`);
      setBannerType("info");
      loadSavedRuns();
    } catch (cause: unknown) {
      setMessage(cause instanceof Error ? cause.message : "Backtest execution failed.");
      setBannerType("warning");
    } finally {
      setIsRunning(false);
    }
  }

  const currentRunId = currentResult?.run_id;

  const comparisonRuns = useMemo(() => {
    return savedRuns.filter((r) => r.run_id && compareRunIds.includes(r.run_id));
  }, [savedRuns, compareRunIds]);

  const toggleCompareRun = (runId: string) => {
    setCompareRunIds((curr) =>
      curr.includes(runId) ? curr.filter((id) => id !== runId) : [...curr, runId]
    );
  };

  const universeDisplay = useMemo(() => {
    // SAFETY: Specification contains optional universe list or legacy security_id string
    const spec = currentResult?.specification as { universe?: string[]; security_id?: string } | undefined;
    const rawU = spec?.universe;
    if (Array.isArray(rawU) && rawU.length > 0) {
      return rawU.join(", ");
    }
    return spec?.security_id || "—";
  }, [currentResult]);

  if (simulationType === "options") {
    return <OptionsBacktestView project={project} onBackToStandard={() => setSimulationType("standard")} />;
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Backtest Simulation Engine</Heading>
              <Token label={`Strategy: ${strategyName}`} color="purple" />
              {project && <Token label={`Project: ${project.name}`} color="purple" />}
              {currentRunId && <Token label={`Run: ${currentRunId.slice(0, 8)}`} color="blue" />}
            </HStack>

            <HStack gap={2}>
              <Button
                label="Options Credit Spreads (Alpaca)"
                variant="secondary"
                size="sm"
                onClick={() => setSimulationType("options")}
              />
              {currentRunId && project && (
                <>
                  <Button
                    label="Export HTML"
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      window.open(
                        api.getBacktestExportUrl(project.id, currentRunId, "html"),
                        "_blank",
                      );
                    }}
                  />
                  <Button
                    label="Export CSV"
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      window.open(
                        api.getBacktestExportUrl(project.id, currentRunId, "csv"),
                        "_blank",
                      );
                    }}
                  />
                  <Button
                    label="Export JSON"
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      window.open(
                        api.getBacktestExportUrl(project.id, currentRunId, "json"),
                        "_blank",
                      );
                    }}
                  />
                </>
              )}
              <Button
                label="Run Backtest"
                variant="primary"
                size="sm"
                onClick={handleRunBacktest}
                disabled={isRunning || isLoadingDatasets}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4} padding={2}>
        {/* Navigation Tabs */}
        <HStack gap={2}>
          <Button
            label="Overview & Chart"
            variant={activeTab === "overview" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("overview")}
          />
          <Button
            label={`Trades (${currentResult?.trades?.length ?? 0})`}
            variant={activeTab === "trades" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("trades")}
          />
          <Button
            label={`Fills (${currentResult?.fills?.length ?? 0})`}
            variant={activeTab === "fills" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("fills")}
          />
          <Button
            label={`Ledger (${currentResult?.ledger?.length ?? 0})`}
            variant={activeTab === "ledger" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("ledger")}
          />
          <Button
            label={`Rejections (${currentResult?.rejections?.length ?? 0})`}
            variant={activeTab === "rejections" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("rejections")}
          />
          <Button
            label="Manifest"
            variant={activeTab === "manifest" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("manifest")}
          />
          <Button
            label={`Compare Runs (${savedRuns.length})`}
            variant={activeTab === "compare" ? "primary" : "secondary"}
            size="sm"
            onClick={() => setActiveTab("compare")}
          />
        </HStack>

        {isLoadingDatasets ? (
          <Text type="supporting">Loading market datasets and securities...</Text>
        ) : (
          <VStack gap={4}>
            {message && (
              <Banner
                status={bannerType === "warning" ? "warning" : "info"}
                title={message}
              />
            )}

            {/* Simulation Parameters & Execution Setup */}
            <Card padding={4}>
              <VStack gap={4}>
                <Heading level={3}>Multi-Security Simulation Setup &amp; Parameters</Heading>

                {/* Section 1: Scope & Universe */}
                <VStack gap={2}>
                  <Text type="supporting" weight="bold">
                    1. Scope &amp; Target Strategy
                  </Text>
                  <Grid columns={{ minWidth: 200, repeat: "fit" }} gap={3}>
                    <Selector
                      label="Strategy"
                      value={strategyName}
                      onChange={(v) => {
                        const val = String(v);
                        setStrategyName(val);
                        setStrategyRevision(`${val}:v1`);
                      }}
                      options={availableStrategies.map((s) => ({
                        value: s.name,
                        label: s.display_name,
                      }))}
                    />
                    <Selector
                      label="Dataset Version"
                      value={selectedDatasetId}
                      onChange={handleDatasetChange}
                      options={datasets.map((d: any) => ({
                        value: d.id,
                        label: `${d.source || "Dataset"} — ${d.id.slice(0, 16)}... (${d.row_count ?? d.total_bars ?? 0} bars)`,
                      }))}
                      placeholder="Select market dataset"
                      hasSearch
                    />
                    <TextInput
                      label="Universe / Symbol Filter (Optional)"
                      value={universeInput}
                      onChange={(v) => setUniverseInput(String(v ?? ""))}
                      placeholder="All assets in dataset (leave empty)"
                      description="Leave empty to run strategy across all assets in dataset."
                    />
                    <TextInput
                      label="Benchmark (Optional)"
                      value={benchmarkInput}
                      onChange={(v) => setBenchmarkInput(String(v ?? ""))}
                    />
                    <TextInput
                      label="Start Date"
                      value={startDate}
                      onChange={(v) => setStartDate(String(v ?? ""))}
                    />
                    <TextInput
                      label="End Date"
                      value={endDate}
                      onChange={(v) => setEndDate(String(v ?? ""))}
                    />
                  </Grid>
                </VStack>

                <Divider />

                {/* Section 2: Execution Model & Trading Costs */}
                <VStack gap={2}>
                  <Text type="supporting" weight="bold">
                    2. Execution Model &amp; Trading Costs
                  </Text>
                  <Grid columns={{ minWidth: 200, repeat: "fit" }} gap={3}>
                    <TextInput
                      label="Starting Cash ($)"
                      value={startingCash}
                      onChange={(v) => setStartingCash(String(v ?? ""))}
                    />
                    <TextInput
                      label="Fast MA Period"
                      value={fastPeriod}
                      onChange={(v) => setFastPeriod(String(v ?? ""))}
                    />
                    <TextInput
                      label="Slow MA Period"
                      value={slowPeriod}
                      onChange={(v) => setSlowPeriod(String(v ?? ""))}
                    />
                    <Selector
                      label="Moving Average Type"
                      value={maType}
                      onChange={(v) => {
                        // SAFETY: Value is constrained by Selector options
                        setMaType(v as "sma" | "ema");
                      }}
                      options={[
                        { value: "sma", label: "Simple (SMA)" },
                        { value: "ema", label: "Exponential (EMA)" },
                      ]}
                    />
                    <TextInput
                      label="Commission (bps)"
                      value={commissionBps}
                      onChange={(v) => setCommissionBps(String(v ?? ""))}
                    />
                    <TextInput
                      label="Slippage (bps)"
                      value={slippageBps}
                      onChange={(v) => setSlippageBps(String(v ?? ""))}
                    />
                    <Selector
                      label="Allow Short Positions"
                      value={allowShorting ? "yes" : "no"}
                      onChange={(v) => setAllowShorting(v === "yes")}
                      options={[
                        { value: "yes", label: "Enabled (Long/Short)" },
                        { value: "no", label: "Disabled (Long-Only)" },
                      ]}
                    />
                    <TextInput
                      label="Borrow Fee (bps p.a.)"
                      value={borrowFeeBps}
                      onChange={(v) => setBorrowFeeBps(String(v ?? ""))}
                    />
                    <TextInput
                      label="Cash Interest (signed bps p.a.)"
                      value={cashInterestBps}
                      onChange={(v) => setCashInterestBps(String(v ?? ""))}
                    />
                    <TextInput
                      label="Unavailable Borrow (Symbols)"
                      value={unavailableBorrowInput}
                      onChange={(v) => setUnavailableBorrowInput(String(v ?? ""))}
                    />
                  </Grid>
                </VStack>

                <Divider />

                {/* Section 3: Leverage & Margin Limits */}
                <VStack gap={2}>
                  <Text type="supporting" weight="bold">
                    3. Leverage &amp; Margin Limits
                  </Text>
                  <Grid columns={{ minWidth: 200, repeat: "fit" }} gap={3}>
                    <TextInput
                      label="Max Leverage Limit (x)"
                      value={maxLeverage}
                      onChange={(v) => setMaxLeverage(String(v ?? ""))}
                    />
                    <Selector
                      label="Leverage Breach Mode"
                      value={leverageMode}
                      onChange={(v) => {
                        // SAFETY: Value is constrained by Selector options
                        setLeverageMode(v as "reject" | "constrain");
                      }}
                      options={[
                        { value: "reject", label: "Reject Orders" },
                        { value: "constrain", label: "Constrain / Scale" },
                      ]}
                    />
                    <TextInput
                      label="Margin Requirement (%)"
                      value={marginRequirement}
                      onChange={(v) => setMarginRequirement(String(v ?? ""))}
                    />
                    <TextInput
                      label="Maintenance Margin (%)"
                      value={maintenanceMargin}
                      onChange={(v) => setMaintenanceMargin(String(v ?? ""))}
                    />
                  </Grid>
                </VStack>
              </VStack>
            </Card>

            {/* Results Section */}
            {currentResult ? (
              <VStack gap={4}>
                {/* KPI Summary Tiles */}
                <HStack gap={3}>
                  <KpiCard
                    label="Total Return"
                    value={percentage(currentResult.metrics.total_return)}
                    subtext={`Benchmark Rel: ${percentage(currentResult.metrics.benchmark_relative_return)}`}
                    valueColor={
                      (currentResult.metrics.total_return ?? 0) >= 0
                        ? "var(--color-text-green)"
                        : "var(--color-text-red)"
                    }
                  />
                  <KpiCard
                    label="Annualized Return"
                    value={percentage(currentResult.metrics.annualized_return)}
                    subtext={`Volatility: ${percentage(currentResult.metrics.annualized_volatility)}`}
                  />
                  <KpiCard
                    label="Sharpe Ratio"
                    value={decimalFormat(currentResult.metrics.sharpe_ratio)}
                    subtext={`Sortino: ${decimalFormat(currentResult.metrics.sortino_ratio)}`}
                  />
                  <KpiCard
                    label="Max Drawdown"
                    value={percentage(currentResult.metrics.max_drawdown)}
                    subtext={`Calmar: ${decimalFormat(currentResult.metrics.calmar_ratio)}`}
                    valueColor="var(--color-text-red)"
                  />
                  <KpiCard
                    label="Win / Hit Rate"
                    value={
                      currentResult.metrics.hit_rate !== null &&
                      currentResult.metrics.hit_rate !== undefined
                        ? percentage(currentResult.metrics.hit_rate)
                        : "—"
                    }
                    subtext={`Turnover: ${decimalFormat(currentResult.metrics.turnover)}x`}
                  />
                  <KpiCard
                    label="Trades / Fills"
                    value={`${currentResult.metrics.num_trades} / ${currentResult.metrics.num_fills}`}
                    subtext={`Gross Exp: ${percentage(currentResult.metrics.gross_exposure)}`}
                  />
                </HStack>

                {/* Sub-tabs for deep replay analysis */}
                <SegmentedControl
                  value={activeTab}
                  onChange={(v) => {
                    // SAFETY: Value is constrained by SegmentedControlItem options
                    setActiveTab(
                      v as
                        | "overview"
                        | "trades"
                        | "fills"
                        | "ledger"
                        | "rejections"
                        | "manifest"
                        | "compare",
                    );
                  }}
                >
                  <SegmentedControlItem value="overview" label="Performance Overview" />
                  <SegmentedControlItem
                    value="trades"
                    label={`Closed Trades (${currentResult.trades?.length ?? 0})`}
                  />
                  <SegmentedControlItem
                    value="fills"
                    label={`Simulated Fills (${currentResult.fills?.length ?? 0})`}
                  />
                  <SegmentedControlItem
                    value="ledger"
                    label={`Daily Ledger (${currentResult.ledger?.length ?? 0})`}
                  />
                  <SegmentedControlItem
                    value="rejections"
                    label={`Rejections (${currentResult.rejections?.length ?? 0})`}
                  />
                  <SegmentedControlItem value="manifest" label="Manifest & Integrity" />
                  <SegmentedControlItem
                    value="compare"
                    label={`Compare Runs (${savedRuns.length})`}
                  />
                </SegmentedControl>

                {/* TAB: Overview */}
                {activeTab === "overview" && (
                  <VStack gap={4}>
                    {/* Time-series Equity & Benchmark & Drawdown Chart */}
                    <EquityDrawdownChart
                      equityCurve={currentResult.equity_curve}
                      drawdownCurve={currentResult.drawdown_curve}
                      benchmarkCurve={currentResult.benchmark_equity_curve}
                    />

                    <Heading level={3}>Execution Assumptions &amp; Strategy Specs</Heading>
                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Strategy &amp; Revision</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">{currentResult.strategy_revision}</Text>
                          </TableCell>
                          <TableCell>
                            <Text type="supporting">Universe</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">{universeDisplay}</Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Simulation Horizon</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {currentResult.specification?.start_date} to{" "}
                              {currentResult.specification?.end_date}
                            </Text>
                          </TableCell>
                          <TableCell>
                            <Text type="supporting">Starting Cash</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {currencyFormat(currentResult.specification?.starting_cash)}
                            </Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Benchmark</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">
                              {currentResult.specification?.benchmark_security_id || "None"}
                            </Text>
                          </TableCell>
                          <TableCell>
                            <Text type="supporting">Commission &amp; Slippage</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {(
                                ((currentResult.specification?.execution?.commission_rate ?? 0) *
                                10000)
                              ).toFixed(1)}{" "}
                              bps comm. /{" "}
                              {(
                                ((currentResult.specification?.execution?.slippage_rate ?? 0) * 10000)
                              ).toFixed(1)}{" "}
                              bps slip.
                            </Text>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>

                    <Heading level={3}>Cost Attribution</Heading>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Category</TableHeaderCell>
                          <TableHeaderCell>Amount</TableHeaderCell>
                          <TableHeaderCell>Portfolio Impact</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[
                          ["Commission", "total_commission", "commission"],
                          ["Slippage", "total_slippage", "slippage"],
                          ["Borrow Fees", "total_borrow_fees", "borrow_fees"],
                          ["Cash Interest", "total_cash_interest", "cash_interest"],
                          ["Net Costs", "total_costs", "net"],
                        ].map(([label, amountKey, impactKey]) => (
                          <TableRow key={label}>
                            <TableCell>
                              <Text weight={label === "Net Costs" ? "bold" : undefined}>{label}</Text>
                            </TableCell>
                            <TableCell>{signedCurrencyFormat(manifestCost(currentResult, amountKey))}</TableCell>
                            <TableCell>
                              <Text weight={label === "Net Costs" ? "bold" : undefined}>
                                {signedCurrencyFormat(manifestPortfolioImpact(currentResult, impactKey))}
                              </Text>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </VStack>
                )}

                {/* TAB: Trades */}
                {activeTab === "trades" && (
                  <VStack gap={3} style={{ width: "100%", overflowX: "auto" }}>
                    <Heading level={3}>Closed Round-Trip Trades</Heading>
                    {currentResult.trades && currentResult.trades.length > 0 ? (
                      <Table style={{ minWidth: "900px" }}>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Trade ID</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Security</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Entry Date</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Exit Date</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Entry Price</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Exit Price</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Quantity</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Total PnL</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Return (%)</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.trades.map((tr) => (
                            <TableRow key={tr.trade_id}>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Text weight="bold">{tr.trade_id}</Text>
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Token label={tr.security_id} color="blue" />
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{tr.entry_date}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{tr.exit_date}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(tr.entry_price)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(tr.exit_price)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{decimalFormat(tr.quantity, 2)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      tr.pnl >= 0
                                        ? "var(--color-text-green)"
                                        : "var(--color-text-red)",
                                  }}
                                >
                                  {currencyFormat(tr.pnl)}
                                </Text>
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      tr.return_pct >= 0
                                        ? "var(--color-text-green)"
                                        : "var(--color-text-red)",
                                  }}
                                >
                                  {percentage(tr.return_pct)}
                                </Text>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">
                        No round-trip trades completed during this Backtest run.
                      </Text>
                    )}
                  </VStack>
                )}

                {/* TAB: Fills */}
                {activeTab === "fills" && (
                  <VStack gap={3} style={{ width: "100%", overflowX: "auto" }}>
                    <Heading level={3}>Simulated Execution Fills</Heading>
                    {currentResult.fills && currentResult.fills.length > 0 ? (
                      <Table style={{ minWidth: "950px" }}>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Fill Date</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Side</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Security</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Quantity</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Fill Price</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Notional Value</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Commission</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Slippage Cost</TableHeaderCell>
                            <TableHeaderCell>Rationale</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.fills.map((fill, idx) => (
                            <TableRow key={idx}>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{fill.session_date}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Token
                                  label={fill.side.toUpperCase()}
                                  color={fill.side.toLowerCase() === "buy" ? "green" : "purple"}
                                />
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Text weight="bold">{fill.security_id}</Text>
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{decimalFormat(fill.quantity, 2)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(fill.price)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(fill.notional)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(fill.commission)}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{currencyFormat(fill.slippage_cost)}</TableCell>
                              <TableCell>
                                <Text type="supporting">{fill.rationale || "—"}</Text>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">No fills generated during this Backtest run.</Text>
                    )}
                  </VStack>
                )}

                {/* TAB: Ledger */}
                {activeTab === "ledger" && (
                  <VStack gap={3} style={{ width: "100%", overflowX: "auto" }}>
                    <Heading level={3}>Daily Mark-to-Market Portfolio Ledger</Heading>
                    {currentResult.ledger && currentResult.ledger.length > 0 ? (
                      <Table style={{ tableLayout: "auto", minWidth: "1200px" }}>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Session Date</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap", minWidth: "300px" }}>Positions (Shares &amp; Value)</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Cash Balance</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Total Position Value</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Portfolio Value</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Gross Exp</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Net Exp</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Borrow Fees</TableHeaderCell>
                            <TableHeaderCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>Cash Interest</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.ledger.map((row, idx) => {
                            const posEntries = Object.entries(row.positions || {});
                            return (
                              <TableRow key={idx}>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{row.session_date}</TableCell>
                                <TableCell style={{ maxWidth: "none", minWidth: "300px" }}>
                                  {posEntries.length > 0 ? (
                                    <HStack gap={2} wrap align="center">
                                      {posEntries.map(([sym, pos]) => (
                                        <HStack key={sym} gap={1} align="center">
                                          <Token
                                            label={sym}
                                            color={pos.shares > 0 ? "blue" : pos.shares < 0 ? "purple" : "default"}
                                          />
                                          <Text size="sm" type="supporting" style={{ whiteSpace: "nowrap" }}>
                                            {decimalFormat(pos.shares, 2)} sh ({currencyFormat(pos.position_value)})
                                          </Text>
                                        </HStack>
                                      ))}
                                    </HStack>
                                  ) : (
                                    <Text type="supporting">Flat</Text>
                                  )}
                                </TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{currencyFormat(row.cash)}</TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{currencyFormat(row.position_value)}</TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>
                                  <Text weight="bold">{currencyFormat(row.portfolio_value)}</Text>
                                </TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{percentage(row.gross_exposure)}</TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{percentage(row.net_exposure)}</TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{currencyFormat(row.borrow_fees ?? 0)}</TableCell>
                                <TableCell style={{ maxWidth: "none", whiteSpace: "nowrap" }}>{signedCurrencyFormat(row.cash_interest ?? 0)}</TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">Ledger is empty.</Text>
                    )}
                  </VStack>
                )}

                {/* TAB: Rejections */}
                {activeTab === "rejections" && (
                  <VStack gap={3} style={{ width: "100%", overflowX: "auto" }}>
                    <Heading level={3}>Constraint Rejections &amp; Margin Limits</Heading>
                    {currentResult.rejections && currentResult.rejections.length > 0 ? (
                      <Table style={{ minWidth: "950px" }}>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Session Date</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Security</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Rule</TableHeaderCell>
                            <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Requested Weight</TableHeaderCell>
                            <TableHeaderCell>Reason</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.rejections.map((rej, idx) => (
                            <TableRow key={idx}>
                              <TableCell style={{ whiteSpace: "nowrap" }}>{rej.session_date}</TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Token label={rej.security_id} color="blue" />
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                <Token
                                  label={rej.rule}
                                  color={
                                    rej.rule.includes("maintenance") || rej.rule.includes("margin")
                                      ? "purple"
                                      : rej.rule.includes("constrained")
                                      ? "green"
                                      : "blue"
                                  }
                                />
                              </TableCell>
                              <TableCell style={{ whiteSpace: "nowrap" }}>
                                {rej.requested_weight !== null && rej.requested_weight !== undefined
                                  ? `${(rej.requested_weight * 100).toFixed(1)}%`
                                  : "—"}
                              </TableCell>
                              <TableCell>
                                <Text>{rej.reason}</Text>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">
                        No constraint rejections or margin breaches occurred during this Backtest run.
                      </Text>
                    )}
                  </VStack>
                )}

                {/* TAB: Manifest */}
                {activeTab === "manifest" && (
                  <VStack gap={3}>
                    <Heading level={3}>Run Manifest &amp; Reproducibility Audit</Heading>
                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Run Identifier</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">{currentResult.run_id}</Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Strategy Revision</Text>
                          </TableCell>
                          <TableCell>
                            <Text>{currentResult.strategy_revision}</Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Universe</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">{universeDisplay}</Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Dataset Version IDs</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {
                                // SAFETY: Manifest may declare dataset_versions provenance array
                                (currentResult.manifest as { dataset_versions?: string[] } | undefined)?.dataset_versions?.join(", ") ||
                                currentResult.specification?.dataset_version_id ||
                                "N/A"
                              }
                            </Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Sample Verification</Text>
                          </TableCell>
                          <TableCell>
                            <Token
                              label="Out-of-sample (Point-in-time sequential simulation)"
                              color="green"
                            />
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Total Execution Costs</Text>
                          </TableCell>
                          <TableCell>
                            <Text>{signedCurrencyFormat(manifestCost(currentResult, "total_costs"))}</Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Cash Interest Periods</Text>
                          </TableCell>
                          <TableCell>
                            <Text>{manifestNumber(currentResult, "cash_interest_periods")}</Text>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </VStack>
                )}

                {/* TAB: Compare Runs */}
                {activeTab === "compare" && (
                  <VStack gap={4}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>Side-by-Side Run Comparison</Heading>
                      <HStack gap={2}>
                        {savedRuns.map((r) => {
                          const rId = r.run_id || "";
                          const isSelected = compareRunIds.includes(rId);
                          const specObj = r.specification;
                          const uDisplay = Array.isArray(specObj?.universe) && specObj.universe.length > 0
                            ? specObj.universe.join(",")
                            : specObj?.security_id || "Run";
                          return (
                            <Button
                              key={rId}
                              label={`${rId.slice(0, 8)} (${uDisplay})`}
                              variant={isSelected ? "primary" : "secondary"}
                              size="sm"
                              onClick={() => toggleCompareRun(rId)}
                            />
                          );
                        })}
                      </HStack>
                    </HStack>

                    {comparisonRuns.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Comparison Metric</TableHeaderCell>
                            {comparisonRuns.map((r) => (
                              <TableHeaderCell key={r.run_id}>
                                <VStack gap={0}>
                                  <Text weight="bold">{r.run_id?.slice(0, 8)}</Text>
                                  <Text type="supporting">
                                    {r.specification?.universe?.join(", ") ||
                                      r.specification?.security_id}
                                  </Text>
                                </VStack>
                              </TableHeaderCell>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          <TableRow>
                            <TableCell><Text type="supporting">Universe</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text weight="bold">
                                  {r.specification?.universe?.join(", ") ||
                                    r.specification?.security_id ||
                                    "—"}
                                </Text>
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Total Return</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      (r.metrics.total_return ?? 0) >= 0
                                        ? "var(--color-text-green)"
                                        : "var(--color-text-red)",
                                  }}
                                >
                                  {percentage(r.metrics.total_return)}
                                </Text>
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Benchmark Relative</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {percentage(r.metrics.benchmark_relative_return)}
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Annualized Return</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {percentage(r.metrics.annualized_return)}
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Sharpe Ratio</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text weight="bold">{decimalFormat(r.metrics.sharpe_ratio)}</Text>
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Sortino Ratio</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {decimalFormat(r.metrics.sortino_ratio)}
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Max Drawdown</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text weight="bold" style={{ color: "var(--color-text-red)" }}>
                                  {percentage(r.metrics.max_drawdown)}
                                </Text>
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Win / Hit Rate</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {percentage(r.metrics.hit_rate)}
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Turnover</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {decimalFormat(r.metrics.turnover)}x
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Trades / Fills</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {r.metrics.num_trades} / {r.metrics.num_fills}
                              </TableCell>
                            ))}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Fast / Slow MA</Text></TableCell>
                            {comparisonRuns.map((r) => {
                              // SAFETY: Specification parameters dictionary holds strategy config values
                              const params = r.specification?.parameters as Record<string, string | number | boolean | null> | undefined;
                              return (
                                <TableCell key={r.run_id}>
                                  {params?.fast_period ?? "—"} /{" "}
                                  {params?.slow_period ?? "—"}
                                </TableCell>
                              );
                            })}
                          </TableRow>
                          <TableRow>
                            <TableCell><Text type="supporting">Simulation Horizon</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text type="supporting">
                                  {r.specification?.start_date} to {r.specification?.end_date}
                                </Text>
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">
                        Select at least one Run above to view side-by-side comparison.
                      </Text>
                    )}
                  </VStack>
                )}
              </VStack>
            ) : (
              <EmptyState
                heading="No Backtest Executed"
                body="Configure your strategy parameters above and click 'Execute Backtest Run' to replay the simulation."
              />
            )}
          </VStack>
        )}
      </VStack>
    </LayoutContent>
      }
      end={
        <LayoutPanel width={320} hasDivider isScrollable label="Past Backtest Runs">
          <VStack gap={3} style={{ padding: "var(--spacing-3)" }}>
            <Heading level={3}>Project Run History</Heading>
            {savedRuns.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Run</TableHeaderCell>
                    <TableHeaderCell>Return</TableHeaderCell>
                    <TableHeaderCell>Sharpe</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {savedRuns.map((run) => {
                    const rId = run.run_id || "";
                    const specObj = run.specification;
                    const uDisplay = Array.isArray(specObj?.universe) && specObj.universe.length > 0
                      ? specObj.universe.join(", ")
                      : specObj?.security_id;
                    return (
                      <TableRow
                        key={rId}
                        onClick={() => setCurrentResult(run)}
                        style={{
                          cursor: "pointer",
                          background:
                            rId === currentRunId
                              ? "var(--color-background-wash)"
                              : undefined,
                        }}
                      >
                        <TableCell>
                          <VStack gap={0}>
                            <Text weight="bold">{rId.slice(0, 8)}</Text>
                            <Text type="supporting">{uDisplay}</Text>
                          </VStack>
                        </TableCell>
                        <TableCell>
                          <Text
                            weight="bold"
                            style={{
                              color:
                                (run.metrics.total_return ?? 0) >= 0
                                  ? "var(--color-text-green)"
                                  : "var(--color-text-red)",
                            }}
                          >
                            {percentage(run.metrics.total_return)}
                          </Text>
                        </TableCell>
                        <TableCell>{decimalFormat(run.metrics.sharpe_ratio)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <Text type="supporting">No previous Backtest runs saved in this project.</Text>
            )}
          </VStack>
        </LayoutPanel>
      }
    />
  );
}
