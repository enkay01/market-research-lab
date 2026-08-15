import { useState } from "react";
import {
  Layout,
  LayoutHeader,
  LayoutContent,
  LayoutPanel,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  VStack,
  HStack,
  Button,
  Heading,
  Text,
  Badge,
  Token,
  Banner,
} from "@astryxdesign/core";
import type { Project } from "../api/client";

interface BacktestViewProps {
  project?: Project;
}

export function BacktestView({ project }: BacktestViewProps) {
  const [isRunning, setIsRunning] = useState(false);

  function handleRunBacktest() {
    setIsRunning(true);
    setTimeout(() => setIsRunning(false), 1500);
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>
                Backtest Simulation Engine
              </Heading>
              <Token label="Strategy: MA Crossover v1" color="purple" />
              {project && <Badge label={`Project: ${project.name}`} variant="purple" />}
            </HStack>

            <HStack gap={2}>
              <Button label="Export HTML Report" variant="secondary" size="sm" />
              <Button
                label="Execute Backtest Run"
                variant="primary"
                size="sm"
                onClick={handleRunBacktest}
                isLoading={isRunning}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            {/* KPI Summary Tiles */}
            <HStack gap={3}>
              <VStack
                gap={1}
                style={{
                  flex: 1,
                  padding: "14px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <Text type="supporting">Total Return</Text>
                <Text weight="bold">+42.8%</Text>
                <Text type="supporting">Benchmark (SPY): +28.4%</Text>
              </VStack>

              <VStack
                gap={1}
                style={{
                  flex: 1,
                  padding: "14px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <Text type="supporting">Sharpe Ratio</Text>
                <Text weight="bold">1.84</Text>
                <Text type="supporting">Sortino: 2.31</Text>
              </VStack>

              <VStack
                gap={1}
                style={{
                  flex: 1,
                  padding: "14px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <Text type="supporting">Max Drawdown</Text>
                <Text weight="bold">-8.2%</Text>
                <Text type="supporting">Calmar: 2.14</Text>
              </VStack>

              <VStack
                gap={1}
                style={{
                  flex: 1,
                  padding: "14px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <Text type="supporting">Win Rate / Trades</Text>
                <Text weight="bold">64.3%</Text>
                <Text type="supporting">28 total fills</Text>
              </VStack>
            </HStack>

            {/* Fills & Trade Ledger */}
            <VStack gap={2}>
              <Heading level={3}>
                Simulated Execution Ledger & Fills
              </Heading>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Fill Date</TableHeaderCell>
                    <TableHeaderCell>Security</TableHeaderCell>
                    <TableHeaderCell>Side</TableHeaderCell>
                    <TableHeaderCell>Qty</TableHeaderCell>
                    <TableHeaderCell>Fill Price</TableHeaderCell>
                    <TableHeaderCell>Slippage & Fees</TableHeaderCell>
                    <TableHeaderCell>Portfolio Cash</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>2024-06-21</TableCell>
                    <TableCell><Text weight="bold">AAPL</Text></TableCell>
                    <TableCell><Token label="BUY" color="green" /></TableCell>
                    <TableCell>480</TableCell>
                    <TableCell>$207.50</TableCell>
                    <TableCell>$1.44</TableCell>
                    <TableCell>$400.00</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>2024-05-14</TableCell>
                    <TableCell><Text weight="bold">AAPL</Text></TableCell>
                    <TableCell><Token label="SELL (FLAT)" color="purple" /></TableCell>
                    <TableCell>525</TableCell>
                    <TableCell>$189.98</TableCell>
                    <TableCell>$1.58</TableCell>
                    <TableCell>$100,000.00</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </VStack>
          </VStack>
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={380}
          hasDivider
          isScrollable
          label="Backtest Assumptions"
        >
          <VStack gap={4} style={{ padding: "16px" }}>
            <Heading level={3}>
              Execution Model Assumptions
            </Heading>

            <Banner status="info" title="Point-in-Time Execution">
              Signals calculated on daily bar close execute on next-day open with 2 bps modeled slippage.
            </Banner>

            <Table>
              <TableBody>
                <TableRow>
                  <TableCell><Text type="supporting">Starting Cash</Text></TableCell>
                  <TableCell><Text weight="bold">$100,000 USD</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Commission</Text></TableCell>
                  <TableCell><Text>$0.005 / share</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Slippage Model</Text></TableCell>
                  <TableCell><Text>2.0 bps fixed</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Short Borrow Rate</Text></TableCell>
                  <TableCell><Text>1.5% annual</Text></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Text type="supporting">Cash Interest</Text></TableCell>
                  <TableCell><Text>4.0% annual</Text></TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </VStack>
        </LayoutPanel>
      }
    />
  );
}

