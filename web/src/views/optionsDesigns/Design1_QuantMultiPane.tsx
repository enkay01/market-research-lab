import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Divider,
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
  Token,
  VStack,
} from "@astryxdesign/core";
import {
  MOCK_OPTIONS_DATASET,
  type SpreadPositionDetail,
} from "./designData";

function percentage(val: number): string {
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

function currency(val: number): string {
  const sign = val > 0 ? "+" : val < 0 ? "-" : "";
  return `${sign}$${Math.abs(val).toFixed(2)}`;
}

export function Design1_QuantMultiPane() {
  const data = MOCK_OPTIONS_DATASET;
  const [expandedPosId, setExpandedPosId] = useState<string | null>(data.positions[0]?.id || null);

  const toggleExpand = (id: string) => {
    setExpandedPosId((curr) => (curr === id ? null : id));
  };

  // Stacked Charts Dimensions
  const width = 860;
  const pane1Height = 110;
  const pane2Height = 60;
  const pane3Height = 45;
  const pad = 24;

  const eq = data.equity_curve;
  const minEq = 98000;
  const maxEq = 106000;

  const pointsStrat = eq
    .map((p, i) => {
      const x = pad + (i / (eq.length - 1)) * (width - 2 * pad);
      const y = pane1Height - 10 - ((p.strategy_equity - minEq) / (maxEq - minEq)) * (pane1Height - 20);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const pointsBench = eq
    .map((p, i) => {
      const x = pad + (i / (eq.length - 1)) * (width - 2 * pad);
      const y = pane1Height - 10 - ((p.benchmark_equity - minEq) / (maxEq - minEq)) * (pane1Height - 20);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <VStack gap={3}>
      {/* 1. LEVEL 1: THE PULSE STRIP (1-Row Summary Stats like Reference Image 1 & 3) */}
      <Card padding={2}>
        <HStack justify="between" align="center" wrap gap={3}>
          <HStack align="center" gap={3}>
            <Token label="Alpaca Provider" color="blue" />
            <Text weight="bold">{data.strategy_name}:v2</Text>
            <Text type="supporting">{data.date_range.start} to {data.date_range.end}</Text>
          </HStack>

          <HStack align="center" gap={4}>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Worst / Best PnL</Text>
              <Text weight="bold" style={{ color: "var(--color-text-green)" }}>
                {currency(data.summary.worst_net_pnl)} / {currency(data.summary.best_net_pnl)}
              </Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Portfolio ROM</Text>
              <Text weight="bold">{percentage(data.summary.portfolio_rom_pct)}</Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Win Rate</Text>
              <Text weight="bold">{data.summary.win_rate_pct.toFixed(1)}% ({data.summary.winning_trades}/{data.summary.total_trades})</Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Max Drawdown</Text>
              <Text weight="bold" style={{ color: "var(--color-text-red)" }}>{data.summary.max_drawdown_pct}%</Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Friction / Slippage</Text>
              <Text weight="bold">${data.summary.total_slippage_drag.toFixed(1)}</Text>
            </VStack>
            <VStack gap={0}>
              <Text size="sm" type="supporting">Data Reliability</Text>
              <Text weight="bold">{data.summary.overall_reliability_pct}%</Text>
            </VStack>
          </HStack>
        </HStack>
      </Card>

      {/* 2. LEVEL 2: 3 STACKED SYNCHRONIZED TIME-SERIES PANES (Image 3 Style) */}
      <Card padding={3}>
        <VStack gap={1}>
          <HStack justify="between" align="center">
            <Heading level={3}>Synchronized Portfolio &amp; Risk Time-Series</Heading>
            <HStack gap={3}>
              <Text size="sm" type="supporting" style={{ color: "var(--color-text-blue)" }}>— Strategy Equity</Text>
              <Text size="sm" type="supporting" style={{ color: "var(--color-text-orange)" }}>- - S&amp;P 500 Benchmark</Text>
              <Text size="sm" type="supporting" style={{ color: "var(--color-text-purple)" }}>■ Margin Utilization %</Text>
              <Text size="sm" type="supporting" style={{ color: "var(--color-text-secondary)" }}>■ # Open Positions</Text>
            </HStack>
          </HStack>

          {/* Pane 1: Return % / Equity Curve */}
          <svg viewBox={`0 0 ${width} ${pane1Height}`} style={{ width: "100%", height: "110px", overflow: "visible" }}>
            <line x1={pad} y1={pane1Height - 10} x2={width - pad} y2={pane1Height - 10} stroke="var(--color-border)" strokeWidth="1" />
            <polyline fill="none" stroke="var(--color-icon-orange)" strokeWidth="1.5" strokeDasharray="3 3" points={pointsBench} />
            <polyline fill="none" stroke="var(--color-icon-blue)" strokeWidth="2.5" points={pointsStrat} />
            <text x={pad} y={20} fill="var(--color-text-supporting)" fontSize="11">Equity ($100k Base)</text>
          </svg>

          {/* Pane 2: Margin Utilization % with Data Gap Markers */}
          <svg viewBox={`0 0 ${width} ${pane2Height}`} style={{ width: "100%", height: "60px", overflow: "visible" }}>
            <line x1={pad} y1={pane2Height - 5} x2={width - pad} y2={pane2Height - 5} stroke="var(--color-border)" strokeWidth="1" />
            {eq.map((p, i) => {
              const x = pad + (i / (eq.length - 1)) * (width - 2 * pad);
              const barH = (p.margin_util_pct / 50) * (pane2Height - 15);
              return (
                <rect key={i} x={x - 8} y={pane2Height - 5 - barH} width={16} height={barH} fill="var(--color-icon-purple)" opacity="0.65" rx="2" />
              );
            })}
            {/* Yellow Data Gap Tick Indicator at 04-10 */}
            <line x1={pad + 0.38 * (width - 2 * pad)} y1={5} x2={pad + 0.38 * (width - 2 * pad)} y2={pane2Height - 5} stroke="var(--color-icon-orange)" strokeWidth="3" strokeDasharray="2 2" />
            <text x={pad} y={15} fill="var(--color-text-supporting)" fontSize="10">Margin Util % (Peak 42%) | [!] Gap Warning</text>
          </svg>

          {/* Pane 3: Active Position Concurrency */}
          <svg viewBox={`0 0 ${width} ${pane3Height}`} style={{ width: "100%", height: "45px", overflow: "visible" }}>
            <line x1={pad} y1={pane3Height - 5} x2={width - pad} y2={pane3Height - 5} stroke="var(--color-border)" strokeWidth="1" />
            {eq.map((p, i) => {
              const x = pad + (i / (eq.length - 1)) * (width - 2 * pad);
              const barH = (p.open_positions_count / 4) * (pane3Height - 12);
              return (
                <rect key={i} x={x - 8} y={pane3Height - 5 - barH} width={16} height={barH} fill="var(--color-text-supporting)" opacity="0.5" rx="2" />
              );
            })}
            <text x={pad} y={14} fill="var(--color-text-supporting)" fontSize="10"># Concurrent Open Spreads (Max 3)</text>
          </svg>

          <HStack justify="between">
            <Text size="sm" type="supporting">{eq[0]?.date}</Text>
            <Text size="sm" type="supporting">{eq[eq.length - 1]?.date}</Text>
          </HStack>
        </VStack>
      </Card>

      {/* 3. LEVEL 3: DENSE SPREAD LEDGER WITH EXPANDABLE TABLE TRAY (Table Tray Style) */}
      <Card padding={3} style={{ width: "100%", overflowX: "auto" }}>
        <VStack gap={3}>
          <HStack justify="between" align="center">
            <Heading level={3}>Simulated Options Spread Ledger</Heading>
            <Text type="supporting">Click any row to open the integrated 3-column trade inspection tray:</Text>
          </HStack>

          <Table style={{ minWidth: "1150px" }}>
            <TableHeader>
              <TableRow>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Security &amp; Expiry</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Spread Type &amp; Strikes</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Width</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Credit</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Margin Req</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>ROM (%)</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Worst PnL</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Best PnL</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Days Held</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Stop Changes</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Status / Outcome</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Action</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.positions.map((pos: SpreadPositionDetail) => {
                const isExp = expandedPosId === pos.id;
                return (
                  <>
                    <TableRow
                      key={pos.id}
                      onClick={() => toggleExpand(pos.id)}
                      style={{
                        cursor: "pointer",
                        backgroundColor: isExp ? "var(--color-background-wash)" : undefined,
                      }}
                    >
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <HStack gap={1} align="center">
                          <Token label={pos.security_id} color="blue" />
                          <Text weight="bold">{pos.expiration}</Text>
                        </HStack>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Text>{pos.spread_type} ({pos.short_strike}/{pos.long_strike})</Text>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>${pos.width.toFixed(2)}</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Text weight="bold" style={{ color: "var(--color-text-green)" }}>${pos.entry_credit.toFixed(2)}</Text>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>${pos.margin_required.toFixed(2)}/sh</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Text weight="bold" style={{ color: pos.return_on_margin_pct >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}>
                          {percentage(pos.return_on_margin_pct)}
                        </Text>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Text weight="bold" style={{ color: pos.worst_net_pnl >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}>
                          {currency(pos.worst_net_pnl)}
                        </Text>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Text weight="bold" style={{ color: pos.best_net_pnl >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}>
                          {currency(pos.best_net_pnl)}
                        </Text>
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>{pos.days_held}d</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}><Badge count={pos.stop_movements.length} /></TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Token
                          label={pos.status}
                          color={pos.status.includes("Profit") ? "green" : pos.status.includes("Stop") ? "orange" : "purple"}
                        />
                      </TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>
                        <Button label={isExp ? "Close Tray" : "Open Tray"} variant="secondary" size="sm" onClick={() => toggleExpand(pos.id)} />
                      </TableCell>
                    </TableRow>

                    {/* EXPANDABLE INLINE TABLE TRAY (3-COLUMN AUDIT COCKPIT) */}
                    {isExp && (
                      <TableRow key={`${pos.id}_tray`}>
                        <TableCell colSpan={12} style={{ backgroundColor: "var(--color-background-surface)", padding: "16px" }}>
                          <VStack gap={3}>
                            <HStack justify="between" align="center">
                              <Heading level={4}>
                                {pos.security_id} {pos.spread_type} (${pos.short_strike}/${pos.long_strike}) — Integrated Inspection Tray
                              </Heading>
                              <Token
                                label={pos.counterfactual.outcome === "STOP_SAVED" ? "Stop Saved: Avoided Max Loss" : "Normal Profit Outcome"}
                                color={pos.counterfactual.outcome === "STOP_SAVED" ? "green" : "purple"}
                              />
                            </HStack>

                            <Grid columns={{ minWidth: 320, repeat: 3 }} gap={3}>
                              {/* TRAY COL 1: Strike Channel & Ratchet Mini Chart */}
                              <Card padding={2}>
                                <VStack gap={2}>
                                  <Text weight="bold" size="sm">1. Strike Channel &amp; Ratchet Corridor</Text>
                                  <svg viewBox="0 0 320 120" style={{ width: "100%", height: "120px" }}>
                                    {/* Shaded Strike Range */}
                                    <rect x="20" y="25" width="280" height="40" fill="var(--color-icon-red)" opacity="0.15" />
                                    <line x1="20" y1="25" x2="300" y2="25" stroke="var(--color-icon-red)" strokeWidth="1.5" strokeDasharray="3 3" />
                                    <line x1="20" y1="65" x2="300" y2="65" stroke="var(--color-icon-orange)" strokeWidth="1.5" />
                                    {/* Underlying Trajectory */}
                                    <polyline
                                      fill="none"
                                      stroke="var(--color-icon-blue)"
                                      strokeWidth="2"
                                      points="30,85 90,82 150,60 210,40 270,30"
                                    />
                                    {/* Stop Ratchet Step */}
                                    <polyline fill="none" stroke="var(--color-icon-red)" strokeWidth="2" strokeDasharray="4 2" points="30,15 150,15 150,35 270,35" />
                                  </svg>
                                  <HStack justify="between">
                                    <Text size="sm" type="supporting">Short Strike: ${pos.short_strike}</Text>
                                    <Text size="sm" type="supporting">Stop: ${pos.stop_movements[pos.stop_movements.length - 1]?.new_stop.toFixed(2)}</Text>
                                  </HStack>
                                </VStack>
                              </Card>

                              {/* TRAY COL 2: Chronological Event Reel */}
                              <Card padding={2}>
                                <VStack gap={2}>
                                  <Text weight="bold" size="sm">2. Chronological Event Reel</Text>
                                  <VStack gap={1}>
                                    <HStack justify="between">
                                      <Text size="sm" weight="bold">Entry: {pos.open_timestamp}</Text>
                                      <Token label={pos.open_rule} color="purple" />
                                    </HStack>
                                    <Text size="sm" type="supporting">Credit: ${pos.entry_credit} | Delta: {pos.short_delta} | IV: {(pos.implied_volatility * 100).toFixed(1)}%</Text>
                                    
                                    <Divider />
                                    
                                    <HStack justify="between">
                                      <Text size="sm" weight="bold">Exit: {pos.close_timestamp}</Text>
                                      <Token label={pos.close_rule} color="orange" />
                                    </HStack>
                                    <Text size="sm" type="supporting">Worst fill: ${pos.worst_net_pnl} | Slip: ${pos.slippage_cost}</Text>
                                  </VStack>
                                </VStack>
                              </Card>

                              {/* TRAY COL 3: Risk & Friction Drag Breakdown */}
                              <Card padding={2}>
                                <VStack gap={2}>
                                  <Text weight="bold" size="sm">3. Financial Friction &amp; Counterfactual</Text>
                                  <Table>
                                    <TableBody>
                                      <TableRow>
                                        <TableCell><Text size="sm" type="supporting">Return on Margin (ROM)</Text></TableCell>
                                        <TableCell><Text size="sm" weight="bold">{percentage(pos.return_on_margin_pct)}</Text></TableCell>
                                      </TableRow>
                                      <TableRow>
                                        <TableCell><Text size="sm" type="supporting">Bid-Ask Friction Drag</Text></TableCell>
                                        <TableCell><Text size="sm">${pos.bid_ask_spread_drag.toFixed(2)}</Text></TableCell>
                                      </TableRow>
                                      <TableRow>
                                        <TableCell><Text size="sm" type="supporting">Whipsaw Counterfactual</Text></TableCell>
                                        <TableCell><Text size="sm">{pos.counterfactual.explanation}</Text></TableCell>
                                      </TableRow>
                                    </TableBody>
                                  </Table>
                                </VStack>
                              </Card>
                            </Grid>
                          </VStack>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                );
              })}
            </TableBody>
          </Table>
        </VStack>
      </Card>
    </VStack>
  );
}
