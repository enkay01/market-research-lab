import { useEffect, useMemo, useState } from "react";
import {
  Banner,
  Button,
  Card,
  EmptyState,
  Grid,
  Heading,
  HStack,
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
  type CoverageResponse,
  type OptionsBacktestRequest,
  type OptionsBacktestResult,
  type OptionsSpreadPosition,
  type Project,
} from "../api/client";
import { InteractiveCandlestickChart } from "../components/InteractiveCandlestickChart";

interface OptionsBacktestViewProps {
  project?: Project;
  onBack?: () => void;
}

function money(value: number): string {
  return `${value < 0 ? "-" : value > 0 ? "+" : ""}$${Math.abs(value).toFixed(2)}`;
}

function percent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function datasetLabel(dataset: CoverageResponse): string {
  return `${dataset.source} · ${dataset.id.slice(0, 14)} · ${dataset.row_count} rows`;
}

export function OptionsBacktestView({ project, onBack }: OptionsBacktestViewProps) {
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [result, setResult] = useState<OptionsBacktestResult | null>(null);
  const [selectedPositionId, setSelectedPositionId] = useState("");
  const [datasetVersionId, setDatasetVersionId] = useState("");
  const [symbol, setSymbol] = useState("SPY");
  const [startDate, setStartDate] = useState("2024-02-01");
  const [endDate, setEndDate] = useState("2026-08-31");
  const [startingCash, setStartingCash] = useState("100000");
  const [isRunning, setIsRunning] = useState(false);
  const [isAuditOpen, setIsAuditOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!project) return;
    void Promise.all([api.listDatasets(), api.listOptionsBacktests(project.id)])
      .then(([availableDatasets, savedRuns]) => {
        setDatasets(availableDatasets);
        const optionsDataset = availableDatasets.find((item) => item.dataset_type === "options");
        setDatasetVersionId(optionsDataset?.id ?? "");
        const saved = savedRuns[0];
        if (saved) {
          setResult(saved);
          setSelectedPositionId(saved.positions[0]?.id ?? "");
        }
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load options data."));
  }, [project]);

  const selectedPosition = useMemo<OptionsSpreadPosition | undefined>(
    () => result?.positions.find((position) => position.id === selectedPositionId) ?? result?.positions[0],
    [result, selectedPositionId],
  );

  async function runBacktest() {
    if (!project || !datasetVersionId) {
      setError("Select an options Dataset Version before running the Backtest.");
      return;
    }
    setIsRunning(true);
    setError(null);
    const request: OptionsBacktestRequest = {
      dataset_version_id: datasetVersionId,
      symbol: symbol.trim().toUpperCase(),
      start_date: startDate,
      end_date: endDate,
      starting_cash: Number(startingCash),
      path: "worst",
      strategy_name: "put_credit_spread",
      strategy_revision: "v1",
      daily_dataset_version_id: datasets.find((item) => item.dataset_type === "daily_bars")?.id,
    };
    try {
      const next = await api.runOptionsBacktest(project.id, request);
      setResult(next);
      setSelectedPositionId(next.positions[0]?.id ?? "");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Options Backtest failed.");
    } finally {
      setIsRunning(false);
    }
  }

  if (!project) {
    return <EmptyState title="Create a Project first" description="Options Backtest Runs belong to a Project." />;
  }

  return (
    <VStack gap={4} style={{ width: "100%", maxWidth: "1440px", margin: "0 auto", paddingBottom: "96px" }}>
      <Card padding={3}>
        <HStack justify="between" align="center" wrap="wrap" gap={3}>
          <VStack gap={1}>
            <HStack align="center" gap={2}>
              <Heading level={2}>Options credit spread Backtest</Heading>
              <Token label="Alpaca minute trades" color="blue" />
            </HStack>
            <Text type="supporting">Put Credit Spreads · worst supported path is the primary result</Text>
          </VStack>
          <HStack gap={2}>
            {result?.run_id && (
              <>
                <Button label="Export HTML" variant="secondary" size="sm" onClick={() => window.open(api.getOptionsBacktestExportUrl(project.id, result.run_id!, "html"), "_blank")} />
                <Button label="Export CSV" variant="secondary" size="sm" onClick={() => window.open(api.getOptionsBacktestExportUrl(project.id, result.run_id!, "csv"), "_blank")} />
                <Button label="Export JSON" variant="secondary" size="sm" onClick={() => window.open(api.getOptionsBacktestExportUrl(project.id, result.run_id!, "json"), "_blank")} />
              </>
            )}
            {onBack && <Button label="Strategy Verdict Lab" variant="secondary" size="sm" onClick={onBack} />}
          </HStack>
        </HStack>
      </Card>

      {error && <Banner status="error" title="Options Backtest Error" description={error} />}

      <Card padding={3}>
        <VStack gap={3}>
          <Heading level={3}>Run setup</Heading>
          <Grid columns={{ minWidth: 220, repeat: "fit" }} gap={3}>
            <Selector
              label="Options Dataset Version"
              value={datasetVersionId}
              onChange={setDatasetVersionId}
              options={datasets.filter((item) => item.dataset_type === "options").map((item) => ({ value: item.id, label: datasetLabel(item) }))}
            />
            <TextInput label="Security" value={symbol} onChange={(value) => setSymbol(String(value ?? ""))} />
            <TextInput label="Start date" value={startDate} onChange={(value) => setStartDate(String(value ?? ""))} />
            <TextInput label="End date" value={endDate} onChange={(value) => setEndDate(String(value ?? ""))} />
            <TextInput label="Starting cash" value={startingCash} onChange={(value) => setStartingCash(String(value ?? ""))} />
          </Grid>
          <HStack justify="end">
            <Button label="Run options Backtest" variant="primary" onClick={() => void runBacktest()} isLoading={isRunning} />
          </HStack>
        </VStack>
      </Card>

      {!result ? (
        <EmptyState title="No options Run selected" description="Choose an options Dataset Version and run the first historical Backtest." />
      ) : (
        <>
          <Grid columns={{ minWidth: 230, repeat: "fit" }} gap={3}>
            <MetricCard label="Worst net PnL" value={money(result.summary.worst_net_pnl)} negative={result.summary.worst_net_pnl < 0} />
            <MetricCard label="Best net PnL" value={money(result.summary.best_net_pnl)} negative={result.summary.best_net_pnl < 0} />
            <MetricCard label="Portfolio ROM" value={percent(result.summary.portfolio_rom_pct)} negative={result.summary.portfolio_rom_pct < 0} />
            <MetricCard label="Win rate" value={`${result.summary.win_rate_pct.toFixed(1)}% (${result.summary.winning_trades}/${result.summary.total_trades})`} />
            <MetricCard label="Data reliability" value={`${result.summary.overall_reliability_pct.toFixed(1)}%`} negative={result.summary.overall_reliability_pct < 99} />
          </Grid>

          <Card padding={3}><VStack gap={1}><Heading level={4}>Run provenance</Heading><Text size="sm" type="supporting">Run {result.run_id ?? "unsaved"} · Provider {String(result.manifest.provider ?? "unknown")} · Dataset {result.specification.dataset_version_id}</Text><Text size="sm" type="supporting">Strategy revision {result.specification.strategy_revision} · Source {String(result.manifest.source_sha256 ?? "not recorded")}</Text></VStack></Card>

          {result.warnings.length > 0 && (
            <Banner status="warning" title="Run Warnings" description={result.warnings.join(" ")} />
          )}

          {selectedPosition && (
            <Card padding={3}>
              <VStack gap={3}>
                <HStack justify="between" align="center" wrap="wrap" gap={2}>
                  <VStack gap={1}>
                    <Heading level={3}>{selectedPosition.security_id} Put Credit</Heading>
                    <Text type="supporting">${selectedPosition.short_strike} / ${selectedPosition.long_strike} · Expiry {selectedPosition.expiration} · {selectedPosition.status}</Text>
                  </VStack>
                  <HStack gap={2} align="center">
                    <Token label={`${selectedPosition.reliability_pct.toFixed(1)}% reliable`} color={selectedPosition.reliability_pct < 99 ? "orange" : "green"} />
                    <Button label={isAuditOpen ? "Hide audit tray" : "Open audit tray"} variant="secondary" size="sm" onClick={() => setIsAuditOpen((open) => !open)} />
                  </HStack>
                </HStack>
                <InteractiveCandlestickChart position={selectedPosition} />
                <HStack gap={3} wrap="wrap">
                  <Text type="supporting">Entry {selectedPosition.open_timestamp}</Text>
                  <Text type="supporting">Credit ${selectedPosition.entry_credit.toFixed(2)}</Text>
                  <Text type="supporting">Full Possible Loss ${selectedPosition.full_possible_loss.toFixed(2)}</Text>
                  <Text type="supporting">Stop changes {selectedPosition.stop_movements.length}</Text>
                  <Text type="supporting">Missing minutes {selectedPosition.missing_minutes_count}</Text>
                </HStack>
                {isAuditOpen && <AuditTray position={selectedPosition} />}
              </VStack>
            </Card>
          )}

          <Card padding={3} style={{ overflowX: "auto" }}>
            <VStack gap={2}>
              <Heading level={3}>Spread ledger</Heading>
              <Table style={{ minWidth: "1180px" }}>
                <TableHeader><TableRow>
                  <TableHeaderCell>Security / expiry</TableHeaderCell>
                  <TableHeaderCell>Strikes</TableHeaderCell>
                  <TableHeaderCell>Credit</TableHeaderCell>
                  <TableHeaderCell>Full Possible Loss</TableHeaderCell>
                  <TableHeaderCell>ROM</TableHeaderCell>
                  <TableHeaderCell>Worst PnL</TableHeaderCell>
                  <TableHeaderCell>Best PnL</TableHeaderCell>
                  <TableHeaderCell>Close rule</TableHeaderCell>
                  <TableHeaderCell>Audit</TableHeaderCell>
                </TableRow></TableHeader>
                <TableBody>{result.positions.map((position) => (
                  <TableRow key={position.id} style={{ cursor: "pointer", backgroundColor: position.id === selectedPosition?.id ? "var(--color-background-muted)" : undefined }} onClick={() => setSelectedPositionId(position.id)}>
                    <TableCell><Text weight="bold">{position.security_id}</Text><Text size="sm" type="supporting">{position.expiration}</Text></TableCell>
                    <TableCell>${position.short_strike} / ${position.long_strike}</TableCell>
                    <TableCell>${position.entry_credit.toFixed(2)}</TableCell>
                    <TableCell>${position.full_possible_loss.toFixed(2)}</TableCell>
                    <TableCell style={{ color: position.return_on_margin_pct < 0 ? "var(--color-text-red)" : "var(--color-text-green)" }}>{percent(position.return_on_margin_pct)}</TableCell>
                    <TableCell style={{ color: position.worst_net_pnl < 0 ? "var(--color-text-red)" : "var(--color-text-green)" }}>{money(position.worst_net_pnl)}</TableCell>
                    <TableCell style={{ color: position.best_net_pnl < 0 ? "var(--color-text-red)" : "var(--color-text-green)" }}>{money(position.best_net_pnl)}</TableCell>
                    <TableCell>{position.close_rule}</TableCell>
                    <TableCell><Button label="Inspect" variant="secondary" size="sm" onClick={() => setSelectedPositionId(position.id)} /></TableCell>
                  </TableRow>
                ))}</TableBody>
              </Table>
            </VStack>
          </Card>

          {result.blocked_candidates.length > 0 && (
            <Card padding={3}><VStack gap={2}><Heading level={3}>Blocked candidates</Heading>{result.blocked_candidates.map((candidate) => <Text key={`${candidate.timestamp}-${candidate.security_id}`} type="supporting">{candidate.timestamp} · {candidate.security_id} · {candidate.rule}: {candidate.reason}</Text>)}</VStack></Card>
          )}
        </>
      )}
    </VStack>
  );
}

function AuditTray({ position }: { position: OptionsSpreadPosition }) {
  return (
    <Grid columns={{ minWidth: 300, repeat: "fit" }} gap={3}>
      <Card padding={3}>
        <VStack gap={2}>
          <Heading level={4}>Stop Ratchet history</Heading>
          {position.stop_movements.length === 0 ? <Text type="supporting">No Stop Level movement was recorded.</Text> : position.stop_movements.map((movement) => <Text key={`${movement.timestamp}-${movement.new_stop}`} size="sm" type="supporting">{movement.timestamp} · stop ${movement.new_stop.toFixed(2)} · underlying ${movement.underlying_price.toFixed(2)} · {movement.trigger_rule}</Text>)}
        </VStack>
      </Card>
      <Card padding={3}>
        <VStack gap={2}>
          <Heading level={4}>Greeks and counterfactual</Heading>
          {Object.entries(position.greeks).map(([phase, values]) => values && <Text key={phase} size="sm" type="supporting">{phase}: Δ {values.delta.toFixed(3)} · Θ {values.theta.toFixed(4)} · Γ {values.gamma.toFixed(4)} · Vega {values.vega.toFixed(4)} · IV {values.implied_volatility.toFixed(2)}</Text>)}
          {position.counterfactual && <Text size="sm" type="supporting">{position.counterfactual.outcome}: {position.counterfactual.explanation} ({money(position.counterfactual.avoided_loss_or_missed_gain)})</Text>}
        </VStack>
      </Card>
    </Grid>
  );
}

function MetricCard({ label, value, negative = false }: { label: string; value: string; negative?: boolean }) {
  return <Card padding={3}><VStack gap={1}><Text type="supporting" weight="bold">{label}</Text><Heading level={3} style={{ color: negative ? "var(--color-text-red)" : undefined, fontVariantNumeric: "tabular-nums" }}>{value}</Heading></VStack></Card>;
}
