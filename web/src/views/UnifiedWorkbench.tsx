import { useState } from "react";
import {
  Banner,
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
import { Selector } from "@astryxdesign/core/Selector";
import { EquityCurveCanvas } from "./EquityCurveCanvas";
import {
  api,
  type Project,
  type StrategyVerdictResponse,
} from "../api/client";

interface UnifiedWorkbenchProps {
  project?: Project;
}

export function UnifiedWorkbench({ project }: UnifiedWorkbenchProps) {
  const [hasExecuted, setHasExecuted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "summary" | "gates" | "replay" | "screener" | "ledger"
  >("summary");

  // Wizard structured configuration state (Zero free-text fields)
  const [universe, setUniverse] = useState("megacap");
  const [benchmark, setBenchmark] = useState("spy");
  const [cadence, setCadence] = useState("daily");
  const [strategyModel, setStrategyModel] = useState("trend_exhaustion");
  const [fastPeriod, setFastPeriod] = useState("10");
  const [slowPeriod, setSlowPeriod] = useState("50");
  const [stopLoss, setStopLoss] = useState("5");
  const [takeProfit, setTakeProfit] = useState("15");
  const [maxHold, setMaxHold] = useState("20");
  const [holdoutSplit, setHoldoutSplit] = useState("75_25");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [positionSizing, setPositionSizing] = useState("compounded_100");
  const [frictionStress, setFrictionStress] = useState("3x_ladder");
  const [commissionBps, setCommissionBps] = useState("5");
  const [slippageBps, setSlippageBps] = useState("2");

  // Live verdict execution result
  const [verdictResult, setVerdictResult] = useState<StrategyVerdictResponse | null>(null);

  async function handleRunEvaluation() {
    if (!project?.id) {
      setErrorMessage("Please select or create a project before running the evaluation.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    const splitMap = {
      "75_25": 0.25,
      "80_20": 0.20,
      "70_30": 0.30,
    } as const;
    // SAFETY: holdoutSplit membership is checked by the in operator before indexing splitMap
    const holdoutRatio =
      holdoutSplit in splitMap ? splitMap[holdoutSplit as keyof typeof splitMap] : 0.25;

    try {
      const response = await api.evaluateVerdict(project.id, {
        strategy_name: strategyModel,
        strategy_revision: "v1",
        universe_preset: universe,
        benchmark_symbol: benchmark.toUpperCase(),
        holdout_ratio: holdoutRatio,
        starting_cash: parseFloat(initialCapital) || 100_000.0,
        parameters: {
          fast_period: parseInt(fastPeriod, 10) || 10,
          slow_period: parseInt(slowPeriod, 10) || 50,
          period: 14,
          stop_loss: stopLoss,
          take_profit: takeProfit,
          max_hold: maxHold,
        },
        execution: {
          schedule: "daily",
          commission_rate: (parseFloat(commissionBps) || 0) / 10000.0,
          slippage_rate: (parseFloat(slippageBps) || 0) / 10000.0,
          allow_shorting: true,
          borrow_fee_rate: 0.0,
          cash_interest_rate: 0.0,
          unavailable_borrow: [],
          max_leverage: 1.0,
          margin_requirement: 1.0,
          maintenance_margin: 0.25,
          leverage_mode: "reject",
        },
      });

      setVerdictResult(response);
      setHasExecuted(true);
      setActiveTab("summary");
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to execute strategy verdict."
      );
    } finally {
      setIsLoading(false);
    }
  }

  // --------------------------------------------------------------------------
  // STATE A: BEFORE RUN — SETUP WIZARD ON ITS OWN (NO DUMP OF RESULTS)
  // --------------------------------------------------------------------------
  if (!hasExecuted || !verdictResult) {
    return (
      <VStack gap={4} style={{ maxWidth: "980px", margin: "0 auto" }}>
        {errorMessage && (
          <Banner status="error" title="Evaluation Error" description={errorMessage} />
        )}

        <Card padding={4}>
          <VStack gap={4}>
            {/* Header */}
            <VStack gap={1}>
              <HStack align="center" gap={2}>
                <Token label="NEW EVALUATION" color="blue" />
                <Text weight="bold" size="lg">
                  Strategy Backtest &amp; Verdict Setup
                </Text>
              </HStack>
              <Text size="sm" type="supporting">
                Configure universe scope, strategy rules, out-of-sample holdout, and fee friction before generating the verdict.
              </Text>
            </VStack>

            <Divider />

            {/* Step 1: Universe & Timeframe */}
            <VStack gap={3}>
              <HStack align="center" gap={2}>
                <Token label="STEP 1" color="purple" />
                <Text weight="bold">Universe &amp; Benchmark Scope</Text>
              </HStack>

              <Grid columns={{ minWidth: 220, repeat: "fit" }} gap={3}>
                <Selector
                  label="Security Universe"
                  value={universe}
                  onChange={(val: string) => setUniverse(val)}
                  options={[
                    { value: "megacap", label: "Megacap Liquid Basket (8 Securities)" },
                    { value: "sp500", label: "S&P 500 Index Universe (500 Securities)" },
                    { value: "nasdaq100", label: "Nasdaq 100 Constituents" },
                  ]}
                />
                <Selector
                  label="Buy &amp; Hold Benchmark"
                  value={benchmark}
                  onChange={(val: string) => setBenchmark(val)}
                  options={[
                    { value: "spy", label: "SPY ETF (S&P 500 Benchmark)" },
                    { value: "qqq", label: "QQQ ETF (Nasdaq 100)" },
                  ]}
                />
                <Selector
                  label="Sampling Cadence"
                  value={cadence}
                  onChange={(val: string) => setCadence(val)}
                  options={[
                    { value: "daily", label: "Daily (Close-to-Close)" },
                    { value: "hourly", label: "1-Hour Aggregates" },
                    { value: "minute", label: "1-Minute Intraday Bars" },
                  ]}
                />
              </Grid>
            </VStack>

            <Divider />

            {/* Step 2: Strategy Rules & Out-of-Sample Holdout */}
            <VStack gap={3}>
              <HStack align="center" gap={2}>
                <Token label="STEP 2" color="purple" />
                <Text weight="bold">Strategy Rules &amp; Out-of-Sample Partition</Text>
              </HStack>

              <Grid columns={{ minWidth: 220, repeat: "fit" }} gap={3}>
                <Selector
                  label="Strategy Logic"
                  value={strategyModel}
                  onChange={(val: string) => setStrategyModel(val)}
                  options={[
                    { value: "trend_exhaustion", label: "Trend Exhaustion + Volatility Sizing" },
                    { value: "ma_crossover", label: "Dual Moving Average Crossover" },
                    { value: "rsi_reversal", label: "RSI Mean Reversion" },
                  ]}
                />
                <Selector
                  label="Fast Lookback"
                  value={fastPeriod}
                  onChange={(val: string) => setFastPeriod(val)}
                  options={[
                    { value: "5", label: "5 Days (Fast)" },
                    { value: "10", label: "10 Days (Standard)" },
                    { value: "20", label: "20 Days (Slow)" },
                  ]}
                />
                <Selector
                  label="Slow Lookback"
                  value={slowPeriod}
                  onChange={(val: string) => setSlowPeriod(val)}
                  options={[
                    { value: "20", label: "20 Days" },
                    { value: "50", label: "50 Days" },
                    { value: "100", label: "100 Days" },
                    { value: "200", label: "200 Days" },
                  ]}
                />
                <Selector
                  label="Out-of-Sample Split"
                  value={holdoutSplit}
                  onChange={(val: string) => setHoldoutSplit(val)}
                  options={[
                    { value: "75_25", label: "75% In-Sample / 25% Holdout (Default)" },
                    { value: "80_20", label: "80% In-Sample / 20% Holdout" },
                    { value: "70_30", label: "70% In-Sample / 30% Holdout" },
                  ]}
                />
                <Selector
                  label="Safety Stop Loss"
                  value={stopLoss}
                  onChange={(val: string) => setStopLoss(val)}
                  options={[
                    { value: "3", label: "3.0% Max Loss Exit" },
                    { value: "5", label: "5.0% Max Loss Exit" },
                    { value: "8", label: "8.0% Max Loss Exit" },
                    { value: "none", label: "None (Unconstrained)" },
                  ]}
                />
                <Selector
                  label="Safety Take Profit"
                  value={takeProfit}
                  onChange={(val: string) => setTakeProfit(val)}
                  options={[
                    { value: "10", label: "10.0% Profit Exit" },
                    { value: "15", label: "15.0% Profit Exit" },
                    { value: "20", label: "20.0% Profit Exit" },
                    { value: "none", label: "None (Unconstrained)" },
                  ]}
                />
                <Selector
                  label="Maximum Holding Period"
                  value={maxHold}
                  onChange={(val: string) => setMaxHold(val)}
                  options={[
                    { value: "10", label: "10 Calendar Days" },
                    { value: "20", label: "20 Calendar Days" },
                    { value: "60", label: "60 Calendar Days" },
                    { value: "none", label: "None (Hold until signal)" },
                  ]}
                />
              </Grid>
            </VStack>

            <Divider />

            {/* Step 3: Capital & Friction Ladder */}
            <VStack gap={3}>
              <HStack align="center" gap={2}>
                <Token label="STEP 3" color="purple" />
                <Text weight="bold">Capital &amp; Fee Friction Stress Testing</Text>
              </HStack>

              <Grid columns={{ minWidth: 220, repeat: "fit" }} gap={3}>
                <Selector
                  label="Starting Capital"
                  value={initialCapital}
                  onChange={(val: string) => setInitialCapital(val)}
                  options={[
                    { value: "10000", label: "$10,000 USD" },
                    { value: "50000", label: "$50,000 USD" },
                    { value: "100000", label: "$100,000 USD" },
                  ]}
                />
                <Selector
                  label="Position Sizing"
                  value={positionSizing}
                  onChange={(val: string) => setPositionSizing(val)}
                  options={[
                    { value: "compounded_100", label: "100% Cash Compounded" },
                    { value: "fixed_50", label: "50% Fixed Portfolio Weight" },
                    { value: "slot_25", label: "25% Multi-Slot Allocation" },
                  ]}
                />
                <Selector
                  label="Cost Stress Protocol"
                  value={frictionStress}
                  onChange={(val: string) => setFrictionStress(val)}
                  options={[
                    { value: "3x_ladder", label: "3x Stress Ladder (Evaluates 1x, 2x, and 3x)" },
                    { value: "1x_static", label: "1x Static Baseline Only" },
                  ]}
                />
                <Selector
                  label="Commission Fee"
                  value={commissionBps}
                  onChange={(val: string) => setCommissionBps(val)}
                  options={[
                    { value: "5", label: "5.0 bps (0.05% per trade)" },
                    { value: "10", label: "10.0 bps (0.10% per trade)" },
                    { value: "0", label: "Zero Commission" },
                  ]}
                />
                <Selector
                  label="Slippage Allowance"
                  value={slippageBps}
                  onChange={(val: string) => setSlippageBps(val)}
                  options={[
                    { value: "2", label: "2.0 bps Execution Slippage" },
                    { value: "5", label: "5.0 bps Execution Slippage" },
                    { value: "0", label: "Zero Slippage" },
                  ]}
                />
              </Grid>
            </VStack>

            <Divider />

            {/* Run Button */}
            <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "12px" }}>
              <Text size="sm" type="supporting">
                Evaluation executes locally with point-in-time constituent checks.
              </Text>

              <Button
                label={isLoading ? "Executing..." : "▶ Run Backtest & Generate Verdict"}
                variant="primary"
                size="md"
                onClick={handleRunEvaluation}
                isDisabled={isLoading}
              />
            </HStack>
          </VStack>
        </Card>
      </VStack>
    );
  }

  // --------------------------------------------------------------------------
  // STATE B: AFTER RUN — THE VERDICT HERO BANNER & TABBED RESULTS WORKSPACE
  // --------------------------------------------------------------------------
  const combined = verdictResult.combined_metrics;
  const isMetrics = verdictResult.in_sample_metrics;
  const oosMetrics = verdictResult.out_of_sample_metrics;
  const netEdge = combined.total_return - combined.benchmark_return;

  return (
    <VStack gap={4} style={{ maxWidth: "1200px", margin: "0 auto" }}>
      {/* 1. TOP HEADER: THE VERDICT BANNER (Primary conclusion surfaced immediately) */}
      <Card
        padding={3}
        style={{
          backgroundColor: "var(--color-background-wash)",
          border: `1px solid ${
            verdictResult.overall_passed
              ? "var(--color-text-green)"
              : "var(--color-text-red)"
          }`,
        }}
      >
        <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "12px" }}>
          <HStack gap={3} align="center">
            <Token
              label={verdictResult.overall_passed ? "● PASS" : "● FAIL"}
              color={verdictResult.overall_passed ? "green" : "red"}
            />
            <VStack gap={1}>
              <Text weight="bold" size="lg">
                {verdictResult.overall_passed
                  ? "Strategy Clears Gate 1 (Benchmark Hurdle)"
                  : `Strategy Rejected: ${verdictResult.rejection_reason ?? "Loses to benchmark after costs"}`}
              </Text>
              <Text size="sm" type="supporting">
                Universe: {universe.toUpperCase()} · Benchmark: {benchmark.toUpperCase()} ETF · Evaluated: Gate 1 (Benchmark Hurdle)
              </Text>
            </VStack>
          </HStack>

          {/* Action to modify settings returning back to the wizard */}
          <HStack gap={2} align="center">
            <Button
              label="✎ Edit Parameters"
              variant="primary"
              size="sm"
              onClick={() => setHasExecuted(false)}
            />
          </HStack>
        </HStack>
      </Card>

      {/* 2. TAB NAVIGATION */}
      <Card padding={2}>
        <SegmentedControl
          label="Evaluation Perspective"
          value={activeTab}
          onChange={(val: string) => {
            // SAFETY: Value is constrained by SegmentedControlItem values
            setActiveTab(val as typeof activeTab);
          }}
        >
          <SegmentedControlItem value="summary" label="1. Verdict &amp; Summary" />
          <SegmentedControlItem value="gates" label="2. Stress &amp; Luck (5 Gates)" />
          <SegmentedControlItem value="replay" label="3. Replay &amp; Trade Actions" />
          <SegmentedControlItem value="screener" label="4. Universe Screener" />
          <SegmentedControlItem value="ledger" label="5. Ledger Audit" />
        </SegmentedControl>
      </Card>

      {/* TAB 1: VERDICT & SUMMARY (Key conclusions surfaced early) */}
      {activeTab === "summary" && (
        <VStack gap={4}>
          {/* Headline KPIs (Clean 6-column grid) */}
          <Grid columns={{ minWidth: 160, repeat: "fit" }} gap={2}>
            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Total Return</Text>
                <Text
                  weight="bold"
                  size="lg"
                  style={{
                    color:
                      combined.total_return >= 0
                        ? "var(--color-text-green)"
                        : "var(--color-text-red)",
                  }}
                >
                  {combined.total_return >= 0 ? "+" : ""}
                  {(combined.total_return * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Benchmark (SPY)</Text>
                <Text weight="bold" size="lg">
                  {combined.benchmark_return >= 0 ? "+" : ""}
                  {(combined.benchmark_return * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Net Edge Over Holding</Text>
                <Text
                  weight="bold"
                  size="lg"
                  style={{
                    color:
                      netEdge > 0
                        ? "var(--color-text-green)"
                        : "var(--color-text-red)",
                  }}
                >
                  {netEdge > 0 ? "+" : ""}
                  {(netEdge * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Annualized CAGR</Text>
                <Text weight="bold" size="lg">
                  {combined.cagr >= 0 ? "+" : ""}
                  {(combined.cagr * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Sharpe Ratio</Text>
                <Text weight="bold" size="lg">
                  {combined.sharpe_ratio.toFixed(2)}
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Max Drawdown</Text>
                <Text weight="bold" size="lg" style={{ color: "var(--color-text-red)" }}>
                  {(combined.max_drawdown * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Win Rate</Text>
                <Text weight="bold" size="lg">
                  {(combined.win_rate * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Profit Factor</Text>
                <Text weight="bold" size="lg">
                  {combined.profit_factor.toFixed(2)}
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Exposure %</Text>
                <Text weight="bold" size="lg">
                  {(combined.exposure_pct * 100).toFixed(1)}%
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Total Trades</Text>
                <Text weight="bold" size="lg">
                  {combined.trades_count}
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">3x Cost Stress PF</Text>
                <Text weight="bold" size="lg" style={{ color: "var(--color-text-primary)" }}>
                  {verdictResult.friction_ladder.find((tier) => tier.multiplier === 3)?.profit_factor.toFixed(2) ?? "—"}
                </Text>
              </VStack>
            </Card>

            <Card padding={2}>
              <VStack gap={1}>
                <Text size="sm" type="supporting">Luck Confidence (PSR)</Text>
                <Text weight="bold" size="lg" style={{ color: "var(--color-text-blue)" }}>
                  Pending Gate 4 (#116)
                </Text>
              </VStack>
            </Card>
          </Grid>

          {/* Out-of-Sample Holdout Breakdown Table */}
          <Card padding={3}>
            <VStack gap={2}>
              <HStack justify="between" align="center" style={{ flexWrap: "wrap", gap: "8px" }}>
                <HStack gap={2} align="center">
                  <Text weight="bold">Chronological Out-of-Sample Partition Breakdown</Text>
                  <Token
                    label={verdictResult.overall_passed ? "Partition Passing" : "Holdout Failed"}
                    color={verdictResult.overall_passed ? "green" : "red"}
                  />
                </HStack>
                <Text size="sm" type="supporting">
                  Final {Math.round((verdictResult.holdout_ratio ?? 0.25) * 100)}% of timeline strictly held out to detect overfitting
                </Text>
              </HStack>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Evaluation Window</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Total Return</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>CAGR</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Sharpe</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Sortino</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Max Drawdown</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>SPY Benchmark</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Trades</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>
                      <Text weight="bold">
                        In-Sample Training ({Math.round((1 - (verdictResult.holdout_ratio ?? 0.25)) * 100)}%)
                      </Text>
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>
                      {isMetrics.total_return >= 0 ? "+" : ""}
                      {(isMetrics.total_return * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>
                      {isMetrics.cagr >= 0 ? "+" : ""}
                      {(isMetrics.cagr * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>{isMetrics.sharpe_ratio.toFixed(2)}</TableCell>
                    <TableCell style={{ textAlign: "end" }}>{isMetrics.sortino_ratio.toFixed(2)}</TableCell>
                    <TableCell style={{ textAlign: "end" }}>{(isMetrics.max_drawdown * 100).toFixed(1)}%</TableCell>
                    <TableCell style={{ textAlign: "end" }}>
                      {isMetrics.benchmark_return >= 0 ? "+" : ""}
                      {(isMetrics.benchmark_return * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>{isMetrics.trades_count}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>
                      <Text weight="bold">
                        Out-of-Sample Holdout ({Math.round((verdictResult.holdout_ratio ?? 0.25) * 100)}%)
                      </Text>
                    </TableCell>
                    <TableCell
                      style={{
                        textAlign: "end",
                        color:
                          oosMetrics.total_return >= 0
                            ? "var(--color-text-green)"
                            : "var(--color-text-red)",
                      }}
                    >
                      {oosMetrics.total_return >= 0 ? "+" : ""}
                      {(oosMetrics.total_return * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>
                      {oosMetrics.cagr >= 0 ? "+" : ""}
                      {(oosMetrics.cagr * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>{oosMetrics.sharpe_ratio.toFixed(2)}</TableCell>
                    <TableCell style={{ textAlign: "end" }}>{oosMetrics.sortino_ratio.toFixed(2)}</TableCell>
                    <TableCell style={{ textAlign: "end" }}>{(oosMetrics.max_drawdown * 100).toFixed(1)}%</TableCell>
                    <TableCell style={{ textAlign: "end" }}>
                      {oosMetrics.benchmark_return >= 0 ? "+" : ""}
                      {(oosMetrics.benchmark_return * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell style={{ textAlign: "end" }}>{oosMetrics.trades_count}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </VStack>
          </Card>

          <EquityCurveCanvas
            points={verdictResult.equity_curve}
            isHoldoutPassing={verdictResult.overall_passed}
            title="Portfolio Equity vs. SPY Benchmark"
            subtitle="Trajectory across in-sample training and out-of-sample holdout partitions"
          />
        </VStack>
      )}

      {activeTab === "gates" && (
        <VStack gap={4}>
          <Card padding={3}>
            <VStack gap={2}>
              <HStack justify="between" align="center">
                <Text weight="bold">Gate 2: Dynamic fee stress</Text>
                <Token
                  label={verdictResult.gates[1]?.passed ? "● PASS" : "● FAIL"}
                  color={verdictResult.gates[1]?.passed ? "green" : "red"}
                />
              </HStack>
              <Text size="sm" type="supporting">
                Gate 2 requires total net return above 0.0% and profit factor above 1.00 at 3x friction.
              </Text>
              <Text>
                Observed 3x PF: {verdictResult.friction_ladder.find((tier) => tier.multiplier === 3)?.profit_factor.toFixed(2) ?? "—"}
              </Text>
              {!verdictResult.gates[1]?.passed && (
                <Text style={{ color: "var(--color-text-red)" }}>Edge disappears under realistic fee stress</Text>
              )}
            </VStack>
          </Card>

          <Card padding={3}>
            <VStack gap={2}>
              <Text weight="bold">Friction ladder</Text>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Tier</TableHeaderCell>
                    <TableHeaderCell>Commission / Slippage / Borrow</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Total Return</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Net Profit</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>PF</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Max Drawdown</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Commissions</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Slippage Drag</TableHeaderCell>
                    <TableHeaderCell style={{ textAlign: "end" }}>Borrow Fees</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {verdictResult.friction_ladder.map((tier) => (
                    <TableRow key={tier.multiplier}>
                      <TableCell>{tier.multiplier}x</TableCell>
                      <TableCell>{tier.commission_bps.toFixed(1)} / {tier.slippage_bps.toFixed(1)} / {tier.borrow_fee_bps.toFixed(1)} bps</TableCell>
                      <TableCell style={{ textAlign: "end" }}>{tier.total_return_pct.toFixed(2)}%</TableCell>
                      <TableCell style={{ textAlign: "end" }}>USD {tier.net_profit_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</TableCell>
                      <TableCell style={{ textAlign: "end" }}>{tier.profit_factor.toFixed(2)}</TableCell>
                      <TableCell style={{ textAlign: "end" }}>{tier.max_drawdown_pct.toFixed(2)}%</TableCell>
                      <TableCell style={{ textAlign: "end" }}>USD {tier.commission_paid_usd.toFixed(2)}</TableCell>
                      <TableCell style={{ textAlign: "end" }}>USD {tier.slippage_drag_usd.toFixed(2)}</TableCell>
                      <TableCell style={{ textAlign: "end" }}>USD {tier.borrow_paid_usd.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </VStack>
          </Card>
        </VStack>
      )}

      {activeTab !== "summary" && activeTab !== "gates" && (
        <Card padding={4}>
          <VStack gap={3} align="center" style={{ textAlign: "center", padding: "32px 16px" }}>
            <Token label="AVAILABLE IN EPIC PHASE 2" color="purple" />
            <Text weight="bold" size="lg">
              {activeTab === "replay" && "Interactive Simulation Replay Canvas"}
              {activeTab === "screener" && "Market-Wide Diagnostic Universe Screener"}
              {activeTab === "ledger" && "Daily Mark-to-Market Ledger Audit"}
            </Text>
            <Text size="sm" type="supporting" style={{ maxWidth: "600px" }}>
              This tab is scheduled for implementation in tickets #115–#119. Tab 1 currently provides the verified Gate 1 (Benchmark Hurdle) verdict and out-of-sample partition evaluation foundation.
            </Text>
            <Button
              label="Return to Tab 1 (Verdict &amp; Summary)"
              variant="secondary"
              size="sm"
              onClick={() => setActiveTab("summary")}
            />
          </VStack>
        </Card>
      )}
    </VStack>
  );
}
