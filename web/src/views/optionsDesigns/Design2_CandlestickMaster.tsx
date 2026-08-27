import { Fragment, useState } from "react";
import {
  Button,
  ButtonGroup,
  Card,
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
  VStack,
} from "@astryxdesign/core";
import {
  MOCK_OPTIONS_DATASET,
  type SpreadPositionDetail,
} from "./designData";
import { InteractiveCandlestickChart } from "../../components/InteractiveCandlestickChart";

function percentage(val: number): string {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

function currency(val: number): string {
  const sign = val > 0 ? "+" : val < 0 ? "-" : "";
  return `${sign}$${Math.abs(val).toFixed(2)}`;
}

export function Design2_CandlestickMaster() {
  const data = MOCK_OPTIONS_DATASET;
  const [selectedPosId, setSelectedPosId] = useState<string>(data.positions[0]?.id || "");
  const [expandedPosId, setExpandedPosId] = useState<string | null>(data.positions[0]?.id || null);

  const selectedPos: SpreadPositionDetail =
    data.positions.find((p) => p.id === selectedPosId) || data.positions[0];

  const toggleExpand = (id: string) => {
    setExpandedPosId((curr) => (curr === id ? null : id));
  };

  const cellStyle: React.CSSProperties = {
    whiteSpace: "nowrap",
    overflow: "visible",
    textOverflow: "clip",
    padding: "8px 12px",
  };

  return (
    <VStack gap={3} style={{ width: "100%", maxWidth: "1400px", margin: "0 auto", paddingBottom: "120px" }}>
      {/* 1. DISCIPLINED 1-ROW STATS STRIP (NO PILLS, TABULAR NUMBERS, STRICT GREEN/RED) */}
      <Card padding={2} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
        <HStack justify="between" align="center" wrap gap={3}>
          <HStack align="center" gap={2}>
            <Text weight="bold" size="md">Options Backtest Results</Text>
            <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
              • Alpaca • {data.strategy_revision} • {data.date_range.start} to {data.date_range.end}
            </Text>
          </HStack>

          <HStack align="center" gap={4}>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Net PnL (Worst / Best)</Text>
              <Text weight="bold" size="sm" style={{ color: "#3fb950", fontVariantNumeric: "tabular-nums" }}>
                {currency(data.summary.worst_net_pnl)} / {currency(data.summary.best_net_pnl)}
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Portfolio ROM</Text>
              <Text weight="bold" size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                {percentage(data.summary.portfolio_rom_pct)}
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Win Rate</Text>
              <Text weight="bold" size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                {data.summary.win_rate_pct.toFixed(1)}% ({data.summary.winning_trades}/{data.summary.total_trades})
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Max Drawdown</Text>
              <Text weight="bold" size="sm" style={{ color: "#f85149", fontVariantNumeric: "tabular-nums" }}>
                {data.summary.max_drawdown_pct}%
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Friction Drag</Text>
              <Text weight="bold" size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                ${data.summary.total_slippage_drag.toFixed(1)}
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Data Reliability</Text>
              <Text weight="bold" size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>
                {data.summary.overall_reliability_pct}%
              </Text>
            </VStack>
          </HStack>
        </HStack>
      </Card>

      {/* 2. INTERACTIVE TRADINGVIEW CANDLESTICK CHART */}
      <Card padding={3} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
        <VStack gap={2}>
          <HStack justify="between" align="center" wrap gap={2}>
            <HStack align="center" gap={2}>
              <Heading level={3} style={{ fontSize: "16px", fontWeight: "bold", margin: 0 }}>
                {selectedPos.security_id} {selectedPos.spread_type} (${selectedPos.short_strike}/${selectedPos.long_strike})
              </Heading>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
                • Credit: ${selectedPos.entry_credit.toFixed(2)} • Margin: ${selectedPos.margin_required.toFixed(2)}/sh
              </Text>
            </HStack>

            <ButtonGroup>
              {data.positions.map((p) => (
                <Button
                  key={p.id}
                  label={`${p.security_id} ${p.spread_type}`}
                  variant={p.id === selectedPos.id ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => {
                    setSelectedPosId(p.id);
                    setExpandedPosId(p.id);
                  }}
                />
              ))}
            </ButtonGroup>
          </HStack>

          <InteractiveCandlestickChart position={selectedPos} />

          {/* Under-Chart Narrative */}
          <HStack justify="between" align="center" wrap gap={2} style={{ borderTop: "1px solid #21262d", paddingTop: "8px" }}>
            <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
              Opened: {selectedPos.open_timestamp} ({selectedPos.open_rule}) ──► Closed: {selectedPos.close_timestamp} ({selectedPos.close_rule})
            </Text>
            <Text size="sm" style={{ color: selectedPos.counterfactual.outcome === "STOP_SAVED" ? "#3fb950" : "#8b949e" }}>
              {selectedPos.counterfactual.explanation}
            </Text>
          </HStack>
        </VStack>
      </Card>

      {/* 3. SPREAD LEDGER (SINGLE RESPONSIVE SCROLLBAR VIA TABLE) */}
      <Card padding={3} style={{ backgroundColor: "#161b22", border: "1px solid #30363d", width: "100%" }}>
        <VStack gap={2}>
          <HStack justify="between" align="center">
            <Heading level={3} style={{ fontSize: "16px", fontWeight: "bold", margin: 0 }}>
              Simulated Options Spreads Ledger
            </Heading>
            <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
              Click any trade row to load chart and inspect details:
            </Text>
          </HStack>

          <Table style={{ minWidth: "1480px" }}>
            <TableHeader>
              <TableRow>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "180px" }}>Security &amp; Expiry</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "220px" }}>Spread Type &amp; Strikes</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "90px" }}>Width</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "90px" }}>Credit</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "120px" }}>Margin Req</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "100px" }}>ROM (%)</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "110px" }}>Worst PnL</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "110px" }}>Best PnL</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "120px" }}>Holding</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "130px" }}>Stop Changes</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "170px" }}>Status / Outcome</TableHeaderCell>
                <TableHeaderCell style={{ ...cellStyle, minWidth: "110px" }}>Inspect</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.positions.map((pos: SpreadPositionDetail) => {
                const isSel = pos.id === selectedPos.id;
                const isExp = expandedPosId === pos.id;
                return (
                  <Fragment key={pos.id}>
                    <TableRow
                      key={pos.id}
                      onClick={() => {
                        setSelectedPosId(pos.id);
                        toggleExpand(pos.id);
                      }}
                      style={{
                        cursor: "pointer",
                        backgroundColor: isSel ? "rgba(56, 139, 253, 0.1)" : undefined,
                      }}
                    >
                      <TableCell style={cellStyle}>
                        <Text weight="bold">{pos.security_id}</Text>
                        {" "}
                        <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>{pos.expiration}</Text>
                      </TableCell>
                      <TableCell style={cellStyle}>
                        <Text>{pos.spread_type} (${pos.short_strike}/${pos.long_strike})</Text>
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        ${pos.width.toFixed(2)}
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        <Text weight="bold" style={{ color: "#3fb950" }}>${pos.entry_credit.toFixed(2)}</Text>
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        ${pos.margin_required.toFixed(2)}/sh
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        <Text weight="bold" style={{ color: pos.return_on_margin_pct >= 0 ? "#3fb950" : "#f85149" }}>
                          {percentage(pos.return_on_margin_pct)}
                        </Text>
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        <Text weight="bold" style={{ color: pos.worst_net_pnl >= 0 ? "#3fb950" : "#f85149" }}>
                          {currency(pos.worst_net_pnl)}
                        </Text>
                      </TableCell>
                      <TableCell style={{ ...cellStyle, fontVariantNumeric: "tabular-nums" }}>
                        <Text weight="bold" style={{ color: pos.best_net_pnl >= 0 ? "#3fb950" : "#f85149" }}>
                          {currency(pos.best_net_pnl)}
                        </Text>
                      </TableCell>
                      <TableCell style={cellStyle}>{pos.days_held} days</TableCell>
                      <TableCell style={cellStyle}>{pos.stop_movements.length} adjustments</TableCell>
                      <TableCell style={cellStyle}>
                        <Text
                          weight="medium"
                          style={{
                            color: pos.status.includes("Profit")
                              ? "#3fb950"
                              : pos.status.includes("Stop")
                              ? "#f85149"
                              : "#8b949e",
                          }}
                        >
                          {pos.status}
                        </Text>
                      </TableCell>
                      <TableCell style={cellStyle}>
                        <Button
                          label={isExp ? "Close Tray" : "Open Tray"}
                          variant="secondary"
                          size="sm"
                          onClick={() => toggleExpand(pos.id)}
                        />
                      </TableCell>
                    </TableRow>

                    {/* EXPANDABLE INLINE TABLE TRAY (SPACIOUS 2-COLUMN SPLIT WITH ZERO TEXT CLIPPING) */}
                    {isExp && (
                      <TableRow key={`${pos.id}_tray`}>
                        <TableCell colSpan={12} style={{ backgroundColor: "#0d1117", padding: "16px", borderTop: "1px solid #30363d", borderBottom: "1px solid #30363d" }}>
                          <VStack gap={3}>
                            <HStack justify="between" align="center">
                              <Heading level={4} style={{ fontSize: "14px", fontWeight: "bold", margin: 0 }}>
                                {pos.security_id} {pos.spread_type} (${pos.short_strike}/${pos.long_strike}) — Detailed Execution Audit
                              </Heading>
                              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
                                Quote Reliability: {pos.reliability_pct}% ({pos.missing_minutes_count} missing mins)
                              </Text>
                            </HStack>

                            <Grid columns={{ minWidth: 480, repeat: 2 }} gap={3}>
                              {/* LEFT COLUMN: Stop Ratchet Log */}
                              <Card padding={3} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
                                <VStack gap={2}>
                                  <Text weight="bold" size="sm">Stop Ratchet Adjustment Log</Text>
                                  <VStack gap={2}>
                                    {pos.stop_movements.map((st, i) => (
                                      <HStack key={i} justify="between" align="center" style={{ borderBottom: "1px solid #21262d", paddingBottom: "6px" }}>
                                        <VStack gap={0}>
                                          <Text size="sm" weight="bold" style={{ fontVariantNumeric: "tabular-nums" }}>{st.timestamp}</Text>
                                          <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>Rule: {st.trigger_rule}</Text>
                                        </VStack>
                                        <HStack gap={3} align="center">
                                          <Text size="sm" type="supporting">Underlying: ${st.underlying_price.toFixed(2)}</Text>
                                          <Text size="sm" weight="bold" style={{ color: "#f85149", fontVariantNumeric: "tabular-nums" }}>
                                            Stop: ${st.new_stop.toFixed(2)}
                                          </Text>
                                        </HStack>
                                      </HStack>
                                    ))}
                                  </VStack>
                                </VStack>
                              </Card>

                              {/* RIGHT COLUMN: Greeks & Financial Drag */}
                              <VStack gap={3}>
                                <Card padding={3} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
                                  <VStack gap={2}>
                                    <Text weight="bold" size="sm">Greeks Evolution Across Holding Period</Text>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Opening:</Text>
                                      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>{pos.greeks.entry.delta} Δ • Theta: +${pos.greeks.entry.theta}/d • Vega: {pos.greeks.entry.vega}</Text>
                                    </HStack>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Mid Hold:</Text>
                                      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>{pos.greeks.mid.delta} Δ • Theta: +${pos.greeks.mid.theta}/d • Gamma: {pos.greeks.mid.gamma}</Text>
                                    </HStack>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Exit:</Text>
                                      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums", color: pos.greeks.exit.gamma.includes("Critical") ? "#f85149" : "#c9d1d9" }}>
                                        {pos.greeks.exit.delta} Δ • Gamma: {pos.greeks.exit.gamma}
                                      </Text>
                                    </HStack>
                                  </VStack>
                                </Card>

                                <Card padding={3} style={{ backgroundColor: "#161b22", border: "1px solid #30363d" }}>
                                  <VStack gap={2}>
                                    <Text weight="bold" size="sm">Financial Risk &amp; Drag</Text>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Return on Margin (ROM):</Text>
                                      <Text size="sm" weight="bold" style={{ color: pos.return_on_margin_pct >= 0 ? "#3fb950" : "#f85149", fontVariantNumeric: "tabular-nums" }}>
                                        {percentage(pos.return_on_margin_pct)} (Annualized: {pos.annualized_rom_pct}%)
                                      </Text>
                                    </HStack>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Bid-Ask Spread Friction:</Text>
                                      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>${pos.bid_ask_spread_drag.toFixed(2)}</Text>
                                    </HStack>
                                    <HStack justify="between" align="center">
                                      <Text size="sm" type="supporting">Slippage Attribution:</Text>
                                      <Text size="sm" style={{ fontVariantNumeric: "tabular-nums" }}>${pos.slippage_cost.toFixed(2)} ({pos.execution_mode})</Text>
                                    </HStack>
                                  </VStack>
                                </Card>
                              </VStack>
                            </Grid>
                          </VStack>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </VStack>
      </Card>
    </VStack>
  );
}
