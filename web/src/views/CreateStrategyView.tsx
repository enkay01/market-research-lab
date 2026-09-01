import { useEffect, useState } from "react";
import {
  Layout,
  LayoutHeader,
  LayoutContent,
  VStack,
  HStack,
  Button,
  TextInput,
  Heading,
  Text,
  Banner,
  Selector,
  Card,
  Badge,
} from "@astryxdesign/core";
import {
  api,
  type StrategyMetadata,
  type StrategyEvaluation,
  type Project,
  type CoverageResponse,
} from "../api/client";

function parseParamValue(
  value: string | number | boolean | null | undefined,
  paramType: string,
): string | number | boolean {
  if (paramType === "int") {
    return parseInt(String(value ?? 0), 10);
  }
  if (paramType === "float") {
    return parseFloat(String(value ?? 0));
  }
  if (paramType === "bool") {
    return Boolean(value);
  }
  return String(value ?? "");
}

interface CreateStrategyViewProps {
  project?: Project;
}

export function CreateStrategyView({ project }: CreateStrategyViewProps) {
  const [strategies, setStrategies] = useState<StrategyMetadata[]>([]);
  const [selectedStrategyName, setSelectedStrategyName] = useState<string>("long_flat_moving_average");
  const [parameters, setParameters] = useState<Record<string, string | number | boolean>>({});
  const [templateCode, setTemplateCode] = useState<string>("");
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("");
  const [evaluationResult, setEvaluationResult] = useState<StrategyEvaluation | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: "info" | "success" | "error" } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const [stratList, dsList, secList, tmpl] = await Promise.all([
          api.listStrategies(),
          api.listDatasets(),
          api.listSecurities({ limit: 200 }),
          api.getStrategyTemplate(),
        ]);

        setStrategies(stratList);
        if (stratList.length > 0) {
          const initial = stratList[0];
          setSelectedStrategyName(initial.name);
          const defaults: Record<string, string | number | boolean> = {};
          for (const param of initial.parameters) {
            defaults[param.name] = parseParamValue(param.default, param.param_type);
          }
          setParameters(defaults);
        }

        const validDatasets = dsList.filter((d) => d.dataset_type !== "corporate_actions");
        setDatasets(validDatasets);
        if (validDatasets.length > 0) {
          setSelectedDatasetId(validDatasets[0].id);
        }

        if (secList.length > 0) {
          setSymbol(secList[0].symbol);
        } else {
          setSymbol("AAPL");
        }

        setTemplateCode(tmpl.code);
      } catch (err: unknown) {
        console.error("Failed to initialize strategy view data:", err);
      }
    }

    void loadData();
  }, []);

  function handleStrategyChange(name: string) {
    setSelectedStrategyName(name);
    const strat = strategies.find((s) => s.name === name);
    if (strat) {
      const defaults: Record<string, string | number | boolean> = {};
      for (const param of strat.parameters) {
        defaults[param.name] = parseParamValue(param.default, param.param_type);
      }
      setParameters(defaults);
    }
  }

  const selectedStrategy = strategies.find((s) => s.name === selectedStrategyName);

  async function handleEvaluate() {
    if (!selectedDatasetId) {
      setStatusMessage({ text: "Please download or select a dataset version first.", type: "error" });
      return;
    }
    setIsEvaluating(true);
    setStatusMessage(null);
    try {
      const targetSymbol = symbol.trim().toUpperCase() || "AAPL";
      const result = await api.evaluateStrategy({
        name: selectedStrategyName,
        dataset_version_id: selectedDatasetId,
        symbol: targetSymbol,
        parameters,
      });
      setEvaluationResult(result);
      setStatusMessage({
        text: `Strategy '${result.strategy_name}' evaluated successfully for ${targetSymbol} with ${result.targets.length} target decision(s).`,
        type: "success",
      });
    } catch (err: unknown) {
      setStatusMessage({
        text: err instanceof Error ? err.message : "Strategy evaluation failed.",
        type: "error",
      });
    } finally {
      setIsEvaluating(false);
    }
  }

  async function handleSaveRevision() {
    if (!project) {
      setStatusMessage({ text: "Select or create a project to save strategy revisions.", type: "error" });
      return;
    }
    if (!selectedDatasetId) {
      setStatusMessage({ text: "Please select a dataset version.", type: "error" });
      return;
    }
    try {
      const targetSymbol = symbol.trim().toUpperCase() || "AAPL";
      await api.saveStrategyEvaluation(project.id, {
        name: selectedStrategyName,
        dataset_version_id: selectedDatasetId,
        symbol: targetSymbol,
        parameters,
      });
      setStatusMessage({
        text: `Strategy '${selectedStrategy?.display_name}' saved to project '${project.name}'.`,
        type: "success",
      });
    } catch (err: unknown) {
      setStatusMessage({
        text: err instanceof Error ? err.message : "Failed to save strategy revision.",
        type: "error",
      });
    }
  }

  function handleCopyTemplate() {
    navigator.clipboard.writeText(templateCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  }

  const datasetOptions = datasets.map((d) => ({
    value: d.id,
    label: `${d.source || "Dataset"} (${d.dataset_type}) — ${d.coverage_start ?? "?"} to ${d.coverage_end ?? "?"} [${d.row_count} rows] (${d.id.slice(0, 8)})`,
  }));

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={3}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <VStack gap={1}>
              <Heading level={2}>
                Create &amp; Configure Trading Strategy
              </Heading>
              <Text type="supporting">
                Configure built-in indicators, options credit spreads, or write custom Python strategies with automatic discovery.
              </Text>
            </VStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={4} isScrollable>
          <VStack gap={4} style={{ maxWidth: "1280px", margin: "0 auto" }}>
            {statusMessage && (
              <Banner
                status={statusMessage.type === "error" ? "error" : statusMessage.type === "success" ? "success" : "info"}
                title={statusMessage.text}
              />
            )}

            <div style={{ display: "grid", gridTemplateColumns: "minmax(380px, 480px) 1fr", gap: "24px", alignItems: "start" }}>
              {/* Left Column: Strategy Configuration & Evaluation Controls */}
              <VStack gap={4}>
                <Card style={{ padding: "20px" }}>
                  <VStack gap={3}>
                    <Text weight="bold" size="lg">1. Choose Strategy</Text>
                    <Selector
                      label="Strategy Selection"
                      options={strategies.map((s) => ({
                        value: s.name,
                        label: s.display_name,
                      }))}
                      value={selectedStrategyName}
                      onChange={handleStrategyChange}
                      isRequired
                    />
                    {selectedStrategy && (
                      <Text type="supporting">{selectedStrategy.description}</Text>
                    )}

                    <HStack gap={2} style={{ marginTop: "4px" }}>
                      <Badge
                        label={selectedStrategyName.startsWith("custom_") ? "Custom Plugin" : "Built-in Strategy"}
                        variant={selectedStrategyName.startsWith("custom_") ? "purple" : "blue"}
                      />
                    </HStack>
                  </VStack>
                </Card>

                <Card style={{ padding: "20px" }}>
                  <VStack gap={3}>
                    <Text weight="bold" size="lg">2. Strategy Parameters</Text>
                    {selectedStrategy?.parameters && selectedStrategy.parameters.length > 0 ? (
                      selectedStrategy.parameters.map((param) => (
                        <VStack key={param.name} gap={1}>
                          <TextInput
                            label={`${param.name} (${param.param_type})`}
                            value={String(parameters[param.name] ?? param.default ?? "")}
                            onChange={(val) => {
                              const numVal =
                                param.param_type === "int"
                                  ? parseInt(String(val), 10)
                                  : param.param_type === "float"
                                    ? parseFloat(String(val))
                                    : val;
                              setParameters((prev) => ({ ...prev, [param.name]: numVal }));
                            }}
                            description={param.description}
                          />
                        </VStack>
                      ))
                    ) : (
                      <Text type="supporting">No configurable parameters for this strategy.</Text>
                    )}
                  </VStack>
                </Card>

                <Card style={{ padding: "20px" }}>
                  <VStack gap={3}>
                    <Text weight="bold" size="lg">3. Evaluation Scope &amp; Target Dataset</Text>
                    <Selector
                      label="Market Dataset"
                      options={datasetOptions}
                      value={selectedDatasetId}
                      onChange={(val) => setSelectedDatasetId(val)}
                      placeholder={datasets.length === 0 ? "No datasets found - download one first" : "Select dataset version"}
                      isRequired
                    />

                    <TextInput
                      label="Target Asset / Universe"
                      value={symbol}
                      onChange={(val) => setSymbol(String(val ?? "").toUpperCase())}
                      placeholder="e.g. AAPL, SPY, MSFT"
                      description="Symbol or asset universe to evaluate strategy signals on."
                    />

                    <HStack gap={2} style={{ marginTop: "8px" }}>
                      <Button
                        label="Evaluate Strategy"
                        variant="primary"
                        onClick={handleEvaluate}
                        isLoading={isEvaluating}
                      />
                      {project && (
                        <Button
                          label="Save to Project"
                          variant="secondary"
                          onClick={handleSaveRevision}
                        />
                      )}
                    </HStack>
                  </VStack>
                </Card>
              </VStack>

              {/* Right Column: Dynamic Evaluation Results & Extensibility Guide */}
              <VStack gap={4}>
                {evaluationResult && (
                  <Card style={{ padding: "20px" }}>
                    <VStack gap={3}>
                      <HStack justify="space-between" align="center">
                        <Text weight="bold" size="lg">Evaluation Results &amp; Target Allocations</Text>
                        <Badge
                          label={`${evaluationResult.targets.length} Target(s)`}
                          variant="green"
                        />
                      </HStack>
                      <Text type="supporting">
                        Strategy: <strong>{evaluationResult.strategy_name}</strong> | Decision Time: <strong>{evaluationResult.decision_time}</strong>
                      </Text>

                      <div style={{ maxHeight: "320px", overflowY: "auto", border: "1px solid var(--color-border-subtle, #30363d)", borderRadius: "6px" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                          <thead>
                            <tr style={{ background: "var(--color-bg-subtle, #161b22)", borderBottom: "1px solid var(--color-border-subtle, #30363d)", textAlign: "left" }}>
                              <th style={{ padding: "8px 12px" }}>Security</th>
                              <th style={{ padding: "8px 12px" }}>Target Allocation</th>
                              <th style={{ padding: "8px 12px" }}>Signal Rationale</th>
                              {evaluationResult.indicator_name && <th style={{ padding: "8px 12px" }}>Indicator State</th>}
                            </tr>
                          </thead>
                          <tbody>
                            {evaluationResult.targets.map((t, idx) => {
                              const weightPct = t.weight * 100;
                              const weightColor = weightPct > 0 ? "#3fb950" : weightPct < 0 ? "#f85149" : "#8b949e";
                              return (
                                <tr key={idx} style={{ borderBottom: "1px solid var(--color-border-subtle, #21262d)" }}>
                                  <td style={{ padding: "8px 12px", fontWeight: "bold" }}>{t.security_id}</td>
                                  <td style={{ padding: "8px 12px", color: weightColor, fontWeight: "bold" }}>
                                    {weightPct > 0 ? `+${weightPct.toFixed(0)}% (LONG)` : weightPct < 0 ? `${weightPct.toFixed(0)}% (SHORT)` : `0% (FLAT)`}
                                  </td>
                                  <td style={{ padding: "8px 12px" }}>{t.rationale}</td>
                                  {evaluationResult.indicator_name && (
                                    <td style={{ padding: "8px 12px" }}>{t.indicator_state ?? "—"}</td>
                                  )}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </VStack>
                  </Card>
                )}

                <Card style={{ padding: "20px" }}>
                  <VStack gap={3}>
                    <HStack justify="space-between" align="center">
                      <Text weight="bold" size="lg">Add a new Strategy</Text>
                      <Button
                        label={copied ? "Copied!" : "Copy Python Template"}
                        variant="secondary"
                        size="sm"
                        onClick={handleCopyTemplate}
                      />
                    </HStack>
                    <Text type="supporting">
                      Drop any Python file into <code style={{ padding: "2px 6px", background: "var(--color-neutral-subtle, #161b22)", borderRadius: "4px" }}>engine/src/market_research_lab/custom_strategies/</code>. The engine automatically discovers it, registers its parameter schema, and makes it available in the dropdown!
                    </Text>
                    <pre
                      style={{
                        backgroundColor: "#0d1117",
                        color: "#e6edf3",
                        padding: "14px",
                        borderRadius: "6px",
                        fontSize: "12px",
                        overflowX: "auto",
                        maxHeight: "220px",
                        lineHeight: "1.45",
                        border: "1px solid #30363d",
                      }}
                    >
                      <code>{templateCode || "# Loading template..."}</code>
                    </pre>
                  </VStack>
                </Card>
              </VStack>
            </div>
          </VStack>
        </LayoutContent>
      }
    />
  );
}
