import { useState } from "react";
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

export function Design3_HybridSplitCanvas() {
  const data = MOCK_OPTIONS_DATASET;
  const [selectedPosId, setSelectedPosId] = useState<string>(data.positions[0]?.id || "");
  const [expandedPosId, setExpandedPosId] = useState<string | null>(null);

  const selectedPos: SpreadPositionDetail =
    data.positions.find((p) => p.id === selectedPosId) || data.positions[0];

  const toggleExpand = (id: string) => {
    setExpandedPosId((curr) => (curr === id ? null : id));
  };

  const eq = data.equity_curve;
  const w = 400;
  const h = 180;
  const pad = 20;

  const pointsStrat = eq
    .map((p, i) => {
      const x = pad + (i / (eq.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((p.strategy_equity - 98000) / 8000) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const pointsBench = eq
    .map((p, i) => {
      const x = pad + (i / (eq.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((p.benchmark_equity - 98000) / 8000) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const traj = selectedPos.trajectory_points;
  const minU = Math.min(...traj.map((t) => t.underlying)) * 0.98;
  const maxU = Math.max(...traj.map((t) => t.underlying), selectedPos.short_strike, selectedPos.long_strike) * 1.02;

  const pointsUnderlying = traj
    .map((t, i) => {
      const x = pad + (i / (traj.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((t.underlying - minU) / (maxU - minU)) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <VStack gap={3}>
      {/* 1. PULSE STRIP */}
      <Card padding={2}>
        <HStack justify="between" align="center" wrap gap={3}>
          <HStack align="center" gap={3}>
            <Token label="Alpaca Provider" color="blue" />
            <Text weight="bold">Hybrid Split-Canvas Dashboard</Text>
            <Text type="supporting">Macro Portfolio + Micro Trade Corridor</Text>
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

      {/* 2. SPLIT 50/50 SYNCHRONIZED CANVASES */}
      <Grid columns={{ minWidth: 380, repeat: 2 }} gap={3}>
        {/* LEFT: Macro Cumulative Equity vs Benchmark */}
        <Card padding={3}>
          <VStack gap={2}>
            <HStack justify="between" align="center">
              <Heading level={3}>Macro Portfolio Equity</Heading>
              <HStack gap={2}>
                <Text size="sm" style={{ color: "var(--color-text-blue)" }}>— Strategy</Text>
                <Text size="sm" style={{ color: "var(--color-text-orange)" }}>- - S&amp;P 500</Text>
              </HStack>
            </HStack>

            <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "180px" }}>
              <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--color-border)" strokeWidth="1" />
              <polyline fill="none" stroke="var(--color-icon-orange)" strokeWidth="1.5" strokeDasharray="3 3" points={pointsBench} />
              <polyline fill="none" stroke="var(--color-icon-blue)" strokeWidth="2.5" points={pointsStrat} />
            </svg>

            <HStack justify="between">
              <Text size="sm" type="supporting">Base: $100,000</Text>
              <Text size="sm" weight="bold" style={{ color: "var(--color-text-green)" }}>
                Ending: {currency(data.summary.worst_net_pnl + 100000)}
              </Text>
            </HStack>
          </VStack>
        </Card>

        {/* RIGHT: Selected Trade Strike Corridor */}
        <Card padding={3}>
          <VStack gap={2}>
            <HStack justify="between" align="center">
              <HStack align="center" gap={2}>
                <Heading level={3}>{selectedPos.security_id} Strike Corridor</Heading>
                <Token label={selectedPos.spread_type} color="blue" />
              </HStack>
              <ButtonGroup>
                {data.positions.map((p) => (
                  <Button
                    key={p.id}
                    label={p.security_id}
                    variant={p.id === selectedPos.id ? "primary" : "secondary"}
                    size="sm"
                    onClick={() => setSelectedPosId(p.id)}
                  />
                ))}
              </ButtonGroup>
            </HStack>

            <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "180px" }}>
              {/* Shaded Strike Range */}
              <rect x={pad} y={pad + 15} width={w - 2 * pad} height={35} fill="var(--color-icon-red)" opacity="0.15" />
              <line x1={pad} y1={pad + 15} x2={w - pad} y2={pad + 15} stroke="var(--color-icon-orange)" strokeWidth="1.5" strokeDasharray="3 3" />
              <line x1={pad} y1={pad + 50} x2={w - pad} y2={pad + 50} stroke="var(--color-icon-purple)" strokeWidth="1.5" strokeDasharray="3 3" />
              {/* Stock trajectory */}
              <polyline fill="none" stroke="var(--color-icon-blue)" strokeWidth="2.5" points={pointsUnderlying} />
            </svg>

            <HStack justify="between">
              <Text size="sm" type="supporting">Credit: ${selectedPos.entry_credit}</Text>
              <Token
                label={selectedPos.counterfactual.outcome === "STOP_SAVED" ? "Stop Saved +$550" : "Normal Profit"}
                color={selectedPos.counterfactual.outcome === "STOP_SAVED" ? "green" : "purple"}
              />
            </HStack>
          </VStack>
        </Card>
      </Grid>

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
                <TableHeaderCell>Credit</TableHeaderCell>
                <TableHeaderCell>Margin</TableHeaderCell>
                <TableHeaderCell>ROM %</TableHeaderCell>
                <TableHeaderCell>Worst PnL</TableHeaderCell>
                <TableHeaderCell>Friction</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
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
                      <TableCell>${pos.bid_ask_spread_drag.toFixed(2)}</TableCell>
                      <TableCell><Token label={pos.status} color="purple" /></TableCell>
                      <TableCell>
                        <Button label={isExp ? "Hide" : "Tray"} variant="secondary" size="sm" onClick={() => toggleExpand(pos.id)} />
                      </TableCell>
                    </TableRow>

                    {isExp && (
                      <TableRow key={`${pos.id}_tray`}>
                        <TableCell colSpan={10} style={{ backgroundColor: "var(--color-background-surface)", padding: "12px" }}>
                          <HStack justify="between" align="center">
                            <Text size="sm" type="supporting">
                              Entry: {pos.open_timestamp} ({pos.open_rule}) ──► Exit: {pos.close_timestamp} ({pos.close_rule})
                            </Text>
                            <Text size="sm" weight="bold">{pos.counterfactual.explanation}</Text>
                          </HStack>
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
