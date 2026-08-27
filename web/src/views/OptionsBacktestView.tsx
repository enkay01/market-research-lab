import { useState } from "react";
import {
  Badge,
  Banner,
  Button,
  Card,
  Divider,
  Grid,
  Heading,
  HStack,
  SegmentedControl,
  SegmentedControlItem,
  StatusDot,
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
import {
  MOCK_OPTIONS_RUN,
  type OptionSpreadPosition,
} from "./optionsPrototype/mockOptionsData";

function percentage(val: number): string {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

function currency(val: number): string {
  const sign = val > 0 ? "+" : val < 0 ? "-" : "";
  return `${sign}$${Math.abs(val).toFixed(2)}`;
}

interface OptionsBacktestViewProps {
  onBackToStandard?: () => void;
}

export function OptionsBacktestView({ onBackToStandard }: OptionsBacktestViewProps) {
  const run = MOCK_OPTIONS_RUN;
  const [selectedPosId, setSelectedPosId] = useState<string>(run.positions[0]?.id || "");
  const [isReliabilityOpen, setIsReliabilityOpen] = useState(false);
  const [chartMode, setChartMode] = useState<"spread" | "underlying">("spread");
  const [detailTab, setDetailTab] = useState<"ratchets" | "prices" | "blocked" | "manifest">("ratchets");

  const selectedPos: OptionSpreadPosition =
    run.positions.find((p) => p.id === selectedPosId) || run.positions[0];

  // SVG Chart Dimensions
  const width = 860;
  const height = 240;
  const pad = 30;

  const traj = selectedPos.trajectory;
  const minSpread = 0;
  const maxSpread =
    Math.max(...traj.map((t) => Math.max(t.stop_level, t.spread_worst, t.spread_best))) * 1.15 || 5;

  const pointsWorst = traj
    .map((t, i) => {
      const x = pad + (i / (traj.length - 1)) * (width - 2 * pad);
      const y =
        height - pad - ((t.spread_worst - minSpread) / (maxSpread - minSpread)) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const pointsBest = traj
    .map((t, i) => {
      const x = pad + (i / (traj.length - 1)) * (width - 2 * pad);
      const y =
        height - pad - ((t.spread_best - minSpread) / (maxSpread - minSpread)) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const pointsStop = traj
    .map((t, i) => {
      const x = pad + (i / (traj.length - 1)) * (width - 2 * pad);
      const y =
        height - pad - ((t.stop_level - minSpread) / (maxSpread - minSpread)) * (height - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const handleExport = (type: "html" | "csv" | "json") => {
    alert(`Exporting ${type.toUpperCase()} options backtest artifact for Run ${run.run_id}`);
  };

  return (
    <VStack gap={4}>
      {/* Top Header & Simulation Metadata Ribbon */}
      <Card padding={3}>
        <HStack justify="between" align="center" wrap gap={3}>
          <HStack align="center" gap={3}>
            <Heading level={2}>Options Credit Spread Simulation</Heading>
            <Token label="Alpaca Provider" color="blue" />
            <Token label={`Revision: ${run.strategy_revision}`} color="purple" />
            <Token label={`${run.date_range.start} to ${run.date_range.end}`} color="default" />
          </HStack>

          <HStack align="center" gap={2}>
            {/* Non-intrusive Data Reliability Drawer Toggle */}
            <Button
              label={`Data Health: ${run.data_health.overall_reliability_pct}%`}
              variant="secondary"
              size="sm"
              onClick={() => setIsReliabilityOpen(!isReliabilityOpen)}
            />
            <Button
              label="Export HTML"
              variant="secondary"
              size="sm"
              onClick={() => handleExport("html")}
            />
            <Button
              label="Export CSV"
              variant="secondary"
              size="sm"
              onClick={() => handleExport("csv")}
            />
            {onBackToStandard && (
              <Button
                label="Multi-Asset Backtest"
                variant="secondary"
                size="sm"
                onClick={onBackToStandard}
              />
            )}
          </HStack>
        </HStack>
      </Card>

      {/* Expandable Data Reliability Banner Drawer */}
      {isReliabilityOpen && (
        <Banner status={run.data_health.gaps_over_5_min > 0 ? "warning" : "info"}>
          <VStack gap={2}>
            <HStack justify="between" align="center">
              <HStack align="center" gap={2}>
                <StatusDot variant={run.data_health.gaps_over_5_min > 0 ? "warning" : "success"} />
                <Text weight="bold">
                  Data Quality &amp; Matching Integrity ({run.data_health.overall_reliability_pct}% Confidence)
                </Text>
              </HStack>
              <Button
                label="Dismiss"
                variant="secondary"
                size="sm"
                onClick={() => setIsReliabilityOpen(false)}
              />
            </HStack>
            <Text type="supporting">
              Total bars analyzed: {run.data_health.total_bars.toLocaleString()} across {run.positions.length} active positions.
              Found {run.data_health.gaps_over_5_min} gaps &gt; 5 minutes and {run.data_health.missing_matching_minutes} missing quote minutes.
            </Text>
          </VStack>
        </Banner>
      )}

      {/* Dual Execution Result KPI Tiles: Worst Case Primary vs Best Case Beside It */}
      <Grid columns={{ minWidth: 260, repeat: "fit" }} gap={3}>
        <Card padding={3} style={{ borderLeft: "4px solid var(--color-border-emphasized)" }}>
          <VStack gap={1}>
            <HStack justify="between" align="center">
              <Text type="supporting" weight="bold">
                Worst Result (Primary Benchmark)
              </Text>
              <Token label="Conservative Fill" color="orange" />
            </HStack>
            <Heading
              level={2}
              style={{
                color:
                  run.worst_result.net_pnl >= 0
                    ? "var(--color-text-green)"
                    : "var(--color-text-red)",
              }}
            >
              {currency(run.worst_result.net_pnl)} ({percentage(run.worst_result.total_return_pct)})
            </Heading>
            <HStack justify="between" align="center">
              <Text type="supporting">
                Win Rate: {run.worst_result.win_rate_pct.toFixed(1)}% ({run.worst_result.winning_trades}/{run.worst_result.total_trades})
              </Text>
              <Text type="supporting">Max DD: {run.worst_result.max_drawdown_pct.toFixed(1)}%</Text>
              <Text type="supporting">Sharpe: {run.worst_result.sharpe_ratio.toFixed(2)}</Text>
            </HStack>
          </VStack>
        </Card>

        <Card padding={3}>
          <VStack gap={1}>
            <HStack justify="between" align="center">
              <Text type="supporting" weight="bold">
                Best Result (Theoretical Mid/Opposite)
              </Text>
              <Token label="Optimistic Fill" color="green" />
            </HStack>
            <Heading
              level={2}
              style={{
                color:
                  run.best_result.net_pnl >= 0
                    ? "var(--color-text-green)"
                    : "var(--color-text-red)",
              }}
            >
              {currency(run.best_result.net_pnl)} ({percentage(run.best_result.total_return_pct)})
            </Heading>
            <HStack justify="between" align="center">
              <Text type="supporting">
                Win Rate: {run.best_result.win_rate_pct.toFixed(1)}% ({run.best_result.winning_trades}/{run.best_result.total_trades})
              </Text>
              <Text type="supporting">Max DD: {run.best_result.max_drawdown_pct.toFixed(1)}%</Text>
              <Text type="supporting">Sharpe: {run.best_result.sharpe_ratio.toFixed(2)}</Text>
            </HStack>
          </VStack>
        </Card>

        <Card padding={3}>
          <VStack gap={1}>
            <Text type="supporting" weight="bold">Active Spread In Focus</Text>
            <HStack align="center" gap={2}>
              <Token label={selectedPos.security_id} color="blue" />
              <Text weight="bold">
                {selectedPos.spread_type} (${selectedPos.short_strike}/${selectedPos.long_strike})
              </Text>
            </HStack>
            <HStack justify="between">
              <Text type="supporting">Status: <Text weight="bold">{selectedPos.status}</Text></Text>
              <Token label={`Credit: $${selectedPos.entry_credit.toFixed(2)}`} color="green" />
            </HStack>
          </VStack>
        </Card>
      </Grid>

      {/* Visual Spread Trajectory & Fill Envelope SVG Chart */}
      <Card padding={4}>
        <VStack gap={3}>
          <HStack justify="between" align="center">
            <HStack align="center" gap={3}>
              <Heading level={3}>
                {selectedPos.security_id} Spread Trajectory &amp; Stop Ratchet Curve
              </Heading>
              <Token label={`Entry Credit: $${selectedPos.entry_credit.toFixed(2)}`} color="green" />
              <Token label={`Short Delta: ${selectedPos.short_delta.toFixed(2)} Δ`} color="purple" />
              <Token label={`IV: ${(selectedPos.implied_volatility * 100).toFixed(1)}%`} color="default" />
            </HStack>
            <HStack align="center" gap={2}>
              <SegmentedControl
                value={chartMode}
                onChange={(val) => {
                  // SAFETY: Value is constrained by SegmentedControlItem values
                  setChartMode(val as "spread" | "underlying");
                }}
              >
                <SegmentedControlItem value="spread" label="Spread Price ($)" />
                <SegmentedControlItem value="underlying" label="Underlying Stock ($)" />
              </SegmentedControl>
            </HStack>
          </HStack>

          {/* SVG Canvas for Trajectory */}
          <svg
            viewBox={`0 0 ${width} ${height}`}
            style={{
              width: "100%",
              height: "240px",
              overflow: "visible",
            }}
          >
            {/* Grid baseline */}
            <line
              x1={pad}
              y1={height - pad}
              x2={width - pad}
              y2={height - pad}
              stroke="var(--color-border)"
              strokeWidth="1"
            />

            {/* Dynamic Stop Level Ratchet Polyline (Red Step/Line) */}
            <polyline
              fill="none"
              stroke="var(--color-icon-red)"
              strokeWidth="2.5"
              strokeDasharray="4 2"
              points={pointsStop}
            />

            {/* Worst-Case Spread Price Polyline (Orange Line) */}
            <polyline
              fill="none"
              stroke="var(--color-icon-orange)"
              strokeWidth="2.5"
              points={pointsWorst}
            />

            {/* Best-Case Spread Price Polyline (Green Line) */}
            <polyline
              fill="none"
              stroke="var(--color-icon-green)"
              strokeWidth="2"
              points={pointsBest}
            />

            {/* Data points */}
            {traj.map((t, idx) => {
              const x = pad + (idx / (traj.length - 1)) * (width - 2 * pad);
              const yWorst =
                height - pad - ((t.spread_worst - minSpread) / (maxSpread - minSpread)) * (height - 2 * pad);
              return (
                <circle
                  key={idx}
                  cx={x}
                  cy={yWorst}
                  r="4"
                  fill="var(--color-icon-orange)"
                />
              );
            })}
          </svg>

          {/* Legend and Milestones */}
          <HStack justify="between" align="center">
            <Text type="supporting">Opened: {selectedPos.open_timestamp} ({selectedPos.open_rule})</Text>
            <HStack gap={4}>
              <Text type="supporting" style={{ color: "var(--color-text-red)" }}>
                - - Dynamic Stop Level (Ratchet)
              </Text>
              <Text type="supporting" style={{ color: "var(--color-text-orange)" }}>
                — Worst-Case Spread Debit
              </Text>
              <Text type="supporting" style={{ color: "var(--color-text-green)" }}>
                — Best-Case Spread Debit
              </Text>
            </HStack>
            <Text type="supporting">Closed: {selectedPos.close_timestamp} ({selectedPos.close_rule})</Text>
          </HStack>
        </VStack>
      </Card>

      {/* Gantt-Style Position Lifecycle Timeline Strip */}
      <Card padding={3}>
        <VStack gap={3}>
          <Heading level={3}>Position Lifecycle Gantt Timeline</Heading>
          <Text type="supporting">
            Click any position bar to load its full minute-by-minute trajectory and stop ratchet ladder:
          </Text>

          <VStack gap={2}>
            {run.positions.map((pos) => {
              const isSel = pos.id === selectedPos.id;
              return (
                <Card
                  key={pos.id}
                  padding={2}
                  style={{
                    backgroundColor: isSel ? "var(--color-background-wash)" : "var(--color-background-card)",
                    border: isSel ? "1px solid var(--color-border-emphasized)" : "1px solid var(--color-border)",
                    cursor: "pointer",
                  }}
                  onClick={() => setSelectedPosId(pos.id)}
                >
                  <HStack justify="between" align="center">
                    <HStack align="center" gap={3}>
                      <Token label={pos.security_id} color="blue" />
                      <Text weight="bold">{pos.spread_type} (${pos.short_strike}/${pos.long_strike})</Text>
                      <Token label={pos.open_timestamp} color="default" />
                      <Text>→</Text>
                      <Token label={pos.close_timestamp} color="default" />
                      <Token
                        label={pos.status}
                        color={
                          pos.status.includes("Profit")
                            ? "green"
                            : pos.status.includes("Stop")
                            ? "orange"
                            : "purple"
                        }
                      />
                    </HStack>
                    <HStack align="center" gap={3}>
                      <Text type="supporting">
                        Ratchets: <Badge count={pos.stop_movements.length} />
                      </Text>
                      <Text
                        weight="bold"
                        style={{
                          color:
                            pos.worst_execution.net_pnl >= 0
                              ? "var(--color-text-green)"
                              : "var(--color-text-red)",
                        }}
                      >
                        Worst: {currency(pos.worst_execution.net_pnl)} / Best: {currency(pos.best_execution.net_pnl)}
                      </Text>
                    </HStack>
                  </HStack>
                </Card>
              );
            })}
          </VStack>
        </VStack>
      </Card>

      {/* Sub-Section Tabs for Deep Position Analysis */}
      <SegmentedControl
        value={detailTab}
        onChange={(v) => {
          // SAFETY: Value is constrained by SegmentedControlItem values
          setDetailTab(v as "ratchets" | "prices" | "blocked" | "manifest");
        }}
      >
        <SegmentedControlItem value="ratchets" label={`Stop Ratchets (${selectedPos.stop_movements.length})`} />
        <SegmentedControlItem value="prices" label="Leg Execution Prices (Both Legs)" />
        <SegmentedControlItem value="blocked" label={`Blocked Opportunities (${run.blocked_positions.length})`} />
        <SegmentedControlItem value="manifest" label="Run Provenance Manifest" />
      </SegmentedControl>

      {/* SUB-TAB 1: Stop Ratchet Ladder */}
      {detailTab === "ratchets" && (
        <Card padding={3}>
          <VStack gap={3}>
            <Heading level={3}>
              {selectedPos.security_id} Minute-by-Minute Stop Adjustment History
            </Heading>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Minute</TableHeaderCell>
                  <TableHeaderCell>Previous Stop</TableHeaderCell>
                  <TableHeaderCell>Updated Stop Level</TableHeaderCell>
                  <TableHeaderCell>Underlying</TableHeaderCell>
                  <TableHeaderCell>Trigger Rule</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {selectedPos.stop_movements.map((step, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{step.timestamp}</TableCell>
                    <TableCell>${step.previous_stop.toFixed(2)}</TableCell>
                    <TableCell>
                      <Text weight="bold" style={{ color: "var(--color-text-red)" }}>
                        ${step.new_stop.toFixed(2)}
                      </Text>
                    </TableCell>
                    <TableCell>${step.underlying_price.toFixed(2)}</TableCell>
                    <TableCell><Token label={step.trigger_reason} color="purple" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </VStack>
        </Card>
      )}

      {/* SUB-TAB 2: Leg Execution Prices */}
      {detailTab === "prices" && (
        <Card padding={3}>
          <VStack gap={3}>
            <Heading level={3}>{selectedPos.security_id} Both Leg Execution Prices (Worst vs Best)</Heading>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Execution Path</TableHeaderCell>
                  <TableHeaderCell>Short Leg Exit (${selectedPos.short_strike})</TableHeaderCell>
                  <TableHeaderCell>Long Leg Exit (${selectedPos.long_strike})</TableHeaderCell>
                  <TableHeaderCell>Net Debit to Close</TableHeaderCell>
                  <TableHeaderCell>Net PnL ($)</TableHeaderCell>
                  <TableHeaderCell>Slippage Attribution</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell><Token label="Worst Result" color="orange" /></TableCell>
                  <TableCell>${selectedPos.worst_execution.short_leg_exit.toFixed(2)}</TableCell>
                  <TableCell>${selectedPos.worst_execution.long_leg_exit.toFixed(2)}</TableCell>
                  <TableCell>${selectedPos.worst_execution.net_debit_to_close.toFixed(2)}</TableCell>
                  <TableCell>
                    <Text
                      weight="bold"
                      style={{
                        color:
                          selectedPos.worst_execution.net_pnl >= 0
                            ? "var(--color-text-green)"
                            : "var(--color-text-red)",
                      }}
                    >
                      {currency(selectedPos.worst_execution.net_pnl)} ({percentage(selectedPos.worst_execution.return_pct)})
                    </Text>
                  </TableCell>
                  <TableCell>${selectedPos.worst_execution.slippage_cost.toFixed(2)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Token label="Best Result" color="green" /></TableCell>
                  <TableCell>${selectedPos.best_execution.short_leg_exit.toFixed(2)}</TableCell>
                  <TableCell>${selectedPos.best_execution.long_leg_exit.toFixed(2)}</TableCell>
                  <TableCell>${selectedPos.best_execution.net_debit_to_close.toFixed(2)}</TableCell>
                  <TableCell>
                    <Text
                      weight="bold"
                      style={{
                        color:
                          selectedPos.best_execution.net_pnl >= 0
                            ? "var(--color-text-green)"
                            : "var(--color-text-red)",
                      }}
                    >
                      {currency(selectedPos.best_execution.net_pnl)} ({percentage(selectedPos.best_execution.return_pct)})
                    </Text>
                  </TableCell>
                  <TableCell>${selectedPos.best_execution.slippage_cost.toFixed(2)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </VStack>
        </Card>
      )}

      {/* SUB-TAB 3: Blocked Spreads */}
      {detailTab === "blocked" && (
        <Card padding={3}>
          <VStack gap={3}>
            <Heading level={3}>Blocked Opportunities &amp; Exclusion Audit</Heading>
            <Text type="supporting">
              Positions filtered out by earnings blackout, 7-day expiration limit, portfolio margin caps, or similarity limits:
            </Text>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Candidate</TableHeaderCell>
                  <TableHeaderCell>Timestamp</TableHeaderCell>
                  <TableHeaderCell>Exclusion Rule</TableHeaderCell>
                  <TableHeaderCell>Reason</TableHeaderCell>
                  <TableHeaderCell>Details</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {run.blocked_positions.map((blk) => (
                  <TableRow key={blk.id}>
                    <TableCell>
                      <HStack gap={1} align="center">
                        <Token label={blk.security_id} color="blue" />
                        <Text weight="bold">{blk.candidate_type}</Text>
                      </HStack>
                    </TableCell>
                    <TableCell>{blk.timestamp}</TableCell>
                    <TableCell>
                      <Token
                        label={blk.rule_id}
                        color={
                          blk.rule_id === "EARNINGS_BLACKOUT"
                            ? "orange"
                            : blk.rule_id === "FINAL_SEVEN_DAY_RULE"
                            ? "purple"
                            : "default"
                        }
                      />
                    </TableCell>
                    <TableCell><Text weight="bold">{blk.reason}</Text></TableCell>
                    <TableCell><Text type="supporting">{blk.details}</Text></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </VStack>
        </Card>
      )}

      {/* SUB-TAB 4: Manifest */}
      {detailTab === "manifest" && (
        <Card padding={3}>
          <VStack gap={2}>
            <Heading level={3}>Run Reproducibility Manifest</Heading>
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell><Text type="supporting">Run Identifier</Text></TableCell>
                  <TableCell><Text weight="bold">{run.run_id}</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Provider</Text></TableCell>
                  <TableCell><Text>{run.provider}</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Strategy Revision</Text></TableCell>
                  <TableCell><Text>{run.strategy_revision}</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Dataset Version</Text></TableCell>
                  <TableCell><Text>{run.dataset_version}</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Engine Source Fingerprint</Text></TableCell>
                  <TableCell><Text size="sm">{run.engine_source_fingerprint}</Text></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </VStack>
        </Card>
      )}
      <Divider />
    </VStack>
  );
}
