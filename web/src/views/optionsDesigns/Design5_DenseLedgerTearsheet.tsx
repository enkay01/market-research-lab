import { useState } from "react";
import {
  Badge,
  Button,
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

export function Design5_DenseLedgerTearsheet() {
  const data = MOCK_OPTIONS_DATASET;
  const [expandedPosId, setExpandedPosId] = useState<string | null>(data.positions[0]?.id || null);

  const toggleExpand = (id: string) => {
    setExpandedPosId((curr) => (curr === id ? null : id));
  };

  return (
    <VStack gap={3}>
      {/* 1. INSTITUTIONAL TEAR-SHEET HEADER (2-ROW DENSE STATS) */}
      <Card padding={3}>
        <VStack gap={2}>
          <HStack justify="between" align="center" wrap gap={3}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Options Quantitative Tear-Sheet</Heading>
              <Token label="Alpaca Provider" color="blue" />
              <Token label={data.strategy_revision} color="purple" />
            </HStack>
            <Text type="supporting">{data.date_range.start} to {data.date_range.end}</Text>
          </HStack>

          <Grid columns={{ minWidth: 220, repeat: "fit" }} gap={2}>
            <Card padding={2}>
              <Text size="sm" type="supporting">Net PnL (Worst / Best)</Text>
              <Text weight="bold" size="lg" style={{ color: "var(--color-text-green)" }}>
                {currency(data.summary.worst_net_pnl)} / {currency(data.summary.best_net_pnl)}
              </Text>
            </Card>
            <Card padding={2}>
              <Text size="sm" type="supporting">Portfolio ROM %</Text>
              <Text weight="bold" size="lg">{percentage(data.summary.portfolio_rom_pct)}</Text>
            </Card>
            <Card padding={2}>
              <Text size="sm" type="supporting">Win Rate / Expectancy</Text>
              <Text weight="bold" size="lg">{data.summary.win_rate_pct.toFixed(1)}% ({currency(data.summary.expectancy_per_trade)}/tr)</Text>
            </Card>
            <Card padding={2}>
              <Text size="sm" type="supporting">Max Drawdown</Text>
              <Text weight="bold" size="lg" style={{ color: "var(--color-text-red)" }}>{data.summary.max_drawdown_pct}%</Text>
            </Card>
            <Card padding={2}>
              <Text size="sm" type="supporting">Friction &amp; Slippage Drag</Text>
              <Text weight="bold" size="lg">${data.summary.total_slippage_drag.toFixed(1)}</Text>
            </Card>
            <Card padding={2}>
              <Text size="sm" type="supporting">Total Margin Capacity</Text>
              <Text weight="bold" size="lg">${data.summary.total_margin_allocated.toLocaleString()}</Text>
            </Card>
          </Grid>
        </VStack>
      </Card>

      {/* 2. DENSE MASTER TABLE WITH EXPANDABLE INSPECTION COCKPIT TRAY */}
      <Card padding={3} style={{ width: "100%", overflowX: "auto" }}>
        <VStack gap={2}>
          <HStack justify="between" align="center">
            <Heading level={3}>Options Trade Master Ledger</Heading>
            <Text type="supporting">Click any row to open the Deep Inspection Cockpit Tray:</Text>
          </HStack>

          <Table style={{ minWidth: "1200px" }}>
            <TableHeader>
              <TableRow>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Security &amp; Expiry</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Type</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Strikes</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Width</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Delta / IV</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Credit</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Margin Req</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>ROM (%)</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Worst PnL</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Best PnL</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Days</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Ratchets</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Status</TableHeaderCell>
                <TableHeaderCell style={{ whiteSpace: "nowrap" }}>Cockpit</TableHeaderCell>
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
                      <TableCell style={{ whiteSpace: "nowrap" }}>{pos.spread_type}</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>{pos.short_strike}/{pos.long_strike}</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>${pos.width.toFixed(2)}</TableCell>
                      <TableCell style={{ whiteSpace: "nowrap" }}>{pos.short_delta}Δ / {(pos.implied_volatility * 100).toFixed(1)}%</TableCell>
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
                        <Button label={isExp ? "Close" : "Open"} variant="secondary" size="sm" onClick={() => toggleExpand(pos.id)} />
                      </TableCell>
                    </TableRow>

                    {/* EXPANDABLE DEEP INSPECTION COCKPIT TRAY */}
                    {isExp && (
                      <TableRow key={`${pos.id}_tray`}>
                        <TableCell colSpan={14} style={{ backgroundColor: "var(--color-background-surface)", padding: "16px" }}>
                          <VStack gap={3}>
                            <HStack justify="between" align="center">
                              <Heading level={4}>
                                {pos.security_id} {pos.spread_type} (${pos.short_strike}/${pos.long_strike}) — Deep Execution &amp; Risk Cockpit
                              </Heading>
                              <Token
                                label={`Whipsaw Diagnostic: ${pos.counterfactual.outcome}`}
                                color={pos.counterfactual.outcome === "STOP_SAVED" ? "green" : "purple"}
                              />
                            </HStack>

                            <Grid columns={{ minWidth: 280, repeat: 4 }} gap={2}>
                              <Card padding={2}>
                                <Text weight="bold" size="sm">1. Event Lifecycle</Text>
                                <Text size="sm" type="supporting">Opened: {pos.open_timestamp} ({pos.open_rule})</Text>
                                <Text size="sm" type="supporting">Closed: {pos.close_timestamp} ({pos.close_rule})</Text>
                                <Text size="sm" type="supporting">Ratchets: {pos.stop_movements.length} adjustments</Text>
                              </Card>

                              <Card padding={2}>
                                <Text weight="bold" size="sm">2. Greeks Evolution</Text>
                                <Text size="sm" type="supporting">Entry: {pos.greeks.entry.delta}Δ | Theta: +${pos.greeks.entry.theta}/day</Text>
                                <Text size="sm" type="supporting">Exit: {pos.greeks.exit.delta}Δ | Gamma: {pos.greeks.exit.gamma}</Text>
                              </Card>

                              <Card padding={2}>
                                <Text weight="bold" size="sm">3. Financial Friction</Text>
                                <Text size="sm" type="supporting">Bid-Ask Drag: ${pos.bid_ask_spread_drag.toFixed(2)}</Text>
                                <Text size="sm" type="supporting">Slippage vs Mid: ${pos.slippage_cost.toFixed(2)}</Text>
                                <Text size="sm" type="supporting">Execution: {pos.execution_mode}</Text>
                              </Card>

                              <Card padding={2}>
                                <Text weight="bold" size="sm">4. Counterfactual</Text>
                                <Text size="sm">{pos.counterfactual.explanation}</Text>
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
