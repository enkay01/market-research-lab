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
  StatusDot,
} from "@astryxdesign/core";
import type { Project } from "../api/client";

interface AlertsViewProps {
  project?: Project;
  engineConnected: boolean;
}

export function AlertsView({ project, engineConnected }: AlertsViewProps) {
  const [isRefreshing, setIsRefreshing] = useState(false);

  function handleRefresh() {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1000);
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>
                Strategy Signals & Local Alerts
              </Heading>
              <Badge label="2 Alerts" variant="error" />
              <HStack align="center" gap={1}>
                <StatusDot
                  variant={engineConnected ? "success" : "error"}
                  label={engineConnected ? "Engine Live" : "Engine Offline"}
                />
                <Text type="supporting">
                  {engineConnected ? "Engine Live" : "Engine Offline"}
                </Text>
              </HStack>
              {project && <Token label={`Project: ${project.name}`} color="blue" />}
            </HStack>

            <HStack gap={2}>
              <Button
                label="Evaluate Enabled Strategies"
                variant="primary"
                size="sm"
                onClick={handleRefresh}
                isLoading={isRefreshing}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            <Banner status="info" title="Local Safety Boundary (ADR 0002)">
              The system produces local notifications for research analysis only. It never connects to a broker or executes orders.
            </Banner>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Signal Time</TableHeaderCell>
                  <TableHeaderCell>Security</TableHeaderCell>
                  <TableHeaderCell>Strategy Revision</TableHeaderCell>
                  <TableHeaderCell>Action Signal</TableHeaderCell>
                  <TableHeaderCell>Target Weight</TableHeaderCell>
                  <TableHeaderCell>Trigger Rationale</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>2026-08-15 16:00 EST</TableCell>
                  <TableCell><Text weight="bold">AAPL</Text></TableCell>
                  <TableCell><Token label="SMA Crossover v2" color="purple" /></TableCell>
                  <TableCell><Token label="BUY / LONG" color="green" /></TableCell>
                  <TableCell><Text weight="bold">100.0%</Text></TableCell>
                  <TableCell>Fast 20 SMA crossed above Slow 50 SMA on latest eligible daily bar.</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>2026-08-14 16:00 EST</TableCell>
                  <TableCell><Text weight="bold">MSFT</Text></TableCell>
                  <TableCell><Token label="FCFF Value Filter v1" color="purple" /></TableCell>
                  <TableCell><Token label="HOLD" color="blue" /></TableCell>
                  <TableCell><Text weight="bold">50.0%</Text></TableCell>
                  <TableCell>Fair value discount &gt; 15% to market price.</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </VStack>
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={380}
          hasDivider
          isScrollable
          label="Strategy Status"
        >
          <VStack gap={4} style={{ padding: "16px" }}>
            <Heading level={3}>
              Enabled Strategies
            </Heading>

            <VStack gap={2}>
              <VStack
                gap={1}
                style={{
                  padding: "12px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <HStack justify="between" align="center">
                  <Text weight="bold">SMA Crossover Strategy</Text>
                  <Token label="Enabled" color="green" />
                </HStack>
                <Text type="supporting">Target Universe: AAPL, MSFT</Text>
                <Text type="supporting">Last evaluated: 2026-08-15 22:00 UTC</Text>
              </VStack>

              <VStack
                gap={1}
                style={{
                  padding: "12px",
                  borderRadius: "var(--radius-md, 6px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <HStack justify="between" align="center">
                  <Text weight="bold">FCFF Value Strategy</Text>
                  <Token label="Enabled" color="green" />
                </HStack>
                <Text type="supporting">Target Universe: AAPL</Text>
                <Text type="supporting">Last evaluated: 2026-08-15 22:00 UTC</Text>
              </VStack>
            </VStack>
          </VStack>
        </LayoutPanel>
      }
    />
  );
}

