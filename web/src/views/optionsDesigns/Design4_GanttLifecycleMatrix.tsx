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

export function Design4_GanttLifecycleMatrix() {
  const data = MOCK_OPTIONS_DATASET;
  const [selectedPosId, setSelectedPosId] = useState<string>(data.positions[0]?.id || "");
  const [expandedPosId, setExpandedPosId] = useState<string | null>(null);

  const selectedPos: SpreadPositionDetail =
    data.positions.find((p) => p.id === selectedPosId) || data.positions[0];

  const toggleExpand = (id: string) => {
    setExpandedPosId((curr) => (curr === id ? null : id));
  };

  return (
    <VStack gap={3}>
      {/* 1. PULSE STRIP */}
      <Card padding={2}>
        <HStack justify="between" align="center" wrap gap={3}>
          <HStack align="center" gap={3}>
            <Token label="Alpaca Provider" color="blue" />
            <Text weight="bold">Gantt Lifecycle Matrix</Text>
            <Text type="supporting">Active Trades + Blocked Candidate Swimlanes</Text>
          </HStack>

          <HStack align="center" gap={4}>
            <Text size="sm" type="supporting">
              Portfolio ROM: <Text weight="bold">{percentage(data.summary.portfolio_rom_pct)}</Text>
            </Text>
            <Text size="sm" type="supporting">
              Max DD: <Text weight="bold" style={{ color: "var(--color-text-red)" }}>{data.summary.max_drawdown_pct}%</Text>
            </Text>
            <Text size="sm" type="supporting">
              Win Rate: <Text weight="bold">{data.summary.win_rate_pct.toFixed(1)}%</Text>
            </Text>
          </HStack>
        </HStack>
      </Card>

      {/* 2. HORIZONTAL LIFECYCLE SWIMLANES (ACTIVE & BLOCKED GHOSTS) */}
      <Card padding={3}>
        <VStack gap={2}>
          <HStack justify="between" align="center">
            <Heading level={3}>Trade Lifecycle Swimlanes (March - June 2024)</Heading>
            <HStack gap={3}>
              <Text size="sm" type="supporting"><Token label="Active Position" color="blue" /></Text>
              <Text size="sm" type="supporting"><Token label="Blocked Candidate" color="default" /></Text>
              <Text size="sm" type="supporting"><Token label="Quote Gap (>5m)" color="orange" /></Text>
            </HStack>
          </HStack>

          <VStack gap={2}>
            {/* Active Position Swimlanes */}
            {data.positions.map((pos) => {
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
                    <HStack align="center" gap={2}>
                      <Token label={pos.security_id} color="blue" />
                      <Text weight="bold">{pos.spread_type} (${pos.short_strike}/${pos.long_strike})</Text>
                      <Token label={`${pos.open_timestamp} → ${pos.close_timestamp}`} color="default" />
                      {pos.gaps.length > 0 && <Token label={`[!] Gap ${pos.gaps[0].duration_minutes}m`} color="orange" />}
                    </HStack>
                    <HStack align="center" gap={3}>
                      <Text size="sm" type="supporting">Ratchets: <Badge count={pos.stop_movements.length} /></Text>
                      <Text
                        size="sm"
                        weight="bold"
                        style={{ color: pos.worst_net_pnl >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}
                      >
                        Worst: {currency(pos.worst_net_pnl)} (ROM: {percentage(pos.return_on_margin_pct)})
                      </Text>
                      <Token
                        label={pos.status}
                        color={pos.status.includes("Profit") ? "green" : pos.status.includes("Stop") ? "orange" : "purple"}
                      />
                    </HStack>
                  </HStack>
                </Card>
              );
            })}

            {/* Blocked Candidate Ghost Swimlanes */}
            {data.blocked_candidates.map((blk) => (
              <Card
                key={blk.id}
                padding={2}
                style={{
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px dashed var(--color-border)",
                  opacity: 0.8,
                }}
              >
                <HStack justify="between" align="center">
                  <HStack align="center" gap={2}>
                    <Token label={blk.security_id} color="default" />
                    <Text type="supporting" weight="bold">SKIPPED: {blk.candidate_type}</Text>
                    <Token label={blk.timestamp} color="default" />
                    <Token label={blk.rule_id} color="orange" />
                  </HStack>
                  <Text size="sm" type="supporting">{blk.details}</Text>
                </HStack>
              </Card>
            ))}
          </VStack>
        </VStack>
      </Card>

      {/* 3. DENSE SPREAD LEDGER WITH EXPANDABLE TRAY */}
      <Card padding={3}>
        <VStack gap={2}>
          <Heading level={3}>Options Spread Ledger</Heading>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHeaderCell>Symbol</TableHeaderCell>
                <TableHeaderCell>Expiry</TableHeaderCell>
                <TableHeaderCell>Strikes</TableHeaderCell>
                <TableHeaderCell>Entry Credit</TableHeaderCell>
                <TableHeaderCell>Margin</TableHeaderCell>
                <TableHeaderCell>ROM %</TableHeaderCell>
                <TableHeaderCell>Worst PnL</TableHeaderCell>
                <TableHeaderCell>Action</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.positions.map((pos) => {
                const isExp = expandedPosId === pos.id;
                return (
                  <>
                    <TableRow key={pos.id} onClick={() => setSelectedPosId(pos.id)} style={{ cursor: "pointer" }}>
                      <TableCell><Token label={pos.security_id} color="blue" /></TableCell>
                      <TableCell>{pos.expiration}</TableCell>
                      <TableCell>{pos.short_strike}/{pos.long_strike}</TableCell>
                      <TableCell>${pos.entry_credit.toFixed(2)}</TableCell>
                      <TableCell>${pos.margin_required.toFixed(2)}/sh</TableCell>
                      <TableCell>
                        <Text weight="bold" style={{ color: pos.return_on_margin_pct >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}>
                          {percentage(pos.return_on_margin_pct)}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text weight="bold" style={{ color: pos.worst_net_pnl >= 0 ? "var(--color-text-green)" : "var(--color-text-red)" }}>
                          {currency(pos.worst_net_pnl)}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Button label={isExp ? "Hide" : "Tray"} variant="secondary" size="sm" onClick={() => toggleExpand(pos.id)} />
                      </TableCell>
                    </TableRow>

                    {isExp && (
                      <TableRow key={`${pos.id}_tray`}>
                        <TableCell colSpan={8} style={{ backgroundColor: "var(--color-background-surface)", padding: "12px" }}>
                          <Grid columns={{ minWidth: 260, repeat: 3 }} gap={2}>
                            <Card padding={2}>
                              <Text weight="bold" size="sm">Strike &amp; Stop Ratchet</Text>
                              <Text size="sm" type="supporting">Short Strike: ${pos.short_strike} | Long Strike: ${pos.long_strike}</Text>
                              <Text size="sm" type="supporting">Final Stop: ${pos.stop_movements[pos.stop_movements.length - 1]?.new_stop.toFixed(2)}</Text>
                            </Card>
                            <Card padding={2}>
                              <Text weight="bold" size="sm">Friction &amp; Slippage</Text>
                              <Text size="sm" type="supporting">Bid-Ask Drag: ${pos.bid_ask_spread_drag.toFixed(2)}</Text>
                              <Text size="sm" type="supporting">Slippage: ${pos.slippage_cost.toFixed(2)}</Text>
                            </Card>
                            <Card padding={2}>
                              <Text weight="bold" size="sm">Whipsaw Counterfactual</Text>
                              <Text size="sm">{pos.counterfactual.explanation}</Text>
                            </Card>
                          </Grid>
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
