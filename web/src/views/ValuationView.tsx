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
  type Project,
  type Security,
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

export function ValuationView({ project }: ValuationViewProps) {
  const [method, setMethod] = useState<"fcff_dcf" | "comparables">("comparables");
  const [wacc, setWacc] = useState("8.5");
  const [terminalGrowth, setTerminalGrowth] = useState("2.5");
  const [revenueGrowth, setRevenueGrowth] = useState("7.0");
  const [securities, setSecurities] = useState<Security[]>([]);
  const [targetId, setTargetId] = useState("");
  const [peerIds, setPeerIds] = useState<string[]>([]);
  const [result, setResult] = useState<ComparableValuation | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    api.listSecurities({ limit: 500 })
      .then((available) => {
        setSecurities(available);
        setTargetId((current) => current || available[0]?.security_id || "");
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Could not load local Securities.");
      });
  }, []);

  useEffect(() => {
    if (!project) return;
    api.listValuations(project.id)
      .then((valuations) => {
        const latest = valuations.at(-1);
        if (!latest) return;
        setResult(latest.result);
        setTargetId(latest.result.target.security_id);
        setPeerIds(latest.result.peers.map((peer) => peer.security_id));
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "Could not reload saved Valuations.");
      });
  }, [project?.id]);

  const peers = useMemo(
    () => securities.filter((security) => security.security_id !== targetId),
    [securities, targetId],
  );

  async function calculate() {
    if (method !== "comparables") {
      setMessage("FCFF DCF calculation is not available in this view yet.");
      return;
    }
    if (!targetId || peerIds.length === 0) {
      setMessage("Select one target Security and at least one peer Security.");
      return;
    }
    setIsCalculating(true);
    setMessage(null);
    try {
      const valuation = await api.calculateComparableValuation({
        target_security_id: targetId,
        peer_security_ids: peerIds,
      });
      setResult(valuation);
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Could not calculate the comparable-company Valuation.");
    } finally {
      setIsCalculating(false);
    }
  }

  async function saveRevision() {
    if (!project) return;
    if (!targetId) {
      setMessage("Select a target Security before saving the Valuation.");
      return;
    }
    setIsSaving(true);
    setMessage(null);
    try {
      if (method === "fcff_dcf") {
        const saved = await api.saveDefinition(project.id, {
          kind: "valuation",
          name: "FCFF DCF valuation",
          definition: {
            method: "fcff_dcf",
            target_security_id: targetId,
            wacc: Number(wacc),
            terminal_growth: Number(terminalGrowth),
            revenue_growth: Number(revenueGrowth),
            currency: "USD",
          },
        });
        setMessage(`Saved FCFF DCF revision ${saved.revision}.`);
      } else {
        const saved = await api.saveComparableValuation(project.id, {
          target_security_id: targetId,
          peer_security_ids: peerIds,
        });
        setResult(saved);
        setMessage(`Saved ${saved.method_revision ?? "comparable"} in Run ${saved.run_id ?? ""}.`);
      }
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Could not save the Valuation revision.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
            <HStack justify="between" align="center">
            <VStack gap={0}>
              <Heading level={2}>
                {method === "comparables" ? "Comparable-company Valuation" : "Valuation Workspace"}
              </Heading>
              <Text type="supporting">
                {method === "comparables"
                  ? "Use locally available Securities and their recorded inputs."
                  : "Save FCFF DCF assumptions as a Definition Revision."}
              </Text>
            </VStack>
            <HStack gap={2}>
              <SegmentedControl
                label="Valuation method"
                value={method}
                onChange={(value) => setMethod(value as "fcff_dcf" | "comparables")}
              >
                <SegmentedControlItem value="fcff_dcf" label="FCFF DCF" />
                <SegmentedControlItem value="comparables" label="Trading Comparables" />
              </SegmentedControl>
              <Button
                label="Calculate"
                variant="primary"
                onClick={calculate}
                isLoading={isCalculating}
                isDisabled={method === "fcff_dcf"}
              />
              <Button
                label="Save Revision"
                variant="secondary"
                onClick={saveRevision}
                isLoading={isSaving}
                isDisabled={!project || (method === "comparables" && !result)}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={5}>
            {message && <Banner status="warning" title="Valuation status">{message}</Banner>}
            {method === "fcff_dcf" ? (
              <VStack gap={3}>
                <Heading level={3}>FCFF DCF</Heading>
                <Text type="supporting">Save the current forecast assumptions as a Definition Revision.</Text>
                <Selector
                  label="Target Security"
                  value={targetId}
                  onChange={setTargetId}
                  options={securities.map((security) => ({
                    value: security.security_id,
                    label: `${security.symbol} — ${security.name}`,
                  }))}
                  placeholder="Select a target Security"
                  hasSearch
                />
                <TextInput
                  label="WACC (%)"
                  value={wacc}
                  onChange={(value) => setWacc(typeof value === "string" ? value : "")}
                />
                <TextInput
                  label="Terminal growth (%)"
                  value={terminalGrowth}
                  onChange={(value) => setTerminalGrowth(typeof value === "string" ? value : "")}
                />
                <TextInput
                  label="Revenue growth (%)"
                  value={revenueGrowth}
                  onChange={(value) => setRevenueGrowth(typeof value === "string" ? value : "")}
                />
              </VStack>
            ) : (
              <VStack gap={3}>
              <Heading level={3}>Selection</Heading>
              <Selector
                label="Target Security"
                value={targetId}
                onChange={(value) => {
                  setTargetId(value);
                  setPeerIds((current) => current.filter((peerId) => peerId !== value));
                  setResult(null);
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
            )}

            {method === "comparables" && result && (
              <VStack gap={3}>
                <HStack justify="between" align="center">
                  <Heading level={3}>Results</Heading>
                  <Token label={`${result.dataset_version_ids.length} Dataset Versions`} color="blue" />
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
                    {[result.target, ...result.peers, result.peer_medians].map((company) => (
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
                  Calculated {new Date(result.calculated_at).toLocaleString()}.
                  {result.method_revision ? ` Method revision: ${result.method_revision}.` : ""}
                  {result.run_id ? ` Run: ${result.run_id}.` : ""}
                </Text>
                {result.warnings.length > 0 && (
                  <Banner status="warning" title="Input warnings">
                    {result.warnings.join(" ")}
                  </Banner>
                )}
              </VStack>
            )}
          </VStack>
        </LayoutContent>
      }
    />
  );
}
