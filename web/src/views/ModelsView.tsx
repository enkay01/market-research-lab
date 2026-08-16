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
  SegmentedControl,
  SegmentedControlItem,
  TextInput,
} from "@astryxdesign/core";
import type { Project } from "../api/client";

interface ModelsViewProps {
  project?: Project;
}

export function ModelsView({ project }: ModelsViewProps) {
  const [activeTab, setActiveTab] = useState<"indicators" | "predictive">("indicators");
  const [fastPeriod, setFastPeriod] = useState("20");
  const [slowPeriod, setSlowPeriod] = useState("50");
  const [modelType, setModelType] = useState<"baseline" | "lightgbm">("baseline");

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>
                Indicators & Predictive Models
              </Heading>
              <SegmentedControl
                label="Model Workspace Mode"
                value={activeTab}
                onChange={(val) => setActiveTab(val as "indicators" | "predictive")}
              >
                <SegmentedControlItem value="indicators" label="Technical Indicators" />
                <SegmentedControlItem value="predictive" label="Predictive Models (Walk-Forward)" />
              </SegmentedControl>
            </HStack>

            <HStack gap={2}>
              {project && <Badge label={`Project: ${project.name}`} variant="purple" />}
              <Button label="Execute Run" variant="primary" size="sm" />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          {activeTab === "indicators" ? (
            <VStack gap={4}>
              <Heading level={3}>
                Moving Average Crossover Indicator Series (AAPL)
              </Heading>
              <Text type="supporting">
                Time-aligned transformation with warm-up periods explicitly marked as missing.
              </Text>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Session Date</TableHeaderCell>
                    <TableHeaderCell>Close Price</TableHeaderCell>
                    <TableHeaderCell>SMA ({fastPeriod})</TableHeaderCell>
                    <TableHeaderCell>SMA ({slowPeriod})</TableHeaderCell>
                    <TableHeaderCell>Spread</TableHeaderCell>
                    <TableHeaderCell>Indicator State</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>2024-06-20</TableCell>
                    <TableCell>$209.68</TableCell>
                    <TableCell>$198.42</TableCell>
                    <TableCell>$187.10</TableCell>
                    <TableCell>+$11.32</TableCell>
                    <TableCell><Token label="Bullish Above Slow" color="green" /></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>2024-06-21</TableCell>
                    <TableCell>$207.49</TableCell>
                    <TableCell>$199.12</TableCell>
                    <TableCell>$187.65</TableCell>
                    <TableCell>+$11.47</TableCell>
                    <TableCell><Token label="Bullish Above Slow" color="green" /></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>2024-06-24</TableCell>
                    <TableCell>$208.14</TableCell>
                    <TableCell>$199.98</TableCell>
                    <TableCell>$188.22</TableCell>
                    <TableCell>+$11.76</TableCell>
                    <TableCell><Token label="Bullish Above Slow" color="green" /></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </VStack>
          ) : (
            <VStack gap={4}>
              <Heading level={3}>
                Chronological Walk-Forward Model Folds
              </Heading>
              <Text type="supporting">
                Feature scaling and training occurs strictly inside each chronological training fold (zero future leakage).
              </Text>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Fold Index</TableHeaderCell>
                    <TableHeaderCell>Train Window</TableHeaderCell>
                    <TableHeaderCell>OOS Test Window</TableHeaderCell>
                    <TableHeaderCell>In-Sample R²</TableHeaderCell>
                    <TableHeaderCell>Out-of-Sample R²</TableHeaderCell>
                    <TableHeaderCell>Naive Benchmark IC</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell><Text weight="bold">Fold 1</Text></TableCell>
                    <TableCell>2020-01 → 2022-12</TableCell>
                    <TableCell>2023-01 → 2023-06</TableCell>
                    <TableCell>0.142</TableCell>
                    <TableCell><Token label="0.058" color="green" /></TableCell>
                    <TableCell>0.012</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><Text weight="bold">Fold 2</Text></TableCell>
                    <TableCell>2020-07 → 2023-06</TableCell>
                    <TableCell>2023-07 → 2023-12</TableCell>
                    <TableCell>0.138</TableCell>
                    <TableCell><Token label="0.061" color="green" /></TableCell>
                    <TableCell>0.009</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><Text weight="bold">Fold 3</Text></TableCell>
                    <TableCell>2021-01 → 2023-12</TableCell>
                    <TableCell>2024-01 → 2024-06</TableCell>
                    <TableCell>0.155</TableCell>
                    <TableCell><Token label="0.049" color="green" /></TableCell>
                    <TableCell>0.015</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </VStack>
          )}
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={360}
          hasDivider
          isScrollable
          label="Model Parameters"
        >
          <VStack gap={4} style={{ padding: "16px" }}>
            <Heading level={3}>
              Configuration & Parameters
            </Heading>

            {activeTab === "indicators" ? (
              <VStack gap={3}>
                <VStack gap={1}>
                  <TextInput
                    label="Fast Period (Days)"
                    value={fastPeriod}
                    onChange={(val) => setFastPeriod(typeof val === "string" ? val : "")}
                  />
                </VStack>
                <VStack gap={1}>
                  <TextInput
                    label="Slow Period (Days)"
                    value={slowPeriod}
                    onChange={(val) => setSlowPeriod(typeof val === "string" ? val : "")}
                  />
                </VStack>
              </VStack>
            ) : (
              <VStack gap={3}>
                <VStack gap={1}>
                  <Text weight="medium">Model Architecture</Text>
                  <SegmentedControl
                    label="Model Architecture"
                    value={modelType}
                    onChange={(val) => setModelType(val as "baseline" | "lightgbm")}
                  >
                    <SegmentedControlItem value="baseline" label="Linear Ridge Baseline" />
                    <SegmentedControlItem value="lightgbm" label="LightGBM Regressor" />
                  </SegmentedControl>
                </VStack>
                <VStack gap={1}>
                  <Text weight="medium">Prediction Target Horizon</Text>
                  <Text type="supporting">5-day forward total return</Text>
                </VStack>
              </VStack>
            )}
          </VStack>
        </LayoutPanel>
      }
    />
  );
}

