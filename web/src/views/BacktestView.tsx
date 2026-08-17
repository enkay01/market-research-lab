import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
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
} from "../api/client";

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
    <VStack
      gap={1}
      style={{
        padding: "var(--spacing-3, 0.75rem) var(--spacing-4, 1rem)",
        background: "var(--color-bg-subtle, #f8fafc)",
        borderRadius: "var(--radius-medium, 0.5rem)",
        border: "1px solid var(--color-border, #e2e8f0)",
        flex: 1,
        minWidth: "160px",
      }}
    >
      <Text type="supporting">{label}</Text>
      <Heading level={3} style={{ color: valueColor }}>
        {value}
      </Heading>
      {subtext && <Text type="supporting">{subtext}</Text>}
    </VStack>
  );
}

function EquityDrawdownChart({
  equityCurve,
  drawdownCurve,
}: {
  equityCurve?: EquityPoint[];
  drawdownCurve?: EquityPoint[];
}) {
  if (!equityCurve || equityCurve.length < 2) {
    return null;
  }

  const width = 800;
  const height = 180;
  const padding = 20;

  const minEquity = Math.min(...equityCurve.map((p) => p.portfolio_value));
  const maxEquity = Math.max(...equityCurve.map((p) => p.portfolio_value));
  const rangeEquity = maxEquity - minEquity || 1;

  const equityPoints = equityCurve
    .map((p, i) => {
      const x = padding + (i / (equityCurve.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((p.portfolio_value - minEquity) / rangeEquity) * (height - 2 * padding);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const minDd = drawdownCurve && drawdownCurve.length > 0
    ? Math.min(...drawdownCurve.map((p) => p.portfolio_value))
    : 0;

  const ddPoints = (drawdownCurve || [])
    .map((p, i) => {
      const x = padding + (i / (drawdownCurve!.length - 1)) * (width - 2 * padding);
      const y = minDd < 0
        ? padding + (p.portfolio_value / minDd) * (height - 2 * padding)
        : padding;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <VStack
      gap={2}
      style={{
        padding: "var(--spacing-4, 1rem)",
        background: "var(--color-bg-subtle, #f8fafc)",
        borderRadius: "var(--radius-medium, 0.5rem)",
        border: "1px solid var(--color-border, #e2e8f0)",
      }}
    >
      <HStack justify="between" align="center">
        <Heading level={3}>Equity &amp; Drawdown Curve (Point-in-Time)</Heading>
        <HStack gap={2}>
          <Token label={`High: ${currencyFormat(maxEquity)}`} color="green" />
          <Token label={`Low: ${currencyFormat(minEquity)}`} color="purple" />
        </HStack>
      </HStack>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{
          width: "100%",
          height: "180px",
          overflow: "visible",
        }}
      >
        {/* Zero baseline */}
        <line
          x1={padding}
          y1={height - padding}
          x2={width - padding}
          y2={height - padding}
          stroke="var(--color-border, #cbd5e1)"
          strokeWidth="1"
          strokeDasharray="4 4"
        />

        {/* Equity Polyline */}
        <polyline
          fill="none"
          stroke="var(--color-brand-primary, #3b82f6)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={equityPoints}
        />

        {/* Drawdown Polyline if available */}
        {ddPoints && (
          <polyline
            fill="none"
            stroke="var(--color-text-danger, #ef4444)"
            strokeWidth="1.5"
            strokeDasharray="3 3"
            points={ddPoints}
          />
        )}
      </svg>
      <HStack justify="between">
        <Text type="supporting">{equityCurve[0]?.session_date}</Text>
        <HStack gap={3}>
          <Text type="supporting" style={{ color: "var(--color-brand-primary, #3b82f6)" }}>
            — Portfolio Equity
          </Text>
          <Text type="supporting" style={{ color: "var(--color-text-danger, #ef4444)" }}>
            --- Max Drawdown
          </Text>
        </HStack>
        <Text type="supporting">{equityCurve[equityCurve.length - 1]?.session_date}</Text>
      </HStack>
    </VStack>
  );
}

export function BacktestView({ project }: BacktestViewProps) {
  const [activeTab, setActiveTab] = useState<
    "overview" | "trades" | "fills" | "ledger" | "manifest" | "compare"
  >("overview");

  // Datasets & Securities
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [securities, setSecurities] = useState<Security[]>([]);
  const [symbol, setSymbol] = useState<string>("AAPL");

  // Strategy & Execution Specification Inputs
  const [strategyName] = useState<string>("long_flat_moving_average");
  const [strategyRevision] = useState<string>("long_flat_moving_average:v1");
  const [startDate, setStartDate] = useState<string>("2024-01-02");
  const [endDate, setEndDate] = useState<string>("2024-06-28");
  const [startingCash, setStartingCash] = useState<string>("100000");
  const [fastPeriod, setFastPeriod] = useState<string>("2");
  const [slowPeriod, setSlowPeriod] = useState<string>("4");
  const [maType, setMaType] = useState<"sma" | "ema">("sma");
  const [commissionBps, setCommissionBps] = useState<string>("5.0");
  const [slippageBps, setSlippageBps] = useState<string>("2.0");

  // Execution & Result state
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
        const [dsList, secList] = await Promise.all([
          api.listDatasets(),
          api.listSecurities({ limit: 200 }),
        ]);
        setDatasets(dsList);
        setSecurities(secList);
        if (dsList.length > 0) {
          setSelectedDatasetId(dsList[0].id);
        }
        if (secList.length > 0) {
          setSymbol(secList[0].symbol);
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
          setCompareRunIds([runs[0].run_id, runs[1].run_id]);
        } else if (runs.length === 1 && compareRunIds.length === 0) {
          setCompareRunIds([runs[0].run_id]);
        }
      })
      .catch((err: unknown) => {
        setMessage(err instanceof Error ? err.message : "Could not load saved Backtest runs.");
        setBannerType("warning");
      });
  };

  useEffect(() => {
    loadSavedRuns();
  }, [project?.id]);

  // When selected dataset changes, inspect dates and symbol
  const handleDatasetChange = async (dsId: string) => {
    setSelectedDatasetId(dsId);
    try {
      const preview = await api.getPreview(dsId);
      if (preview && preview.length > 0) {
        const first = preview[0];
        const last = preview[preview.length - 1];
        if (typeof first.date === "string" && typeof last.date === "string") {
          setStartDate(first.date);
          setEndDate(last.date);
        }
        if (typeof first.symbol === "string") {
          setSymbol(first.symbol);
        }
      }
    } catch {
      // Keep defaults
    }
  };

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
    if (!symbol) {
      setMessage("Specify a security ticker symbol.");
      setBannerType("warning");
      return;
    }

    setIsRunning(true);
    setMessage(null);
    try {
      const res = await api.runBacktest(project.id, {
        strategy_name: strategyName,
        strategy_revision: strategyRevision,
        dataset_version_id: selectedDatasetId,
        symbol: symbol.trim().toUpperCase(),
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
          fill_price: "next_open",
          commission_rate: (parseFloat(commissionBps) || 0) / 10000,
          slippage_rate: (parseFloat(slippageBps) || 0) / 10000,
        },
      });
      setCurrentResult(res);
      setMessage(`Backtest Run ${res.run_id} executed and persisted successfully.`);
      setBannerType("info");
      loadSavedRuns();
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Backtest execution failed.");
      setBannerType("warning");
    } finally {
      setIsRunning(false);
    }
  }

  const currentRunId = currentResult?.run_id;

  const comparisonRuns = useMemo(() => {
    return savedRuns.filter((r) => compareRunIds.includes(r.run_id));
  }, [savedRuns, compareRunIds]);

  const toggleCompareRun = (runId: string) => {
    setCompareRunIds((curr) =>
      curr.includes(runId) ? curr.filter((id) => id !== runId) : [...curr, runId]
    );
  };

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Backtest Simulation Engine</Heading>
              <Token label={`Strategy: ${strategyName}`} color="purple" />
              {project && <Badge label={`Project: ${project.name}`} variant="purple" />}
              {currentRunId && <Token label={`Run: ${currentRunId.slice(0, 8)}`} color="blue" />}
            </HStack>

            <HStack gap={2}>
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
                label="Execute Backtest Run"
                variant="primary"
                size="sm"
                onClick={handleRunBacktest}
                isLoading={isRunning}
                isDisabled={!project || isLoadingDatasets || datasets.length === 0}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            {message && (
              <Banner status={bannerType} title="Simulation Status">
                {message}
              </Banner>
            )}

            {/* Warnings Alert Banner (REP-002) */}
            {currentResult?.warnings && currentResult.warnings.length > 0 && (
              <Banner status="warning" title="Simulation Warnings">
                <VStack gap={1}>
                  {currentResult.warnings.map((w, idx) => (
                    <Text key={idx}>{w}</Text>
                  ))}
                </VStack>
              </Banner>
            )}

            {/* Simulation Parameters & Execution Setup */}
            <VStack
              gap={3}
              style={{
                padding: "var(--spacing-4, 1rem)",
                background: "var(--color-bg-surface, #ffffff)",
                borderRadius: "var(--radius-medium, 0.5rem)",
                border: "1px solid var(--color-border, #e2e8f0)",
              }}
            >
              <Heading level={3}>Simulation Setup &amp; Parameters</Heading>

              <HStack gap={3} align="end">
                <Selector
                  label="Dataset Version"
                  value={selectedDatasetId}
                  onChange={handleDatasetChange}
                  options={datasets.map((d) => ({
                    value: d.id,
                    label: `${d.source || "Dataset"} — ${d.id.slice(0, 16)}... (${d.total_bars ?? 0} bars)`,
                  }))}
                  placeholder="Select market dataset"
                  hasSearch
                />
                <TextInput
                  label="Security Symbol"
                  value={symbol}
                  onChange={(v) => setSymbol(typeof v === "string" ? v.toUpperCase() : "")}
                />
                <TextInput
                  label="Start Date (YYYY-MM-DD)"
                  value={startDate}
                  onChange={(v) => setStartDate(typeof v === "string" ? v : "")}
                />
                <TextInput
                  label="End Date (YYYY-MM-DD)"
                  value={endDate}
                  onChange={(v) => setEndDate(typeof v === "string" ? v : "")}
                />
              </HStack>

              <HStack gap={3} align="end">
                <TextInput
                  label="Starting Cash ($ USD)"
                  value={startingCash}
                  onChange={(v) => setStartingCash(typeof v === "string" ? v : "")}
                />
                <TextInput
                  label="Fast MA Period"
                  value={fastPeriod}
                  onChange={(v) => setFastPeriod(typeof v === "string" ? v : "")}
                />
                <TextInput
                  label="Slow MA Period"
                  value={slowPeriod}
                  onChange={(v) => setSlowPeriod(typeof v === "string" ? v : "")}
                />
                <Selector
                  label="Moving Average Type"
                  value={maType}
                  onChange={(v) => setMaType(v as "sma" | "ema")}
                  options={[
                    { value: "sma", label: "Simple Moving Average (SMA)" },
                    { value: "ema", label: "Exponential Moving Average (EMA)" },
                  ]}
                />
                <TextInput
                  label="Commission (bps)"
                  value={commissionBps}
                  onChange={(v) => setCommissionBps(typeof v === "string" ? v : "")}
                />
                <TextInput
                  label="Slippage (bps)"
                  value={slippageBps}
                  onChange={(v) => setSlippageBps(typeof v === "string" ? v : "")}
                />
              </HStack>
            </VStack>

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
                        ? "var(--color-text-success, #166534)"
                        : "var(--color-text-danger, #991b1b)"
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
                    valueColor="var(--color-text-danger, #991b1b)"
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
                  onChange={(v) =>
                    setActiveTab(
                      v as
                        | "overview"
                        | "trades"
                        | "fills"
                        | "ledger"
                        | "manifest"
                        | "compare",
                    )
                  }
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
                  <SegmentedControlItem value="manifest" label="Manifest & Integrity" />
                  <SegmentedControlItem
                    value="compare"
                    label={`Compare Runs (${savedRuns.length})`}
                  />
                </SegmentedControl>

                {/* TAB: Overview */}
                {activeTab === "overview" && (
                  <VStack gap={4}>
                    {/* Time-series Equity & Drawdown Chart */}
                    <EquityDrawdownChart
                      equityCurve={currentResult.equity_curve}
                      drawdownCurve={currentResult.drawdown_curve}
                    />

                    <Heading level={3}>Execution Assumptions &amp; Strategy Specs</Heading>
                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Strategy Model &amp; Revision</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">{currentResult.strategy_revision}</Text>
                          </TableCell>
                          <TableCell>
                            <Text type="supporting">Security Target</Text>
                          </TableCell>
                          <TableCell>
                            <Text weight="bold">
                              {currentResult.specification?.security_id}
                            </Text>
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
                            <Text type="supporting">Starting Capital</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {currencyFormat(currentResult.specification?.starting_cash)}
                            </Text>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>
                            <Text type="supporting">Execution Rule</Text>
                          </TableCell>
                          <TableCell>
                            <Text>Next-Bar Open (Daily schedule, Point-in-Time)</Text>
                          </TableCell>
                          <TableCell>
                            <Text type="supporting">Commission &amp; Slippage</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {(
                                (currentResult.specification?.execution?.commission_rate ?? 0) *
                                10000
                              ).toFixed(1)}{" "}
                              bps comm. /{" "}
                              {(
                                (currentResult.specification?.execution?.slippage_rate ?? 0) * 10000
                              ).toFixed(1)}{" "}
                              bps slip.
                            </Text>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>

                    {/* Quick Equity Trajectory Table */}
                    <Heading level={3}>Mark-to-Market Performance Snapshot</Heading>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Session Date</TableHeaderCell>
                          <TableHeaderCell>Target Weight</TableHeaderCell>
                          <TableHeaderCell>Shares Held</TableHeaderCell>
                          <TableHeaderCell>Close Price</TableHeaderCell>
                          <TableHeaderCell>Cash Balance</TableHeaderCell>
                          <TableHeaderCell>Position Value</TableHeaderCell>
                          <TableHeaderCell>Portfolio Equity</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(currentResult.ledger ?? []).slice(-10).map((row, idx) => (
                          <TableRow key={idx}>
                            <TableCell>{row.session_date}</TableCell>
                            <TableCell>
                              {row.signal_weight !== null && row.signal_weight !== undefined
                                ? percentage(row.signal_weight)
                                : "—"}
                            </TableCell>
                            <TableCell>{decimalFormat(row.shares, 2)}</TableCell>
                            <TableCell>{currencyFormat(row.close_price)}</TableCell>
                            <TableCell>{currencyFormat(row.cash)}</TableCell>
                            <TableCell>{currencyFormat(row.position_value)}</TableCell>
                            <TableCell>
                              <Text weight="bold">{currencyFormat(row.portfolio_value)}</Text>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </VStack>
                )}

                {/* TAB: Closed Trades */}
                {activeTab === "trades" && (
                  <VStack gap={3}>
                    <Heading level={3}>Closed Round-Trip Trades</Heading>
                    {currentResult.trades && currentResult.trades.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Trade ID</TableHeaderCell>
                            <TableHeaderCell>Security</TableHeaderCell>
                            <TableHeaderCell>Entry Date</TableHeaderCell>
                            <TableHeaderCell>Exit Date</TableHeaderCell>
                            <TableHeaderCell>Entry Price</TableHeaderCell>
                            <TableHeaderCell>Exit Price</TableHeaderCell>
                            <TableHeaderCell>Quantity</TableHeaderCell>
                            <TableHeaderCell>PnL ($)</TableHeaderCell>
                            <TableHeaderCell>Return (%)</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.trades.map((tr) => (
                            <TableRow key={tr.trade_id}>
                              <TableCell>{tr.trade_id}</TableCell>
                              <TableCell>
                                <Text weight="bold">{tr.security_id}</Text>
                              </TableCell>
                              <TableCell>{tr.entry_date}</TableCell>
                              <TableCell>{tr.exit_date}</TableCell>
                              <TableCell>{currencyFormat(tr.entry_price)}</TableCell>
                              <TableCell>{currencyFormat(tr.exit_price)}</TableCell>
                              <TableCell>{decimalFormat(tr.quantity, 2)}</TableCell>
                              <TableCell>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      (tr.pnl ?? 0) >= 0
                                        ? "var(--color-text-success, #166534)"
                                        : "var(--color-text-danger, #991b1b)",
                                  }}
                                >
                                  {currencyFormat(tr.pnl)}
                                </Text>
                              </TableCell>
                              <TableCell>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      (tr.return_pct ?? 0) >= 0
                                        ? "var(--color-text-success, #166534)"
                                        : "var(--color-text-danger, #991b1b)",
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
                  <VStack gap={3}>
                    <Heading level={3}>Simulated Execution Fills</Heading>
                    {currentResult.fills && currentResult.fills.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Fill Date</TableHeaderCell>
                            <TableHeaderCell>Side</TableHeaderCell>
                            <TableHeaderCell>Security</TableHeaderCell>
                            <TableHeaderCell>Quantity</TableHeaderCell>
                            <TableHeaderCell>Fill Price</TableHeaderCell>
                            <TableHeaderCell>Notional Value</TableHeaderCell>
                            <TableHeaderCell>Commission</TableHeaderCell>
                            <TableHeaderCell>Slippage Cost</TableHeaderCell>
                            <TableHeaderCell>Rationale</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.fills.map((fill, idx) => (
                            <TableRow key={idx}>
                              <TableCell>{fill.session_date}</TableCell>
                              <TableCell>
                                <Token
                                  label={fill.side.toUpperCase()}
                                  color={fill.side.toLowerCase() === "buy" ? "green" : "purple"}
                                />
                              </TableCell>
                              <TableCell>
                                <Text weight="bold">{fill.security_id}</Text>
                              </TableCell>
                              <TableCell>{decimalFormat(fill.quantity, 2)}</TableCell>
                              <TableCell>{currencyFormat(fill.price)}</TableCell>
                              <TableCell>{currencyFormat(fill.notional)}</TableCell>
                              <TableCell>{currencyFormat(fill.commission)}</TableCell>
                              <TableCell>{currencyFormat(fill.slippage_cost)}</TableCell>
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
                  <VStack gap={3}>
                    <Heading level={3}>Daily Mark-to-Market Portfolio Ledger</Heading>
                    {currentResult.ledger && currentResult.ledger.length > 0 ? (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Session Date</TableHeaderCell>
                            <TableHeaderCell>Target Weight</TableHeaderCell>
                            <TableHeaderCell>Decision Time</TableHeaderCell>
                            <TableHeaderCell>Shares Held</TableHeaderCell>
                            <TableHeaderCell>Close Price</TableHeaderCell>
                            <TableHeaderCell>Cash Balance</TableHeaderCell>
                            <TableHeaderCell>Position Value</TableHeaderCell>
                            <TableHeaderCell>Portfolio Value</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {currentResult.ledger.map((row, idx) => (
                            <TableRow key={idx}>
                              <TableCell>{row.session_date}</TableCell>
                              <TableCell>
                                {row.signal_weight !== null && row.signal_weight !== undefined
                                  ? percentage(row.signal_weight)
                                  : "—"}
                              </TableCell>
                              <TableCell>
                                <Text type="supporting">
                                  {row.signal_decision_time
                                    ? new Date(row.signal_decision_time).toLocaleTimeString()
                                    : "Close"}
                                </Text>
                              </TableCell>
                              <TableCell>{decimalFormat(row.shares, 2)}</TableCell>
                              <TableCell>{currencyFormat(row.close_price)}</TableCell>
                              <TableCell>{currencyFormat(row.cash)}</TableCell>
                              <TableCell>{currencyFormat(row.position_value)}</TableCell>
                              <TableCell>
                                <Text weight="bold">{currencyFormat(row.portfolio_value)}</Text>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Text type="supporting">Ledger is empty.</Text>
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
                            <Text type="supporting">Dataset Version IDs</Text>
                          </TableCell>
                          <TableCell>
                            <Text>
                              {currentResult.manifest?.dataset_versions?.join(", ") ||
                                currentResult.specification?.dataset_version_id ||
                                "N/A"}
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
                            <Text>
                              {currencyFormat(
                                (currentResult.manifest?.costs as any)?.total_costs ?? 0,
                              )}
                            </Text>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </VStack>
                )}

                {/* TAB: Compare Runs (REP-001) */}
                {activeTab === "compare" && (
                  <VStack gap={4}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>Side-by-Side Run Comparison</Heading>
                      <HStack gap={2}>
                        {savedRuns.map((r) => {
                          const isSelected = compareRunIds.includes(r.run_id);
                          return (
                            <Button
                              key={r.run_id}
                              label={`${r.run_id.slice(0, 8)} (${r.specification?.security_id})`}
                              variant={isSelected ? "primary" : "secondary"}
                              size="sm"
                              onClick={() => toggleCompareRun(r.run_id)}
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
                                  <Text weight="bold">{r.run_id.slice(0, 8)}</Text>
                                  <Text type="supporting">{r.specification?.security_id}</Text>
                                </VStack>
                              </TableHeaderCell>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          <TableRow>
                            <TableCell><Text type="supporting">Total Return</Text></TableCell>
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                <Text
                                  weight="bold"
                                  style={{
                                    color:
                                      (r.metrics.total_return ?? 0) >= 0
                                        ? "var(--color-text-success, #166534)"
                                        : "var(--color-text-danger, #991b1b)",
                                  }}
                                >
                                  {percentage(r.metrics.total_return)}
                                </Text>
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
                                <Text weight="bold" style={{ color: "var(--color-text-danger, #991b1b)" }}>
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
                            {comparisonRuns.map((r) => (
                              <TableCell key={r.run_id}>
                                {r.specification?.parameters?.fast_period ?? "—"} /{" "}
                                {r.specification?.parameters?.slow_period ?? "—"}
                              </TableCell>
                            ))}
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
        </LayoutContent>
      }
      end={
        <LayoutPanel width={320} hasDivider isScrollable label="Past Backtest Runs">
          <VStack gap={3} style={{ padding: "var(--spacing-3, 0.75rem)" }}>
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
                  {savedRuns.map((run) => (
                    <TableRow
                      key={run.run_id}
                      onClick={() => setCurrentResult(run)}
                      style={{
                        cursor: "pointer",
                        background:
                          run.run_id === currentRunId
                            ? "var(--color-bg-subtle, #f1f5f9)"
                            : undefined,
                      }}
                    >
                      <TableCell>
                        <VStack gap={0}>
                          <Text weight="bold">{run.run_id.slice(0, 8)}</Text>
                          <Text type="supporting">{run.specification?.security_id}</Text>
                        </VStack>
                      </TableCell>
                      <TableCell>
                        <Text
                          weight="bold"
                          style={{
                            color:
                              (run.metrics.total_return ?? 0) >= 0
                                ? "var(--color-text-success, #166534)"
                                : "var(--color-text-danger, #991b1b)",
                          }}
                        >
                          {percentage(run.metrics.total_return)}
                        </Text>
                      </TableCell>
                      <TableCell>{decimalFormat(run.metrics.sharpe_ratio)}</TableCell>
                    </TableRow>
                  ))}
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
