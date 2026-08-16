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
    if (!project || !result) return;
    setIsSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveDefinition(project.id, {
        kind: "valuation",
        name: `Comparable valuation - ${result.target.symbol}`,
        definition: {
          method: "trading_comparables",
          target_security_id: targetId,
          peer_security_ids: peerIds,
          result,
        },
      });
      setMessage(`Saved revision ${saved.revision}.`);
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
              <Heading level={2}>Comparable-company Valuation</Heading>
              <Text type="supporting">Use locally available Securities and their recorded inputs.</Text>
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
              <Button label="Calculate" variant="primary" onClick={calculate} isLoading={isCalculating} />
              <Button
                label="Save Revision"
                variant="secondary"
                onClick={saveRevision}
                isLoading={isSaving}
                isDisabled={!project || !result || method !== "comparables"}
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
              <Banner status="warning" title="FCFF DCF">
                Select Trading Comparables to calculate and save a comparable-company Valuation.
              </Banner>
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
                <Text type="supporting">Calculated {new Date(result.calculated_at).toLocaleString()}.</Text>
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
