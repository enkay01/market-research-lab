import { useCallback, useEffect, useState } from "react";
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
  Dialog,
  DialogHeader,
  CodeBlock,
  EmptyState,
  Link,
} from "@astryxdesign/core";
import {
  api,
  type DefinitionRevision,
  type EnabledStrategy,
  type Project,
  type Signal,
  type SignalRefresh,
} from "../api/client";

type AlertFeedState = "offline-engine" | "no-alerts" | "stale-data" | "fresh";

interface AlertsViewProps {
  project?: Project;
  engineConnected: boolean;
  onOpenSecurity?: (securityId: string) => void;
}

function splitStrategyRevision(strategyRevision: string): { name: string; revision: string } | null {
  const separator = strategyRevision.lastIndexOf(":");
  if (separator <= 0 || separator === strategyRevision.length - 1) {
    return null;
  }
  return {
    name: strategyRevision.slice(0, separator),
    revision: strategyRevision.slice(separator + 1),
  };
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatWeight(weight: number): string {
  return `${(weight * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

function actionTokenColor(action: string): "green" | "red" | "default" {
  if (action === "long") return "green";
  if (action === "short") return "red";
  return "default";
}

function alertFeedState(engineConnected: boolean, alerts: Signal[]): AlertFeedState {
  if (!engineConnected) return "offline-engine";
  if (alerts.length === 0) return "no-alerts";
  return alerts.some((alert) => alert.data_state === "stale-data") ? "stale-data" : "fresh";
}

export function AlertsView({ project, engineConnected, onOpenSecurity }: AlertsViewProps) {
  const [alerts, setAlerts] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<SignalRefresh | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [revisionDetail, setRevisionDetail] = useState<DefinitionRevision | null>(null);
  const [revisionError, setRevisionError] = useState<string | null>(null);

  const loadAlerts = useCallback(async () => {
    if (!project) {
      setAlerts([]);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    try {
      setAlerts(await api.listAlerts(project.id));
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : "Failed to load Alerts.");
    } finally {
      setIsLoading(false);
    }
  }, [project]);

  useEffect(() => {
    setRefreshResult(null);
    setRefreshError(null);
    void loadAlerts();
  }, [loadAlerts]);

  async function handleRefresh() {
    if (!project || !engineConnected) return;
    setIsRefreshing(true);
    setRefreshError(null);
    try {
      setRefreshResult(await api.refreshAlerts(project.id));
      await loadAlerts();
    } catch (err: unknown) {
      setRefreshResult(null);
      setRefreshError(err instanceof Error ? err.message : "Failed to evaluate Strategies.");
    } finally {
      setIsRefreshing(false);
    }
  }

  async function openRevisionDetail(strategyRevision: string) {
    if (!project) return;
    const parts = splitStrategyRevision(strategyRevision);
    if (!parts) {
      setRevisionError(`'${strategyRevision}' does not name a saved Strategy revision.`);
      setRevisionDetail(null);
      return;
    }
    setRevisionError(null);
    try {
      setRevisionDetail(
        await api.getDefinitionRevision(project.id, "strategy", parts.name, parts.revision),
      );
    } catch (err: unknown) {
      setRevisionDetail(null);
      setRevisionError(err instanceof Error ? err.message : "Failed to load the Strategy revision.");
    }
  }

  function closeRevisionDetail(open: boolean) {
    if (!open) {
      setRevisionDetail(null);
      setRevisionError(null);
    }
  }

  const feedState = alertFeedState(engineConnected, alerts);
  const canRefresh = Boolean(project) && engineConnected && !isRefreshing;

  return (
    <>
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Alerts</Heading>
              {alerts.length > 0 && <Badge label={String(alerts.length)} variant="error" />}
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
                onClick={() => void handleRefresh()}
                isLoading={isRefreshing}
                isDisabled={!canRefresh}
                tooltip={
                  engineConnected
                    ? "Evaluate every enabled Strategy against the latest eligible data"
                    : "The engine is offline, so Strategies cannot be evaluated"
                }
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4}>
            <Banner
              status="info"
              title="Local Safety Boundary (ADR 0002)"
              description="Alerts are local research notifications. The system never places, routes, or submits an order, never sends mobile notifications, and keeps no trade journal."
            />

            {!engineConnected && (
              <Banner
                status="error"
                title="Engine Offline"
                defaultIsExpanded
                description="The engine is not reachable, so Alerts show the last saved local Signals and cannot be refreshed. Restart the engine to evaluate Strategies again."
              />
            )}
            {engineConnected && feedState === "no-alerts" && (
              <Banner
                status="info"
                title="No Alerts Yet"
                defaultIsExpanded
                description="Enable a Strategy revision and evaluate it against fresh data to produce the first local Alert."
              />
            )}
            {engineConnected && feedState === "stale-data" && (
              <Banner
                status="warning"
                title="Stale Data"
                defaultIsExpanded
                description="One or more active Alerts were evaluated against data older than the Alert freshness window. Refresh the Project datasets before trusting these Signals."
              />
            )}
            {engineConnected && feedState === "fresh" && (
              <Banner
                status="success"
                title="Data Is Fresh"
                description="All active Alerts were evaluated against eligible data inside the freshness window."
              />
            )}

            {loadError && (
              <Banner status="error" title="Load Failed" defaultIsExpanded description={loadError} />
            )}
            {refreshError && (
              <Banner
                status="error"
                title="Evaluation Failed"
                defaultIsExpanded
                description={refreshError}
              />
            )}
            {refreshResult && refreshResult.signals.length > 0 && (
              <Banner
                status="success"
                title="New Signals"
                defaultIsExpanded
                description={`${refreshResult.signals.length} new Signal${
                  refreshResult.signals.length === 1 ? "" : "s"
                } saved as local Alerts.`}
              />
            )}
            {refreshResult &&
              refreshResult.signals.length === 0 &&
              refreshResult.failures.length === 0 && (
                <Banner
                  status="info"
                  title="No New Signals"
                  description="No enabled Strategy produced a new Signal in this evaluation pass."
                />
              )}
            {refreshResult && refreshResult.failures.length > 0 && (
              <Banner
                status="warning"
                title="Some Strategies Failed"
                defaultIsExpanded
                description={refreshResult.failures
                  .map((failure) => `${failure.strategy_revision}: ${failure.error}`)
                  .join(" · ")}
              />
            )}

            {!project ? (
              <EmptyState
                title="No Project Selected"
                description="Create or select a Project to see its Alerts."
              />
            ) : isLoading ? (
              <Text type="supporting">Loading Alerts…</Text>
            ) : alerts.length === 0 ? (
              <EmptyState
                title="No Alerts"
                description="Evaluate an enabled Strategy to produce Signals with rationale and provenance."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Decision Time</TableHeaderCell>
                    <TableHeaderCell>Security</TableHeaderCell>
                    <TableHeaderCell>Strategy Revision</TableHeaderCell>
                    <TableHeaderCell>Intended State</TableHeaderCell>
                    <TableHeaderCell>Data Time</TableHeaderCell>
                    <TableHeaderCell>Rationale</TableHeaderCell>
                    <TableHeaderCell>Provenance</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alerts.map((signal) => (
                    <TableRow key={signal.signal_id}>
                      <TableCell>{formatTimestamp(signal.decision_time)}</TableCell>
                      <TableCell>
                        <Link
                          onClick={() => onOpenSecurity?.(signal.security_id)}
                          label={`Open ${signal.security_id} in Security Research`}
                        >
                          {signal.security_id}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <VStack gap={1} align="start">
                          <Token label={signal.strategy_revision} color="purple" />
                          <Link
                            onClick={() => void openRevisionDetail(signal.strategy_revision)}
                            label={`Inspect Strategy revision ${signal.strategy_revision}`}
                          >
                            Inspect
                          </Link>
                        </VStack>
                      </TableCell>
                      <TableCell>
                        <HStack align="center" gap={2}>
                          <Token label={signal.action.toUpperCase()} color={actionTokenColor(signal.action)} />
                          <Text weight="bold">{formatWeight(signal.weight)}</Text>
                        </HStack>
                      </TableCell>
                      <TableCell>
                        <VStack gap={1} align="start">
                          <Text>{formatTimestamp(signal.data_time)}</Text>
                          {signal.data_state === "fresh" ? (
                            <Token label="fresh data" color="green" />
                          ) : (
                            <Token label="stale data" color="orange" />
                          )}
                        </VStack>
                      </TableCell>
                      <TableCell>{signal.rationale}</TableCell>
                      <TableCell>
                        <VStack gap={1} align="start">
                          <Text type="supporting">Dataset: {signal.dataset_version_id}</Text>
                          {signal.created_at && (
                            <Text type="supporting">Saved: {formatTimestamp(signal.created_at)}</Text>
                          )}
                        </VStack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </VStack>
        </LayoutContent>
      }
      end={
        <LayoutPanel width={380} hasDivider isScrollable label="Enabled Strategies">
          <EnabledStrategiesPanel project={project} refreshResult={refreshResult} />
        </LayoutPanel>
      }
    />

    <Dialog isOpen={revisionDetail !== null || revisionError !== null} onOpenChange={closeRevisionDetail}>
      <DialogHeader
        title="Strategy Revision"
        subtitle={
          revisionDetail
            ? `${revisionDetail.name} · ${revisionDetail.revision}`
            : "Revision could not be read"
        }
      />
      <VStack gap={3}>
        {revisionError && (
          <Banner status="error" title="Not Found">
            {revisionError}
          </Banner>
        )}
        {revisionDetail && (
          <>
            <HStack align="center" gap={2}>
              <Token label={`Kind: ${revisionDetail.kind}`} color="blue" />
              {revisionDetail.saved_at && (
                <Text type="supporting">Saved: {formatTimestamp(revisionDetail.saved_at)}</Text>
              )}
            </HStack>
            <CodeBlock
              title="Immutable Definition Revision (CORE-005)"
              code={JSON.stringify(revisionDetail.definition, null, 2)}
              language="json"
              width="100%"
            />
            <Text type="supporting">
              This revision is immutable. Alerts reference it exactly as saved.
            </Text>
          </>
        )}
      </VStack>
    </Dialog>
    </>
  );
}

function EnabledStrategiesPanel({
  project,
  refreshResult,
}: {
  project?: Project;
  refreshResult: SignalRefresh | null;
}) {
  const [enabled, setEnabled] = useState<EnabledStrategy[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!project) {
      setEnabled([]);
      return;
    }
    let isMounted = true;
    api
      .listEnabledStrategies(project.id)
      .then((items) => {
        if (isMounted) setEnabled(items);
      })
      .catch((err: unknown) => {
        if (isMounted) setError(err instanceof Error ? err.message : "Failed to load enabled Strategies.");
      });
    return () => {
      isMounted = false;
    };
  }, [project, refreshResult]);

  return (
    <VStack gap={4} padding={4}>
      <Heading level={3}>Enabled Strategies</Heading>
      {error && (
        <Banner status="error" title="Load Failed">
          {error}
        </Banner>
      )}
      {!project ? (
        <Text type="supporting">Select a Project to see its enabled Strategies.</Text>
      ) : enabled.length === 0 ? (
        <Text type="supporting">
          No enabled Strategy revisions. Save and enable one to evaluate Signals.
        </Text>
      ) : (
        <VStack gap={2}>
          {enabled.map((item) => (
            <VStack
              key={`${item.name}:${item.revision}`}
              gap={1}
              padding={3}
              style={{
                borderRadius: "var(--radius-element)",
                backgroundColor: "var(--color-background-surface)",
                border: "1px solid var(--color-border)",
              }}
            >
              <HStack justify="between" align="center">
                <Text weight="bold">{item.name}</Text>
                <Token label={item.revision} color="green" />
              </HStack>
              <Text type="supporting">
                Enabled: {formatTimestamp(item.enabled_at)}
              </Text>
            </VStack>
          ))}
        </VStack>
      )}
    </VStack>
  );
}
