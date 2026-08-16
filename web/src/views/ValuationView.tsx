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
  SegmentedControl,
  SegmentedControlItem,
  TextInput,
} from "@astryxdesign/core";
import { api, type Project } from "../api/client";

interface ValuationViewProps {
  project?: Project;
}

export function ValuationView({ project }: ValuationViewProps) {
  const [method, setMethod] = useState<"fcff_dcf" | "comparables">("fcff_dcf");
  const [scenario, setScenario] = useState<"base" | "bull" | "bear">("base");
  const [wacc, setWacc] = useState("8.5");
  const [terminalGrowth, setTerminalGrowth] = useState("2.5");
  const [revenueGrowth, setRevenueGrowth] = useState("7.0");
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  async function handleSaveRevision() {
    if (!project) return;
    setIsSaving(true);
    try {
      const result = await api.saveDefinition(project.id, {
        kind: "valuation",
        name: `${method === "fcff_dcf" ? "FCFF DCF" : "Trading Comps"} - AAPL`,
        definition: {
          method,
          scenario,
          wacc: parseFloat(wacc),
          terminal_growth: parseFloat(terminalGrowth),
          revenue_growth: parseFloat(revenueGrowth),
          currency: "USD",
        },
      });
      setStatusMessage(`Saved revision ${result.revision} successfully.`);
    } catch (err: unknown) {
      setStatusMessage(err instanceof Error ? err.message : "Failed to save valuation revision.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>
                Valuation Workspace
              </Heading>
              <Token label="Target: AAPL" color="blue" />
              {project && <Badge label={`Project: ${project.name}`} variant="purple" />}
            </HStack>

            <HStack gap={2}>
              <SegmentedControl
                label="Valuation Method"
                value={method}
                onChange={(val) => setMethod(val as "fcff_dcf" | "comparables")}
              >
                <SegmentedControlItem value="fcff_dcf" label="FCFF DCF Model" />
                <SegmentedControlItem value="comparables" label="Trading Comparables" />
              </SegmentedControl>
              <Button label="Save Revision" variant="primary" size="sm" onClick={handleSaveRevision} isLoading={isSaving} />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            {statusMessage && (
              <Banner status="success" title="Valuation Status">
                {statusMessage}
              </Banner>
            )}

            {method === "fcff_dcf" ? (
              <VStack gap={4}>
                <HStack justify="between" align="center">
                  <VStack gap={0}>
                    <Heading level={3}>
                      Discounted Free Cash Flow to Firm (FCFF)
                    </Heading>
                    <Text type="supporting">
                      Explicit 5-year forecast horizon with Gordon Growth terminal value.
                    </Text>
                  </VStack>
                  <SegmentedControl
                    label="Scenario Selection"
                    value={scenario}
                    onChange={(val) => setScenario(val as "base" | "bull" | "bear")}
                  >
                    <SegmentedControlItem value="bear" label="Bear Case" />
                    <SegmentedControlItem value="base" label="Base Case" />
                    <SegmentedControlItem value="bull" label="Bull Case" />
                  </SegmentedControl>
                </HStack>

                {/* DCF Forecast Cash Flows Table */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>Line Item ($M)</TableHeaderCell>
                      <TableHeaderCell>Year 1</TableHeaderCell>
                      <TableHeaderCell>Year 2</TableHeaderCell>
                      <TableHeaderCell>Year 3</TableHeaderCell>
                      <TableHeaderCell>Year 4</TableHeaderCell>
                      <TableHeaderCell>Year 5</TableHeaderCell>
                      <TableHeaderCell>Terminal</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell><Text weight="medium">Projected Revenue</Text></TableCell>
                      <TableCell>$412,000</TableCell>
                      <TableCell>$440,840</TableCell>
                      <TableCell>$471,698</TableCell>
                      <TableCell>$504,717</TableCell>
                      <TableCell>$540,047</TableCell>
                      <TableCell>—</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="medium">Operating Income (EBIT)</Text></TableCell>
                      <TableCell>$125,660</TableCell>
                      <TableCell>$134,456</TableCell>
                      <TableCell>$143,868</TableCell>
                      <TableCell>$153,939</TableCell>
                      <TableCell>$164,714</TableCell>
                      <TableCell>—</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="medium">Unlevered Free Cash Flow</Text></TableCell>
                      <TableCell>$102,400</TableCell>
                      <TableCell>$109,568</TableCell>
                      <TableCell>$117,237</TableCell>
                      <TableCell>$125,444</TableCell>
                      <TableCell>$134,225</TableCell>
                      <TableCell>$2,281,825</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="medium">Discount Factor (WACC {wacc}%)</Text></TableCell>
                      <TableCell>0.922</TableCell>
                      <TableCell>0.849</TableCell>
                      <TableCell>0.783</TableCell>
                      <TableCell>0.722</TableCell>
                      <TableCell>0.665</TableCell>
                      <TableCell>0.665</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="bold">Present Value of FCFF</Text></TableCell>
                      <TableCell><Text weight="bold">$94,413</Text></TableCell>
                      <TableCell><Text weight="bold">$93,023</Text></TableCell>
                      <TableCell><Text weight="bold">$91,797</Text></TableCell>
                      <TableCell><Text weight="bold">$90,571</Text></TableCell>
                      <TableCell><Text weight="bold">$89,260</Text></TableCell>
                      <TableCell><Text weight="bold">$1,517,414</Text></TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </VStack>
            ) : (
              <VStack gap={4}>
                <Heading level={3}>
                  Trading Multiples & Peer Comparables
                </Heading>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>Peer Company</TableHeaderCell>
                      <TableHeaderCell>Ticker</TableHeaderCell>
                      <TableHeaderCell>EV / Revenue</TableHeaderCell>
                      <TableHeaderCell>EV / EBITDA</TableHeaderCell>
                      <TableHeaderCell>P / E (LTM)</TableHeaderCell>
                      <TableHeaderCell>FCF Yield</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell><Text weight="bold">Target: Apple Inc.</Text></TableCell>
                      <TableCell>AAPL</TableCell>
                      <TableCell>7.8x</TableCell>
                      <TableCell>23.4x</TableCell>
                      <TableCell>31.2x</TableCell>
                      <TableCell>3.7%</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Microsoft Corp.</TableCell>
                      <TableCell>MSFT</TableCell>
                      <TableCell>11.2x</TableCell>
                      <TableCell>21.8x</TableCell>
                      <TableCell>34.5x</TableCell>
                      <TableCell>3.1%</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Alphabet Inc.</TableCell>
                      <TableCell>GOOGL</TableCell>
                      <TableCell>5.9x</TableCell>
                      <TableCell>16.2x</TableCell>
                      <TableCell>23.8x</TableCell>
                      <TableCell>4.6%</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="bold">Peer Median</Text></TableCell>
                      <TableCell>—</TableCell>
                      <TableCell><Text weight="bold">8.5x</Text></TableCell>
                      <TableCell><Text weight="bold">19.0x</Text></TableCell>
                      <TableCell><Text weight="bold">29.1x</Text></TableCell>
                      <TableCell><Text weight="bold">3.8%</Text></TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </VStack>
            )}
          </VStack>
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={380}
          hasDivider
          isScrollable
          label="Valuation Parameters"
        >
          <VStack gap={4} style={{ padding: "16px" }}>
            <Heading level={3}>
              Model Assumptions
            </Heading>

            <VStack gap={1}>
              <TextInput
                label="WACC (%)"
                value={wacc}
                onChange={(val) => setWacc(typeof val === "string" ? val : "")}
              />
            </VStack>

            <VStack gap={1}>
              <TextInput
                label="Terminal Growth Rate (%)"
                value={terminalGrowth}
                onChange={(val) => setTerminalGrowth(typeof val === "string" ? val : "")}
              />
            </VStack>

            <VStack gap={1}>
              <TextInput
                label="Revenue Growth (% CAGR)"
                value={revenueGrowth}
                onChange={(val) => setRevenueGrowth(typeof val === "string" ? val : "")}
              />
            </VStack>

            <VStack gap={2}>
              <Text weight="semibold">
                Valuation Output Summary
              </Text>
              <Table>
                <TableBody>
                  <TableRow>
                    <TableCell><Text type="supporting">Enterprise Value</Text></TableCell>
                    <TableCell><Text weight="bold">$1,976,479 M</Text></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><Text type="supporting">Net Cash / (Debt)</Text></TableCell>
                    <TableCell><Text>($45,200 M)</Text></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><Text type="supporting">Implied Equity Value</Text></TableCell>
                    <TableCell><Text weight="bold">$1,931,279 M</Text></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><Text weight="bold">Fair Value Per Share</Text></TableCell>
                    <TableCell><Token label="$218.45 / share" color="green" /></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </VStack>
          </VStack>
        </LayoutPanel>
      }
    />
  );
}

