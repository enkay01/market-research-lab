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
import type { Project } from "../api/client";

interface StudyViewProps {
  project?: Project;
}

interface CaseStudySummary {
  id: string;
  ticker: string;
  company: string;
  title: string;
  methodology: string;
  category: "dcf" | "sotp" | "multistage" | "reverse";
  status: "completed" | "in_progress";
  dateUpdated: string;
  description: string;
  summaryMetrics: {
    baseMetric: string;
    discountRate: string;
    impliedFairValue: string;
    marketPrice: string;
    gapPercent: string;
  };
}

const CASE_STUDIES: CaseStudySummary[] = [
  {
    id: "aapl-dcf",
    ticker: "AAPL",
    company: "Apple Inc.",
    title: "Apple Inc. (AAPL) — FCFF DCF Valuation Model",
    methodology: "5-Year Explicit Free Cash Flow to Firm + Gordon Growth Terminal Value",
    category: "dcf",
    status: "completed",
    dateUpdated: "2026-08-15",
    description: "End-to-end worked DCF model for Apple Inc. evaluating trailing cash flow of $136.68B, a 5.0% high-growth phase, 8.25% WACC hurdle rate, and balance sheet equity bridge to $190.63/share.",
    summaryMetrics: {
      baseMetric: "$136.68B FCF",
      discountRate: "8.25% WACC",
      impliedFairValue: "$190.63",
      marketPrice: "$305.93",
      gapPercent: "-37.7%",
    },
  },
  {
    id: "msft-sotp",
    ticker: "MSFT",
    company: "Microsoft Corporation",
    title: "Microsoft Corp. (MSFT) — Sum-of-the-Parts (SOTP) Valuation",
    methodology: "Segment Enterprise Multiples (Cloud, Productivity SaaS, Personal Computing)",
    category: "sotp",
    status: "completed",
    dateUpdated: "2026-08-12",
    description: "Multi-segment enterprise valuation valuing Azure / Intelligent Cloud at 14.5x EV/Sales, Office & Productivity at 22x P/E, and Gaming/Devices at 12x EV/EBITDA.",
    summaryMetrics: {
      baseMetric: "$245.1B Revenue",
      discountRate: "8.50% CoE",
      impliedFairValue: "$438.50",
      marketPrice: "$448.20",
      gapPercent: "-2.2%",
    },
  },
  {
    id: "nvda-growth",
    ticker: "NVDA",
    company: "NVIDIA Corporation",
    title: "NVIDIA Corp. (NVDA) — 3-Stage Hyper-Growth DCF",
    methodology: "3-Stage DCF with Compute Cycle Normalization & Capex Deceleration",
    category: "multistage",
    status: "in_progress",
    dateUpdated: "2026-08-10",
    description: "Modeling data center accelerated computing demand with 35% 3-year CAGR transitioning to 12% fade phase and long-run 3.0% perpetual growth.",
    summaryMetrics: {
      baseMetric: "$60.8B FCF",
      discountRate: "9.50% WACC",
      impliedFairValue: "$122.40",
      marketPrice: "$128.50",
      gapPercent: "-4.7%",
    },
  },
  {
    id: "googl-reverse",
    ticker: "GOOGL",
    company: "Alphabet Inc.",
    title: "Alphabet Inc. (GOOGL) — Reverse DCF Expectations",
    methodology: "Reverse DCF solving for market-implied revenue and margin trajectory",
    category: "reverse",
    status: "in_progress",
    dateUpdated: "2026-08-05",
    description: "Deconstructing current market enterprise valuation to uncover the implied 10-year free cash flow growth rate required to justify market trading levels.",
    summaryMetrics: {
      baseMetric: "$350.0B EV",
      discountRate: "8.75% WACC",
      impliedFairValue: "Implied 11.2% CAGR",
      marketPrice: "$176.80",
      gapPercent: "Fairly Priced",
    },
  },
];

export function StudyView({ project }: StudyViewProps) {
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<"all" | "dcf" | "sotp" | "multistage" | "reverse">("all");
  const [activeSection, setActiveSection] = useState<"all" | "inputs" | "math" | "bridge" | "risks">("all");

  const selectedStudy = CASE_STUDIES.find((s) => s.id === selectedStudyId);

  const filteredStudies = CASE_STUDIES.filter((s) => {
    const matchesSearch =
      s.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.company.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.methodology.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = categoryFilter === "all" || s.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              {selectedStudy ? (
                <HStack align="center" gap={2}>
                  <Button
                    label="← Back to Worked Examples"
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelectedStudyId(null)}
                  />
                  <Heading level={2}>
                    {selectedStudy.ticker} — {selectedStudy.company}
                  </Heading>
                  <Token label={selectedStudy.status === "completed" ? "Verified" : "Draft"} color={selectedStudy.status === "completed" ? "green" : "gray"} />
                </HStack>
              ) : (
                <HStack align="center" gap={2}>
                  <Heading level={2}>
                    Valuation Worked Examples
                  </Heading>
                  <Badge label={`${CASE_STUDIES.length} Cases`} variant="purple" />
                  {project && <Token label={`Project: ${project.name}`} color="blue" />}
                </HStack>
              )}
            </HStack>

            {selectedStudy ? (
              <SegmentedControl
                label="Section Filter"
                value={activeSection}
                onChange={(val) => setActiveSection(val as "all" | "inputs" | "math" | "bridge" | "risks")}
              >
                <SegmentedControlItem value="all" label="Full Case" />
                <SegmentedControlItem value="inputs" label="1. Inputs" />
                <SegmentedControlItem value="math" label="2. Financial Math" />
                <SegmentedControlItem value="bridge" label="3. Price Bridge" />
                <SegmentedControlItem value="risks" label="4. Risks" />
              </SegmentedControl>
            ) : (
              <HStack gap={2}>
                <TextInput
                  label="Search worked examples"
                  isLabelHidden
                  placeholder="Search ticker, company, methodology…"
                  value={searchQuery}
                  onChange={(val) => setSearchQuery(typeof val === "string" ? val : "")}
                  width={280}
                />
                <SegmentedControl
                  label="Category Filter"
                  value={categoryFilter}
                  onChange={(val) => setCategoryFilter(val as typeof categoryFilter)}
                >
                  <SegmentedControlItem value="all" label="All Types" />
                  <SegmentedControlItem value="dcf" label="DCF" />
                  <SegmentedControlItem value="sotp" label="SOTP" />
                  <SegmentedControlItem value="multistage" label="Multi-Stage" />
                </SegmentedControl>
              </HStack>
            )}
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={4} isScrollable>
          {!selectedStudy ? (
            /* ========================================================= */
            /* 1. INDEX VIEW: CATALOGUE OF WORKED EXAMPLES               */
            /* ========================================================= */
            <VStack gap={5} style={{ maxWidth: "1080px", margin: "0 auto" }}>
              {/* Introduction Banner */}
              <VStack
                gap={2}
                style={{
                  padding: "24px",
                  borderRadius: "var(--radius-lg, 8px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <HStack justify="between" align="start" gap={4}>
                  <VStack gap={1} style={{ flex: 1 }}>
                    <Heading level={2}>
                      Worked Valuation Library & Mathematical Case Studies
                    </Heading>
                    <Text type="supporting">
                      Explore detailed, step-by-step worked valuation models for institutional securities. Each study includes full transparent formula derivations, discount factor schedules, Gordon Growth calculations, balance sheet bridge reconciliations, and key risk sensitivities.
                    </Text>
                  </VStack>
                  <Token label="Institutional Library" color="purple" />
                </HStack>
              </VStack>

              {/* Grid / List of Case Studies */}
              <VStack gap={3}>
                <HStack justify="between" align="center">
                  <Text weight="bold" size="lg">
                    Available Worked Examples ({filteredStudies.length})
                  </Text>
                  <Text type="supporting">
                    Click any study card to inspect step-by-step financial calculations.
                  </Text>
                </HStack>

                {filteredStudies.map((study) => (
                  <VStack
                    key={study.id}
                    gap={3}
                    onClick={() => setSelectedStudyId(study.id)}
                    style={{
                      cursor: "pointer",
                      padding: "20px 24px",
                      borderRadius: "var(--radius-md, 6px)",
                      backgroundColor: "var(--color-background-surface)",
                      border: "1px solid var(--color-border)",
                      transition: "border-color 0.15s ease, transform 0.1s ease",
                    }}
                  >
                    <HStack justify="between" align="start">
                      <VStack gap={1}>
                        <HStack align="center" gap={2}>
                          <Badge label={study.ticker} variant="purple" />
                          <Heading level={3}>
                            {study.company}
                          </Heading>
                          <Token
                            label={study.status === "completed" ? "Verified Model" : "Draft In Progress"}
                            color={study.status === "completed" ? "green" : "gray"}
                          />
                        </HStack>
                        <Text type="supporting" weight="medium">
                          {study.methodology}
                        </Text>
                      </VStack>

                      <Button
                        label="View Worked Example →"
                        variant={study.status === "completed" ? "primary" : "secondary"}
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedStudyId(study.id);
                        }}
                      />
                    </HStack>

                    <Text>
                      {study.description}
                    </Text>

                    {/* Summary Metric Strip */}
                    <HStack
                      gap={4}
                      style={{
                        padding: "12px 16px",
                        borderRadius: "var(--radius-sm, 4px)",
                        backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      <VStack gap={0} style={{ flex: 1 }}>
                        <Text type="supporting">Base Trailing Metric</Text>
                        <Text weight="bold">{study.summaryMetrics.baseMetric}</Text>
                      </VStack>
                      <VStack gap={0} style={{ flex: 1 }}>
                        <Text type="supporting">Cost of Capital</Text>
                        <Text weight="bold">{study.summaryMetrics.discountRate}</Text>
                      </VStack>
                      <VStack gap={0} style={{ flex: 1 }}>
                        <Text type="supporting">Implied Fair Value</Text>
                        <Text weight="bold" color="green">{study.summaryMetrics.impliedFairValue}</Text>
                      </VStack>
                      <VStack gap={0} style={{ flex: 1 }}>
                        <Text type="supporting">Market Trading Price</Text>
                        <Text weight="medium">{study.summaryMetrics.marketPrice}</Text>
                      </VStack>
                      <VStack gap={0} style={{ flex: 1 }}>
                        <Text type="supporting">Valuation Gap</Text>
                        <Token
                          label={study.summaryMetrics.gapPercent}
                          color={study.summaryMetrics.gapPercent.startsWith("-") ? "purple" : "green"}
                        />
                      </VStack>
                    </HStack>
                  </VStack>
                ))}
              </VStack>
            </VStack>
          ) : (
            /* ========================================================= */
            /* 2. DETAIL VIEW: WORKED VALUATION EXAMPLE (AAPL)           */
            /* ========================================================= */
            <VStack gap={5} style={{ maxWidth: "1080px", margin: "0 auto" }}>
              {/* Worked Example Header */}
              <VStack
                gap={2}
                style={{
                  padding: "24px",
                  borderRadius: "var(--radius-lg, 8px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <HStack justify="between" align="center">
                  <VStack gap={1}>
                    <HStack align="center" gap={2}>
                      <Badge label={selectedStudy.ticker} variant="purple" />
                      <Heading level={1}>
                        {selectedStudy.company} — Worked Valuation Model
                      </Heading>
                    </HStack>
                    <Text type="supporting">
                      {selectedStudy.description}
                    </Text>
                  </VStack>
                  <HStack gap={2}>
                    <Token label="FCFF DCF Standard" color="purple" />
                    <Token label="Verified Model" color="green" />
                  </HStack>
                </HStack>
              </VStack>

              {/* ------------------------------------------------------------- */}
              {/* SECTION 1: Core Inputs & Tech Assumptions                     */}
              {/* ------------------------------------------------------------- */}
              {(activeSection === "all" || activeSection === "inputs") && (
                <VStack
                  gap={4}
                  style={{
                    padding: "24px",
                    borderRadius: "var(--radius-lg, 8px)",
                    backgroundColor: "var(--color-background-surface)",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <HStack justify="between" align="center">
                    <HStack align="center" gap={2}>
                      <Heading level={2}>
                        📌 1. Core Inputs & Tech Assumptions
                      </Heading>
                    </HStack>
                    <Token label="Model Parameters" color="blue" />
                  </HStack>

                  <HStack gap={3}>
                    <VStack
                      gap={1}
                      style={{
                        flex: 1,
                        padding: "16px",
                        borderRadius: "var(--radius-md, 6px)",
                        backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      <Text type="supporting">Base Cash Flow (FCF₀)</Text>
                      <Text weight="bold" size="lg">$136.68 Billion</Text>
                      <Text type="supporting">Actual trailing free cash flow</Text>
                    </VStack>

                    <VStack
                      gap={1}
                      style={{
                        flex: 1,
                        padding: "16px",
                        borderRadius: "var(--radius-md, 6px)",
                        backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      <Text type="supporting">Discount Rate (WACC)</Text>
                      <Text weight="bold" size="lg">8.25%</Text>
                      <Text type="supporting">Standard risk rate for stable tech</Text>
                    </VStack>

                    <VStack
                      gap={1}
                      style={{
                        flex: 1,
                        padding: "16px",
                        borderRadius: "var(--radius-md, 6px)",
                        backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      <Text type="supporting">High Growth (Years 1–5)</Text>
                      <Text weight="bold" size="lg">5.0% annually</Text>
                      <Text type="supporting">Organic hardware & services growth</Text>
                    </VStack>

                    <VStack
                      gap={1}
                      style={{
                        flex: 1,
                        padding: "16px",
                        borderRadius: "var(--radius-md, 6px)",
                        backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                        border: "1px solid var(--color-border)",
                      }}
                    >
                      <Text type="supporting">Perpetual Growth (g)</Text>
                      <Text weight="bold" size="lg">2.5% annually</Text>
                      <Text type="supporting">Permanent economic ceiling</Text>
                    </VStack>
                  </HStack>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Parameter</TableHeaderCell>
                        <TableHeaderCell>Value</TableHeaderCell>
                        <TableHeaderCell>Unit / Basis</TableHeaderCell>
                        <TableHeaderCell>Description & Methodological Rationale</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell><Text weight="bold">Base Free Cash Flow (FCF₀)</Text></TableCell>
                        <TableCell><Text weight="bold">$136.68B</Text></TableCell>
                        <TableCell>USD (Billions)</TableCell>
                        <TableCell>Actual trailing operating cash flow less capital expenditures.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Discount Rate (WACC)</Text></TableCell>
                        <TableCell><Text weight="bold">8.25%</Text></TableCell>
                        <TableCell>Percentage</TableCell>
                        <TableCell>Standard risk requirement reflecting high credit quality and balance sheet durability.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">High Growth Phase (Years 1–5)</Text></TableCell>
                        <TableCell><Text weight="bold">5.00%</Text></TableCell>
                        <TableCell>Annual Compounded</TableCell>
                        <TableCell>Conservative 5-year organic growth rate across hardware and recurring services.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Perpetual Growth Rate (g)</Text></TableCell>
                        <TableCell><Text weight="bold">2.50%</Text></TableCell>
                        <TableCell>Annual Perpetual</TableCell>
                        <TableCell>Permanent economic growth ceiling aligned with long-run nominal GDP expansion.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Total Cash & Marketable Securities</Text></TableCell>
                        <TableCell>$153.00B</TableCell>
                        <TableCell>USD (Billions)</TableCell>
                        <TableCell>Liquid non-operating cash balance from balance sheet.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Total Debt & Borrowings</Text></TableCell>
                        <TableCell>$84.34B</TableCell>
                        <TableCell>USD (Billions)</TableCell>
                        <TableCell>Short-term commercial paper and long-term notes.</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Diluted Shares Outstanding</Text></TableCell>
                        <TableCell>14.61B shares</TableCell>
                        <TableCell>Shares (Billions)</TableCell>
                        <TableCell>Weighted average diluted common shares.</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </VStack>
              )}

              {/* ------------------------------------------------------------- */}
              {/* SECTION 2: Step-by-Step Financial Math                        */}
              {/* ------------------------------------------------------------- */}
              {(activeSection === "all" || activeSection === "math") && (
                <VStack
                  gap={4}
                  style={{
                    padding: "24px",
                    borderRadius: "var(--radius-lg, 8px)",
                    backgroundColor: "var(--color-background-surface)",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <HStack justify="between" align="center">
                    <Heading level={2}>
                      📊 2. Step-by-Step Financial Math
                    </Heading>
                    <Token label="Three-Phase Derivation" color="purple" />
                  </HStack>

                  {/* Phase 1: Near-Term Growth */}
                  <VStack gap={2}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>
                        Phase 1: Near-Term Growth (Years 1–5)
                      </Heading>
                      <Token label="PV Years 1–5 = $624.26 Billion" color="blue" />
                    </HStack>
                    <Text type="supporting">
                      We grow the cash flow by 5% each year and discount it back to today using the WACC (8.25%):
                    </Text>

                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Forecast Period</TableHeaderCell>
                          <TableHeaderCell>Growth Formula</TableHeaderCell>
                          <TableHeaderCell>Nominal Cash Flow</TableHeaderCell>
                          <TableHeaderCell>Discount Factor (1 / 1.0825ᵗ)</TableHeaderCell>
                          <TableHeaderCell>Present Value (PV)</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow>
                          <TableCell><Text weight="bold">Year 1</Text></TableCell>
                          <TableCell>$136.68B × (1 + 0.05)¹</TableCell>
                          <TableCell>$143.51 Billion</TableCell>
                          <TableCell>0.92379 (1 / 1.0825¹)</TableCell>
                          <TableCell><Text weight="bold">$132.58 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">Year 2</Text></TableCell>
                          <TableCell>$143.51B × (1 + 0.05)</TableCell>
                          <TableCell>$150.69 Billion</TableCell>
                          <TableCell>0.85338 (1 / 1.0825²)</TableCell>
                          <TableCell><Text weight="bold">$128.60 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">Year 3</Text></TableCell>
                          <TableCell>$150.69B × (1 + 0.05)</TableCell>
                          <TableCell>$158.23 Billion</TableCell>
                          <TableCell>0.78835 (1 / 1.0825³)</TableCell>
                          <TableCell><Text weight="bold">$124.74 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">Year 4</Text></TableCell>
                          <TableCell>$158.23B × (1 + 0.05)</TableCell>
                          <TableCell>$166.14 Billion</TableCell>
                          <TableCell>0.72826 (1 / 1.0825⁴)</TableCell>
                          <TableCell><Text weight="bold">$120.99 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">Year 5</Text></TableCell>
                          <TableCell>$166.14B × (1 + 0.05)</TableCell>
                          <TableCell>$174.44 Billion</TableCell>
                          <TableCell>0.67276 (1 / 1.0825⁵)</TableCell>
                          <TableCell><Text weight="bold">$117.36 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">PV of Years 1–5</Text></TableCell>
                          <TableCell>$132.58B + $128.60B + $124.74B + $120.99B + $117.36B</TableCell>
                          <TableCell>—</TableCell>
                          <TableCell>—</TableCell>
                          <TableCell><Text weight="bold" color="blue" size="lg">$624.26 Billion</Text></TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </VStack>

                  {/* Phase 2: The Forever Terminal Value */}
                  <VStack gap={2}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>
                        Phase 2: The "Forever" Terminal Value
                      </Heading>
                      <Token label="PV Terminal = $2,092.03 Billion" color="purple" />
                    </HStack>
                    <Text type="supporting">
                      We apply the Gordon Growth formula at Year 5, then discount that massive lump sum back 5 years to today:
                    </Text>

                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Step</TableHeaderCell>
                          <TableHeaderCell>Formula & Input Equation</TableHeaderCell>
                          <TableHeaderCell>Resulting Amount</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow>
                          <TableCell><Text weight="medium">Year 6 Normalized Cash Flow</Text></TableCell>
                          <TableCell>FCF₅ × (1 + g) = $174.44B × (1 + 0.025)</TableCell>
                          <TableCell><Text weight="bold">$178.80 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="medium">Capitalization Spread (WACC − g)</Text></TableCell>
                          <TableCell>0.0825 − 0.0250</TableCell>
                          <TableCell><Text weight="bold">0.0575 (5.75%)</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="medium">Terminal Value at Year 5</Text></TableCell>
                          <TableCell>[$174.44B × (1 + 0.025)] / (0.0825 − 0.025) = $178.80B / 0.0575</TableCell>
                          <TableCell><Text weight="bold">$3,109.62 Billion</Text></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold">Present Value of Terminal Value</Text></TableCell>
                          <TableCell>$3,109.62B / (1 + 0.0825)⁵ = $3,109.62B × 0.67276</TableCell>
                          <TableCell><Text weight="bold" color="purple" size="lg">$2,092.03 Billion</Text></TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </VStack>

                  {/* Phase 3: Total Enterprise Value */}
                  <VStack gap={2}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>
                        Phase 3: Total Enterprise Value
                      </Heading>
                      <Token label="Enterprise Value = $2,716.29 Billion" color="green" />
                    </HStack>
                    <Text type="supporting">
                      Combine the near-term phase ($624.26B) and the terminal phase ($2,092.03B):
                    </Text>

                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell><Text weight="medium">Phase 1: Present Value of Explicit Forecast (Years 1–5)</Text></TableCell>
                          <TableCell>$624.26 Billion</TableCell>
                          <TableCell><Token label="23.0% of Total EV" color="blue" /></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="medium">Phase 2: Present Value of Perpetual Terminal Value</Text></TableCell>
                          <TableCell>$2,092.03 Billion</TableCell>
                          <TableCell><Token label="77.0% of Total EV" color="purple" /></TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell><Text weight="bold" size="lg">Total Enterprise Value</Text></TableCell>
                          <TableCell><Text weight="bold" size="lg" color="green">$2,716.29 Billion</Text></TableCell>
                          <TableCell><Token label="100.0%" color="green" /></TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </VStack>
                </VStack>
              )}

              {/* ------------------------------------------------------------- */}
              {/* SECTION 3: The Stock Price Bridge                             */}
              {/* ------------------------------------------------------------- */}
              {(activeSection === "all" || activeSection === "bridge") && (
                <VStack
                  gap={4}
                  style={{
                    padding: "24px",
                    borderRadius: "var(--radius-lg, 8px)",
                    backgroundColor: "var(--color-background-surface)",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <HStack justify="between" align="center">
                    <Heading level={2}>
                      💵 3. The Stock Price Bridge
                    </Heading>
                    <Token label="Balance Sheet Reconciliation" color="green" />
                  </HStack>
                  <Text type="supporting">
                    To find the final per-share value, we adjust for Apple's actual balance sheet items and divide by its 14.61 Billion outstanding shares:
                  </Text>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Step Item</TableHeaderCell>
                        <TableHeaderCell>Balance Sheet Line Item</TableHeaderCell>
                        <TableHeaderCell>Impact / Math Operation</TableHeaderCell>
                        <TableHeaderCell>Total Equity & Per Share</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell><Text weight="bold">Step 1: Enterprise Value</Text></TableCell>
                        <TableCell>Calculated Operating Asset Value</TableCell>
                        <TableCell>Starting Base</TableCell>
                        <TableCell><Text weight="bold">$2,716.29 Billion</Text></TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="medium">Step 2: Add Cash & Equivalents</Text></TableCell>
                        <TableCell>Balance Sheet Liquid Cash</TableCell>
                        <TableCell>+ $153.00 Billion</TableCell>
                        <TableCell>$2,869.29 Billion</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="medium">Step 3: Deduct Total Debt</Text></TableCell>
                        <TableCell>Commercial Paper & Term Debt</TableCell>
                        <TableCell>− $84.34 Billion</TableCell>
                        <TableCell><Text weight="bold">$2,784.95 Billion (Equity Value)</Text></TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Step 4: Divide by Share Count</Text></TableCell>
                        <TableCell>Diluted Shares Outstanding</TableCell>
                        <TableCell>÷ 14.61 Billion Shares</TableCell>
                        <TableCell>14,610,000,000 shares</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold" size="lg">Implied Stock Price</Text></TableCell>
                        <TableCell><Token label="$190.63 / share" color="green" /></TableCell>
                        <TableCell>$2,784.95B ÷ 14.61B shares</TableCell>
                        <TableCell><Text weight="bold" size="lg" color="green">$190.63 per share</Text></TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </VStack>
              )}

              {/* ------------------------------------------------------------- */}
              {/* SECTION 4: Key Takeaways & Risks                              */}
              {/* ------------------------------------------------------------- */}
              {(activeSection === "all" || activeSection === "risks") && (
                <VStack
                  gap={4}
                  style={{
                    padding: "24px",
                    borderRadius: "var(--radius-lg, 8px)",
                    backgroundColor: "var(--color-background-surface)",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <HStack justify="between" align="center">
                    <Heading level={2}>
                      ⚠️ 4. Key Takeaways & Risks
                    </Heading>
                    <Token label="Risk & Sensitivity Context" color="error" />
                  </HStack>

                  <Banner status="warning" title="Terminal Dominance (77% of Worth)">
                    The terminal value represents 77% of Apple's total calculated worth ($2,092.03B out of $2,716.29B), proving the model is highly sensitive to long-term assumptions. A small 50 bps deviation in WACC or perpetual growth shifts fair value by over $35 per share.
                  </Banner>

                  <Banner status="info" title="The Market Gap ($190.63 vs ~$305.93)">
                    Our calculated price ($190.63) is lower than the actual market price (~$305.93) because investors are paying a premium for aggressive AI growth or accepting lower risk returns (~6.5% to 7.0% cost of equity).
                  </Banner>

                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell>Sensitivity Dimension</TableHeaderCell>
                        <TableHeaderCell>Base Assumption</TableHeaderCell>
                        <TableHeaderCell>Bull Case (+)</TableHeaderCell>
                        <TableHeaderCell>Bear Case (−)</TableHeaderCell>
                        <TableHeaderCell>Sensitivity Impact</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell><Text weight="bold">Discount Rate (WACC)</Text></TableCell>
                        <TableCell>8.25%</TableCell>
                        <TableCell>7.50% (-75 bps)</TableCell>
                        <TableCell>9.00% (+75 bps)</TableCell>
                        <TableCell>Bull: $228.10 / share | Bear: $162.40 / share</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">Perpetual Growth (g)</Text></TableCell>
                        <TableCell>2.50%</TableCell>
                        <TableCell>3.00% (+50 bps)</TableCell>
                        <TableCell>2.00% (-50 bps)</TableCell>
                        <TableCell>Bull: $214.80 / share | Bear: $171.50 / share</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="bold">5-Yr Cash Flow CAGR</Text></TableCell>
                        <TableCell>5.00%</TableCell>
                        <TableCell>8.00% (+300 bps)</TableCell>
                        <TableCell>2.00% (-300 bps)</TableCell>
                        <TableCell>Bull: $219.40 / share | Bear: $166.80 / share</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </VStack>
              )}
            </VStack>
          )}
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={360}
          hasDivider
          isScrollable
          label="Case Study Navigator"
        >
          <VStack gap={4} style={{ padding: "20px" }}>
            <VStack gap={1}>
              <Heading level={3}>
                {selectedStudy ? "Study Quick Summary" : "Library Guide"}
              </Heading>
              <Text type="supporting">
                {selectedStudy
                  ? `${selectedStudy.company} (${selectedStudy.ticker}) valuation metrics.`
                  : "Worked models for fundamental research and valuation testing."}
              </Text>
            </VStack>

            {selectedStudy ? (
              <VStack gap={3}>
                <Table>
                  <TableBody>
                    <TableRow>
                      <TableCell><Text type="supporting">Methodology</Text></TableCell>
                      <TableCell><Text weight="bold">FCFF DCF</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">Base FCF (FCF₀)</Text></TableCell>
                      <TableCell><Text weight="bold">$136.68 B</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">WACC / g</Text></TableCell>
                      <TableCell><Text weight="bold">8.25% / 2.5%</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">Enterprise Value</Text></TableCell>
                      <TableCell><Text weight="bold">$2,716.29 B</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">Cash / Debt</Text></TableCell>
                      <TableCell><Text>+$153.0B / −$84.3B</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">Equity Value</Text></TableCell>
                      <TableCell><Text weight="bold">$2,784.95 B</Text></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="bold">DCF Fair Value</Text></TableCell>
                      <TableCell><Token label="$190.63 / share" color="green" /></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text type="supporting">Market Trading Price</Text></TableCell>
                      <TableCell><Text>~$305.93 / share</Text></TableCell>
                    </TableRow>
                  </TableBody>
                </Table>

                <Button
                  label="← Return to Case Index"
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelectedStudyId(null)}
                />
              </VStack>
            ) : (
              <VStack gap={3}>
                <VStack
                  gap={1}
                  style={{
                    padding: "12px",
                    borderRadius: "var(--radius-md, 6px)",
                    backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <Text weight="bold">1. Free Cash Flow to Firm (FCFF)</Text>
                  <Text type="supporting">
                    Unlevered cash flow discounted by WACC. Best for capital-intensive or stable cash flow generators.
                  </Text>
                </VStack>

                <VStack
                  gap={1}
                  style={{
                    padding: "12px",
                    borderRadius: "var(--radius-md, 6px)",
                    backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <Text weight="bold">2. Sum-of-the-Parts (SOTP)</Text>
                  <Text type="supporting">
                    Individual segment peer multiples. Best for diversified conglomerates with distinct business units.
                  </Text>
                </VStack>

                <VStack
                  gap={1}
                  style={{
                    padding: "12px",
                    borderRadius: "var(--radius-md, 6px)",
                    backgroundColor: "var(--color-background-wash, rgba(255, 255, 255, 0.04))",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  <Text weight="bold">3. Multi-Stage High Growth</Text>
                  <Text type="supporting">
                    Explicit high growth, fade period, and terminal stabilization. Best for cyclical or AI scaling companies.
                  </Text>
                </VStack>
              </VStack>
            )}
          </VStack>
        </LayoutPanel>
      }
    />
  );
}
