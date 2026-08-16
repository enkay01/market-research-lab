import { useEffect, useMemo, useState } from "react";
import {
  Banner,
  Button,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  SegmentedControl,
  SegmentedControlItem,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  TextInput,
  Token,
  VStack,
} from "@astryxdesign/core";
import { CheckboxList, CheckboxListItem } from "@astryxdesign/core/CheckboxList";
import { Selector } from "@astryxdesign/core/Selector";
import {
  api,
  type ComparableValuation,
  type FCFFDCFRequest,
  type FCFFDCFValuation,
  type Project,
  type SavedValuation,
  type Security,
  type ValuationComparison,
} from "../api/client";

interface ValuationViewProps {
  project?: Project;
}

function multiple(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(2)}x`;
}

function percentage(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;
}

function currencyFormat(value: number | null | undefined, currency: string = "USD"): string {
  if (value === null || value === undefined) return "—";
  return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function ValuationView({ project }: ValuationViewProps) {
  const [activeTab, setActiveTab] = useState<"fcff_dcf" | "comparables" | "comparison">("fcff_dcf");
  const [securities, setSecurities] = useState<Security[]>([]);
  const [targetId, setTargetId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [bannerType, setBannerType] = useState<"info" | "warning">("info");

  // DCF state
  const [baseRevenue, setBaseRevenue] = useState("100.0");
  const [revenueGrowth, setRevenueGrowth] = useState("7.0");
  const [operatingMargin, setOperatingMargin] = useState("20.0");
  const [taxRate, setTaxRate] = useState("21.0");
  const [reinvestmentRate, setReinvestmentRate] = useState("20.0");
  const [wacc, setWacc] = useState("8.5");
  const [terminalGrowth, setTerminalGrowth] = useState("2.5");
  const [sharesOutstanding, setSharesOutstanding] = useState("10.0");
  const [totalDebt, setTotalDebt] = useState("0.0");
  const [cash, setCash] = useState("0.0");
  const [forecastYears, setForecastYears] = useState("5");
  const [dcfResult, setDcfResult] = useState<FCFFDCFValuation | null>(null);

  // Comparables state
  const [peerIds, setPeerIds] = useState<string[]>([]);
  const [comparableResult, setComparableResult] = useState<ComparableValuation | null>(null);

  // Comparison & saved valuations state
  const [savedValuations, setSavedValuations] = useState<SavedValuation[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [comparisonResult, setComparisonResult] = useState<ValuationComparison | null>(null);

  // Loading states
  const [isCalculating, setIsCalculating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isComparing, setIsComparing] = useState(false);

  useEffect(() => {
    api.listSecurities({ limit: 500 })
      .then((available) => {
        setSecurities(available);
        if (available.length > 0) {
          setTargetId((current) => current || available[0].security_id);
        }
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Could not load local Securities.");
        setBannerType("warning");
      });
  }, []);

  // Reload saved valuations when project changes
  const loadSavedValuations = () => {
    if (!project) return;
    api.listValuations(project.id)
      .then((valuations) => {
        setSavedValuations(valuations);
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Could not reload saved Valuations.");
        setBannerType("warning");
      });
  };

  useEffect(() => {
    loadSavedValuations();
  }, [project?.id]);

  // When target security changes in DCF mode, automatically fetch seeded inputs
  const handleSecuritySelect = async (secId: string) => {
    setTargetId(secId);
    setPeerIds((current) => current.filter((p) => p !== secId));
    setComparableResult(null);

    if (project && secId) {
      try {
        const seed = await api.seedDcfValuation(project.id, secId);
        if (seed.base_revenue !== null && seed.base_revenue !== undefined) {
          setBaseRevenue(seed.base_revenue.toString());
        }
        if (seed.shares_outstanding !== null && seed.shares_outstanding !== undefined) {
          setSharesOutstanding(seed.shares_outstanding.toString());
        }
        setTotalDebt((seed.total_debt ?? 0).toString());
        setCash((seed.cash ?? 0).toString());
        setOperatingMargin((seed.operating_margin * 100).toFixed(1));
        setTaxRate((seed.tax_rate * 100).toFixed(1));
        setReinvestmentRate((seed.reinvestment_rate * 100).toFixed(1));
        setWacc((seed.wacc * 100).toFixed(2));
        setTerminalGrowth((seed.terminal_growth_rate * 100).toFixed(2));
        setRevenueGrowth((seed.revenue_growth_rate * 100).toFixed(1));
        if (seed.warnings.length > 0) {
          setMessage(`Seeded inputs from catalog with notices: ${seed.warnings.join(" ")}`);
          setBannerType("info");
        }
      } catch {
        // Fallback gracefully
      }
    }
  };

  const peers = useMemo(
    () => securities.filter((security) => security.security_id !== targetId),
    [securities, targetId],
  );

  const buildDcfRequest = (): FCFFDCFRequest => ({
    target_security_id: targetId,
    base_revenue: parseFloat(baseRevenue) || 100.0,
    revenue_growth_rate: (parseFloat(revenueGrowth) || 7.0) / 100.0,
    operating_margin: (parseFloat(operatingMargin) || 20.0) / 100.0,
    tax_rate: (parseFloat(taxRate) || 21.0) / 100.0,
    reinvestment_rate: (parseFloat(reinvestmentRate) || 20.0) / 100.0,
    wacc: (parseFloat(wacc) || 8.5) / 100.0,
    terminal_growth_rate: (parseFloat(terminalGrowth) || 2.5) / 100.0,
    shares_outstanding: parseFloat(sharesOutstanding) || 10.0,
    total_debt: parseFloat(totalDebt) || 0.0,
    cash: parseFloat(cash) || 0.0,
    forecast_years: parseInt(forecastYears, 10) || 5,
  });

  async function calculate() {
    setMessage(null);
    setIsCalculating(true);
    try {
      if (activeTab === "fcff_dcf") {
        if (!targetId) {
          setMessage("Select a target Security first.");
          setBannerType("warning");
          return;
        }
        const val = await api.calculateDcfValuation(buildDcfRequest());
        setDcfResult(val);
      } else if (activeTab === "comparables") {
        if (!targetId || peerIds.length === 0) {
          setMessage("Select one target Security and at least one peer Security.");
          setBannerType("warning");
          return;
        }
        const val = await api.calculateComparableValuation({
          target_security_id: targetId,
          peer_security_ids: peerIds,
        });
        setComparableResult(val);
      }
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Calculation failed.");
      setBannerType("warning");
    } finally {
      setIsCalculating(false);
    }
  }

  async function saveRevision() {
    if (!project) return;
    if (!targetId) {
      setMessage("Select a target Security before saving.");
      setBannerType("warning");
      return;
    }
    setIsSaving(true);
    setMessage(null);
    try {
      if (activeTab === "fcff_dcf") {
        const saved = await api.saveDcfValuation(project.id, buildDcfRequest());
        setDcfResult(saved);
        setMessage(`Saved ${saved.method_revision ?? "FCFF DCF"} in Run ${saved.run_id ?? ""}.`);
        setBannerType("info");
        loadSavedValuations();
      } else if (activeTab === "comparables") {
        const saved = await api.saveComparableValuation(project.id, {
          target_security_id: targetId,
          peer_security_ids: peerIds,
        });
        setComparableResult(saved);
        setMessage(`Saved ${saved.method_revision ?? "comparable"} in Run ${saved.run_id ?? ""}.`);
        setBannerType("info");
        loadSavedValuations();
      }
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Could not save the Valuation revision.");
      setBannerType("warning");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCompare() {
    if (!project) return;
    if (selectedRunIds.length < 2) {
      setMessage("Select at least 2 saved Valuations to compare.");
      setBannerType("warning");
      return;
    }
    setIsComparing(true);
    setMessage(null);
    try {
      const res = await api.compareValuations(project.id, { run_ids: selectedRunIds });
      setComparisonResult(res);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Comparison failed.");
      setBannerType("warning");
    } finally {
      setIsComparing(false);
    }
  }

  const currentRunId =
    activeTab === "fcff_dcf"
      ? dcfResult?.run_id
      : activeTab === "comparables"
      ? comparableResult?.run_id
      : null;

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center">
            <VStack gap={0}>
              <Heading level={2}>
                {activeTab === "fcff_dcf"
                  ? "FCFF DCF Valuation"
                  : activeTab === "comparables"
                  ? "Trading Comparables"
                  : "Valuation Comparison"}
              </Heading>
              <Text type="supporting">
                {activeTab === "fcff_dcf"
                  ? "Multi-year Free Cash Flow to Firm projections, WACC sensitivity, and Definition Revisions."
                  : activeTab === "comparables"
                  ? "Evaluate enterprise value and price multiples against peer securities."
                  : "Compare revisions, assumptions, and terminal values side-by-side."}
              </Text>
            </VStack>
            <HStack gap={2} align="center">
              <SegmentedControl
                label="Valuation view"
                value={activeTab}
                onChange={(value) => setActiveTab(value as "fcff_dcf" | "comparables" | "comparison")}
              >
                <SegmentedControlItem value="fcff_dcf" label="FCFF DCF" />
                <SegmentedControlItem value="comparables" label="Comparables" />
                <SegmentedControlItem value="comparison" label="Compare Revisions" />
              </SegmentedControl>
              {activeTab !== "comparison" && (
                <>
                  <Button
                    label="Calculate"
                    variant="primary"
                    onClick={calculate}
                    isLoading={isCalculating}
                  />
                  <Button
                    label="Save Revision"
                    variant="secondary"
                    onClick={saveRevision}
                    isLoading={isSaving}
                    isDisabled={!project}
                  />
                </>
              )}
              {currentRunId && project && (
                <HStack gap={1}>
                  <Button
                    label="Export HTML"
                    variant="tertiary"
                    onClick={() => {
                      window.open(api.getValuationExportUrl(project.id, currentRunId, "html"), "_blank");
                    }}
                  />
                  <Button
                    label="Export CSV"
                    variant="tertiary"
                    onClick={() => {
                      window.open(api.getValuationExportUrl(project.id, currentRunId, "csv"), "_blank");
                    }}
                  />
                  <Button
                    label="Export JSON"
                    variant="tertiary"
                    onClick={() => {
                      window.open(api.getValuationExportUrl(project.id, currentRunId, "json"), "_blank");
                    }}
                  />
                </HStack>
              )}
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={5}>
            {message && (
              <Banner status={bannerType} title="Valuation Notice">
                {message}
              </Banner>
            )}

            {/* TAB 1: FCFF DCF */}
            {activeTab === "fcff_dcf" && (
              <VStack gap={4}>
                <VStack gap={3}>
                  <Heading level={3}>Model Assumptions & Inputs</Heading>
                  <Selector
                    label="Target Security"
                    value={targetId}
                    onChange={handleSecuritySelect}
                    options={securities.map((security) => ({
                      value: security.security_id,
                      label: `${security.symbol} — ${security.name} (${security.currency})`,
                    }))}
                    placeholder="Select a target Security"
                    hasSearch
                  />
                  <HStack gap={3}>
                    <TextInput
                      label="Base Revenue ($M)"
                      value={baseRevenue}
                      onChange={(val) => setBaseRevenue(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Revenue Growth Rate (%)"
                      value={revenueGrowth}
                      onChange={(val) => setRevenueGrowth(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Operating Margin (%)"
                      value={operatingMargin}
                      onChange={(val) => setOperatingMargin(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Effective Tax Rate (%)"
                      value={taxRate}
                      onChange={(val) => setTaxRate(typeof val === "string" ? val : "")}
                    />
                  </HStack>
                  <HStack gap={3}>
                    <TextInput
                      label="Reinvestment Rate (% NOPAT)"
                      value={reinvestmentRate}
                      onChange={(val) => setReinvestmentRate(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="WACC / Discount Rate (%)"
                      value={wacc}
                      onChange={(val) => setWacc(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Terminal Growth Rate (%)"
                      value={terminalGrowth}
                      onChange={(val) => setTerminalGrowth(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Shares Outstanding (M)"
                      value={sharesOutstanding}
                      onChange={(val) => setSharesOutstanding(typeof val === "string" ? val : "")}
                    />
                  </HStack>
                  <HStack gap={3}>
                    <TextInput
                      label="Total Debt ($M)"
                      value={totalDebt}
                      onChange={(val) => setTotalDebt(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Cash & Equivalents ($M)"
                      value={cash}
                      onChange={(val) => setCash(typeof val === "string" ? val : "")}
                    />
                    <TextInput
                      label="Forecast Horizon (Years)"
                      value={forecastYears}
                      onChange={(val) => setForecastYears(typeof val === "string" ? val : "")}
                    />
                  </HStack>
                </VStack>

                {dcfResult && (
                  <VStack gap={4}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>Valuation Summary: {dcfResult.symbol} ({dcfResult.currency})</Heading>
                      <HStack gap={2}>
                        {dcfResult.method_revision && (
                          <Token label={dcfResult.method_revision} color="green" />
                        )}
                        <Token label={`${dcfResult.dataset_version_ids.length} Dataset Versions`} color="blue" />
                      </HStack>
                    </HStack>

                    {/* Headline KPI cards */}
                    <HStack gap={3}>
                      <VStack gap={1} style={{ padding: "16px", background: "var(--color-bg-subtle, #f8fafc)", borderRadius: "8px", flex: 1 }}>
                        <Text type="supporting">Value Per Share</Text>
                        <Heading level={2}>{currencyFormat(dcfResult.value_per_share, dcfResult.currency)}</Heading>
                      </VStack>
                      <VStack gap={1} style={{ padding: "16px", background: "var(--color-bg-subtle, #f8fafc)", borderRadius: "8px", flex: 1 }}>
                        <Text type="supporting">Enterprise Value</Text>
                        <Heading level={2}>{currencyFormat(dcfResult.enterprise_value, dcfResult.currency)}</Heading>
                      </VStack>
                      <VStack gap={1} style={{ padding: "16px", background: "var(--color-bg-subtle, #f8fafc)", borderRadius: "8px", flex: 1 }}>
                        <Text type="supporting">Equity Value</Text>
                        <Heading level={2}>{currencyFormat(dcfResult.equity_value, dcfResult.currency)}</Heading>
                      </VStack>
                      <VStack gap={1} style={{ padding: "16px", background: "var(--color-bg-subtle, #f8fafc)", borderRadius: "8px", flex: 1 }}>
                        <Text type="supporting">Terminal Contribution</Text>
                        <Heading level={2}>{percentage(dcfResult.terminal_value_contribution)}</Heading>
                      </VStack>
                    </HStack>

                    {/* Forecast Cash Flows Table */}
                    <VStack gap={2}>
                      <Heading level={4}>Forecast Free Cash Flows to Firm</Heading>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Forecast Period</TableHeaderCell>
                            <TableHeaderCell>Revenue</TableHeaderCell>
                            <TableHeaderCell>Growth</TableHeaderCell>
                            <TableHeaderCell>EBIT</TableHeaderCell>
                            <TableHeaderCell>NOPAT</TableHeaderCell>
                            <TableHeaderCell>Reinvestment</TableHeaderCell>
                            <TableHeaderCell>FCFF</TableHeaderCell>
                            <TableHeaderCell>Discount Factor</TableHeaderCell>
                            <TableHeaderCell>Present Value</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {dcfResult.forecast_cash_flows.map((cf) => (
                            <TableRow key={cf.year}>
                              <TableCell><Text weight="medium">Year {cf.year}</Text></TableCell>
                              <TableCell>{cf.revenue.toFixed(2)}</TableCell>
                              <TableCell>{percentage(cf.revenue_growth)}</TableCell>
                              <TableCell>{cf.operating_income.toFixed(2)}</TableCell>
                              <TableCell>{cf.nopat.toFixed(2)}</TableCell>
                              <TableCell>{cf.reinvestment.toFixed(2)}</TableCell>
                              <TableCell><Text weight="bold">{cf.free_cash_flow.toFixed(2)}</Text></TableCell>
                              <TableCell>{cf.discount_factor.toFixed(4)}</TableCell>
                              <TableCell>{cf.present_value.toFixed(2)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </VStack>

                    {/* Scenario Analysis */}
                    <VStack gap={2}>
                      <Heading level={4}>Scenario Analysis</Heading>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>Scenario</TableHeaderCell>
                            <TableHeaderCell>WACC</TableHeaderCell>
                            <TableHeaderCell>Terminal Growth</TableHeaderCell>
                            <TableHeaderCell>Revenue Growth</TableHeaderCell>
                            <TableHeaderCell>Operating Margin</TableHeaderCell>
                            <TableHeaderCell>Enterprise Value</TableHeaderCell>
                            <TableHeaderCell>Value Per Share</TableHeaderCell>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {dcfResult.scenarios.map((sc) => (
                            <TableRow key={sc.name}>
                              <TableCell><Text weight="bold">{sc.name}</Text></TableCell>
                              <TableCell>{percentage(sc.wacc)}</TableCell>
                              <TableCell>{percentage(sc.terminal_growth_rate)}</TableCell>
                              <TableCell>{percentage(sc.revenue_growth_rate)}</TableCell>
                              <TableCell>{percentage(sc.operating_margin)}</TableCell>
                              <TableCell>{currencyFormat(sc.enterprise_value, dcfResult.currency)}</TableCell>
                              <TableCell><Text weight="bold">{currencyFormat(sc.value_per_share, dcfResult.currency)}</Text></TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </VStack>

                    {/* Sensitivity Matrix */}
                    <VStack gap={2}>
                      <Heading level={4}>Sensitivity Matrix (WACC vs Terminal Growth Rate)</Heading>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHeaderCell>WACC \ Terminal Growth</TableHeaderCell>
                            {dcfResult.sensitivity.terminal_growth_values.map((tg) => (
                              <TableHeaderCell key={tg}>{percentage(tg)}</TableHeaderCell>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {dcfResult.sensitivity.wacc_values.map((wVal, rIdx) => (
                            <TableRow key={wVal}>
                              <TableCell><Text weight="bold">{percentage(wVal)}</Text></TableCell>
                              {dcfResult.sensitivity.grid[rIdx]?.map((val, cIdx) => (
                                <TableCell key={cIdx}>
                                  {val !== null && val !== undefined ? currencyFormat(val, dcfResult.currency) : "—"}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </VStack>

                    <Text type="supporting">
                      Calculated at {new Date(dcfResult.calculated_at).toLocaleString()}.
                      {dcfResult.method_revision ? ` Revision: ${dcfResult.method_revision}.` : ""}
                      {dcfResult.run_id ? ` Run ID: ${dcfResult.run_id}.` : ""}
                    </Text>
                    {dcfResult.warnings.length > 0 && (
                      <Banner status="warning" title="Model Notices">
                        {dcfResult.warnings.join(" ")}
                      </Banner>
                    )}
                  </VStack>
                )}
              </VStack>
            )}

            {/* TAB 2: COMPARABLES */}
            {activeTab === "comparables" && (
              <VStack gap={4}>
                <VStack gap={3}>
                  <Heading level={3}>Selection</Heading>
                  <Selector
                    label="Target Security"
                    value={targetId}
                    onChange={(value) => {
                      setTargetId(value);
                      setPeerIds((current) => current.filter((peerId) => peerId !== value));
                      setComparableResult(null);
                    }}
                    options={securities.map((security) => ({
                      value: security.security_id,
                      label: `${security.symbol} — ${security.name}`,
                    }))}
                    placeholder="Select a target Security"
                    hasSearch
                  />
                  <CheckboxList
                    label="Peer Securities"
                    description="Only peers with the target currency contribute to peer medians."
                    value={peerIds}
                    onChange={setPeerIds}
                    hasDividers
                  >
                    {peers.map((security) => (
                      <CheckboxListItem
                        key={security.security_id}
                        value={security.security_id}
                        label={`${security.symbol} — ${security.name}`}
                        description={security.currency}
                      />
                    ))}
                  </CheckboxList>
                </VStack>

                {comparableResult && (
                  <VStack gap={3}>
                    <HStack justify="between" align="center">
                      <Heading level={3}>Trading Multiples</Heading>
                      <HStack gap={2}>
                        {comparableResult.method_revision && (
                          <Token label={comparableResult.method_revision} color="green" />
                        )}
                        <Token label={`${comparableResult.dataset_version_ids.length} Dataset Versions`} color="blue" />
                      </HStack>
                    </HStack>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Security</TableHeaderCell>
                          <TableHeaderCell>P/E</TableHeaderCell>
                          <TableHeaderCell>EV / Revenue</TableHeaderCell>
                          <TableHeaderCell>EV / EBITDA</TableHeaderCell>
                          <TableHeaderCell>Free-cash-flow Yield</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[comparableResult.target, ...comparableResult.peers, comparableResult.peer_medians].map((company) => (
                          <TableRow key={company.security_id}>
                            <TableCell><Text weight="medium">{company.name}</Text></TableCell>
                            <TableCell>{multiple(company.price_to_earnings)}</TableCell>
                            <TableCell>{multiple(company.ev_to_revenue)}</TableCell>
                            <TableCell>{multiple(company.ev_to_ebitda)}</TableCell>
                            <TableCell>{percentage(company.free_cash_flow_yield)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Text type="supporting">
                      Calculated {new Date(comparableResult.calculated_at).toLocaleString()}.
                      {comparableResult.method_revision ? ` Method revision: ${comparableResult.method_revision}.` : ""}
                      {comparableResult.run_id ? ` Run: ${comparableResult.run_id}.` : ""}
                    </Text>
                    {comparableResult.warnings.length > 0 && (
                      <Banner status="warning" title="Input warnings">
                        {comparableResult.warnings.join(" ")}
                      </Banner>
                    )}
                  </VStack>
                )}
              </VStack>
            )}

            {/* TAB 3: SIDE-BY-SIDE COMPARISON */}
            {activeTab === "comparison" && (
              <VStack gap={4}>
                <VStack gap={3}>
                  <Heading level={3}>Select Saved Valuations</Heading>
                  <Text type="supporting">Select 2 or more saved Valuation runs to compare assumptions, revisions, and outputs side-by-side.</Text>
                  {savedValuations.length === 0 ? (
                    <Banner status="info" title="No Saved Valuations">
                      Save at least two DCF or Comparable Valuations to enable side-by-side comparison.
                    </Banner>
                  ) : (
                    <VStack gap={2}>
                      <CheckboxList
                        label="Saved Runs"
                        value={selectedRunIds}
                        onChange={setSelectedRunIds}
                        hasDividers
                      >
                        {savedValuations.map((val) => {
                          const res = val.result as any;
                          const sym = res?.symbol || res?.target?.symbol || "Unknown";
                          return (
                            <CheckboxListItem
                              key={val.run_id}
                              value={val.run_id}
                              label={`${val.method_revision} — ${sym} (${val.run_id})`}
                              description={`Calculated: ${new Date(val.calculated_at).toLocaleString()}`}
                            />
                          );
                        })}
                      </CheckboxList>
                      <HStack gap={2}>
                        <Button
                          label="Compare Selected Valuations"
                          variant="primary"
                          onClick={handleCompare}
                          isLoading={isComparing}
                          isDisabled={selectedRunIds.length < 2}
                        />
                      </HStack>
                    </VStack>
                  )}
                </VStack>

                {comparisonResult && (
                  <VStack gap={3}>
                    <Heading level={3}>Comparative Analysis ({comparisonResult.items.length} Runs)</Heading>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHeaderCell>Revision & Run</TableHeaderCell>
                          <TableHeaderCell>Method</TableHeaderCell>
                          <TableHeaderCell>Security</TableHeaderCell>
                          <TableHeaderCell>Value Per Share</TableHeaderCell>
                          <TableHeaderCell>Enterprise Value</TableHeaderCell>
                          <TableHeaderCell>Terminal Contribution</TableHeaderCell>
                          <TableHeaderCell>Key Assumptions</TableHeaderCell>
                          <TableHeaderCell>Exports</TableHeaderCell>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {comparisonResult.items.map((item) => (
                          <TableRow key={item.run_id}>
                            <TableCell>
                              <VStack gap={0}>
                                <Text weight="bold">{item.method_revision}</Text>
                                <Text type="supporting" style={{ fontSize: "0.75rem" }}>{item.run_id}</Text>
                              </VStack>
                            </TableCell>
                            <TableCell><Token label={item.method} color="blue" /></TableCell>
                            <TableCell><Text weight="medium">{item.symbol}</Text></TableCell>
                            <TableCell><Text weight="bold">{currencyFormat(item.value_per_share, item.currency)}</Text></TableCell>
                            <TableCell>{currencyFormat(item.enterprise_value, item.currency)}</TableCell>
                            <TableCell>{percentage(item.terminal_value_contribution)}</TableCell>
                            <TableCell>
                              <VStack gap={0} style={{ fontSize: "0.8rem" }}>
                                {item.method === "fcff_dcf" ? (
                                  <>
                                    <Text>WACC: {((Number(item.key_assumptions.wacc) || 0) * 100).toFixed(1)}%</Text>
                                    <Text>Term Growth: {((Number(item.key_assumptions.terminal_growth_rate) || 0) * 100).toFixed(1)}%</Text>
                                    <Text>Rev Growth: {((Number(item.key_assumptions.revenue_growth_rate) || 0) * 100).toFixed(1)}%</Text>
                                  </>
                                ) : (
                                  <>
                                    <Text>P/E: {multiple(item.price_to_earnings)}</Text>
                                    <Text>EV/Rev: {multiple(item.ev_to_revenue)}</Text>
                                    <Text>EV/EBITDA: {multiple(item.ev_to_ebitda)}</Text>
                                  </>
                                )}
                              </VStack>
                            </TableCell>
                            <TableCell>
                              {project && (
                                <HStack gap={1}>
                                  <Button
                                    label="HTML"
                                    variant="tertiary"
                                    onClick={() => window.open(api.getValuationExportUrl(project.id, item.run_id, "html"), "_blank")}
                                  />
                                  <Button
                                    label="CSV"
                                    variant="tertiary"
                                    onClick={() => window.open(api.getValuationExportUrl(project.id, item.run_id, "csv"), "_blank")}
                                  />
                                </HStack>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </VStack>
                )}
              </VStack>
            )}
          </VStack>
        </LayoutContent>
      }
    />
  );
}
