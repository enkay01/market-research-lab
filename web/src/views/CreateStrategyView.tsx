import { useEffect, useState } from "react";
import {
  VStack,
  HStack,
  Button,
  TextInput,
  Text,
  Banner,
  Selector,
  Card,
  Badge,
} from "@astryxdesign/core";
import { api, type StrategyMetadata, type StrategyEvaluation, type Project } from "../api/client";

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
  const [datasetVersions, setDatasetVersions] = useState<string[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("SPY");
  const [evaluationResult, setEvaluationResult] = useState<StrategyEvaluation | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: "info" | "success" | "error" } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    void api.listStrategies().then((list) => {
      setStrategies(list);
      if (list.length > 0) {
        const initial = list[0];
        setSelectedStrategyName(initial.name);
        const defaults: Record<string, string | number | boolean> = {};
        for (const param of initial.parameters) {
          defaults[param.name] = parseParamValue(param.default, param.param_type);
        }
        setParameters(defaults);
      }
    });

    void api.getStrategyTemplate().then((res) => {
      setTemplateCode(res.code);
    });

    void api.listSecurities().then((secs) => {
      if (secs.length > 0 && !symbol) {
        setSymbol(secs[0].symbol);
      }
    });

    void api.listDatasets().then((items) => {
      const versions = items.map((i) => i.dataset_version_id);
      setDatasetVersions(versions);
      if (versions.length > 0) {
        setSelectedDataset(versions[0]);
      }
    });
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
    if (!selectedDataset) {
      setStatusMessage({ text: "Please download or select a dataset version first.", type: "error" });
      return;
    }
    setIsEvaluating(true);
    setStatusMessage(null);
    try {
      const result = await api.evaluateStrategy({
        name: selectedStrategyName,
        dataset_version_id: selectedDataset,
        symbol: symbol.trim().toUpperCase(),
        parameters,
      });
      setEvaluationResult(result);
      setStatusMessage({ text: `Strategy evaluated successfully with ${result.targets.length} target allocations.`, type: "success" });
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
    if (!selectedDataset) {
      setStatusMessage({ text: "Please select a dataset version.", type: "error" });
      return;
    }
    try {
      await api.saveStrategyEvaluation(project.id, {
        name: selectedStrategyName,
        dataset_version_id: selectedDataset,
        symbol: symbol.trim().toUpperCase(),
        parameters,
      });
      setStatusMessage({ text: `Strategy '${selectedStrategy?.display_name}' saved to project '${project.name}'.`, type: "success" });
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

  return (
    <VStack gap={4} style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      <VStack gap={1}>
        <Text size="xl" weight="bold">Create & Configure Trading Strategy</Text>
        <Text type="supporting">
          Configure built-in indicators, options credit spreads, or write custom Python strategies that are automatically discovered from <code style={{ padding: "2px 6px", background: "var(--color-neutral-subtle)", borderRadius: "4px" }}>engine/src/market_research_lab/custom_strategies/</code>.
        </Text>
      </VStack>

      {statusMessage && (
        <Banner status={statusMessage.type === "error" ? "error" : statusMessage.type === "success" ? "success" : "info"}>
          {statusMessage.text}
        </Banner>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Left Column: Parameter Configuration */}
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
              />
              {selectedStrategy && (
                <Text type="supporting">{selectedStrategy.description}</Text>
              )}

              <HStack gap={2} style={{ marginTop: "8px" }}>
                <Badge variant="primary">{selectedStrategyName.startsWith("custom_") ? "Custom Plugin" : "Built-in Strategy"}</Badge>
              </HStack>
            </VStack>
          </Card>

          <Card style={{ padding: "20px" }}>
            <VStack gap={3}>
              <Text weight="bold" size="lg">2. Strategy Parameters</Text>
              {selectedStrategy?.parameters.map((param) => (
                <VStack key={param.name} gap={1}>
                  <TextInput
                    label={`${param.name} (${param.param_type})`}
                    value={String(parameters[param.name] ?? param.default ?? "")}
                    onChange={(val) => {
                      const numVal = param.param_type === "int" ? parseInt(String(val), 10) : param.param_type === "float" ? parseFloat(String(val)) : val;
                      setParameters((prev) => ({ ...prev, [param.name]: numVal }));
                    }}
                    description={param.description}
                  />
                </VStack>
              ))}
            </VStack>
          </Card>

          <Card style={{ padding: "20px" }}>
            <VStack gap={3}>
              <Text weight="bold" size="lg">3. Test Target & Dataset</Text>
              <TextInput
                label="Underlying Symbol"
                value={symbol}
                onChange={(val) => setSymbol(String(val ?? "").toUpperCase())}
                placeholder="e.g. SPY, AAPL"
              />
              <Selector
                label="Dataset Version"
                options={datasetVersions.map((v) => ({ value: v, label: v }))}
                value={selectedDataset}
                onChange={(val) => setSelectedDataset(val)}
              />

              <HStack gap={2} style={{ marginTop: "12px" }}>
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

        {/* Right Column: Custom Strategy Python Extensibility Guide & Evaluation Results */}
        <VStack gap={4}>
          <Card style={{ padding: "20px" }}>
            <VStack gap={3}>
              <HStack justify="space-between" align="center">
                <Text weight="bold" size="lg">Extensibility: Add Custom Strategy</Text>
                <Button
                  label={copied ? "Copied!" : "Copy Python Template"}
                  variant="secondary"
                  size="sm"
                  onClick={handleCopyTemplate}
                />
              </HStack>
              <Text type="supporting">
                Drop any Python file into <code style={{ padding: "2px 6px", background: "var(--color-neutral-subtle)", borderRadius: "4px" }}>engine/src/market_research_lab/custom_strategies/</code>. The engine automatically discovers it and creates dynamic form inputs for its parameters!
              </Text>
              <pre
                style={{
                  backgroundColor: "#0d1117",
                  color: "#e6edf3",
                  padding: "16px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  overflowX: "auto",
                  maxHeight: "340px",
                  lineHeight: "1.4",
                }}
              >
                <code>{templateCode || "# Loading template..."}</code>
              </pre>
            </VStack>
          </Card>

          {evaluationResult && (
            <Card style={{ padding: "20px" }}>
              <VStack gap={3}>
                <Text weight="bold" size="lg">Evaluation Results</Text>
                <Text type="supporting">
                  Strategy: <strong>{evaluationResult.strategy_name}</strong> | Decision Time: <strong>{evaluationResult.decision_time}</strong>
                </Text>
                <div style={{ maxHeight: "200px", overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--color-border-subtle)", textAlign: "left" }}>
                        <th style={{ padding: "6px" }}>Security</th>
                        <th style={{ padding: "6px" }}>Weight</th>
                        <th style={{ padding: "6px" }}>Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluationResult.targets.map((t, idx) => (
                        <tr key={idx} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                          <td style={{ padding: "6px" }}>{t.security_id}</td>
                          <td style={{ padding: "6px" }}>{(t.weight * 100).toFixed(0)}%</td>
                          <td style={{ padding: "6px" }}>{t.rationale}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </VStack>
            </Card>
          )}
        </VStack>
      </div>
    </VStack>
  );
}
