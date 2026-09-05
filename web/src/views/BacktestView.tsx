import { useState } from "react";
import {
  Button,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  Token,
} from "@astryxdesign/core";
import { type Project } from "../api/client";
import { OptionsBacktestView } from "./OptionsBacktestView";
import { UnifiedWorkbench } from "./UnifiedWorkbench";

interface BacktestViewProps {
  project?: Project;
}

export function BacktestView({ project }: BacktestViewProps) {
  const [simulationType, setSimulationType] = useState<"verdict" | "options">(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("mode") === "options" ? "options" : "verdict";
  });

  if (simulationType === "options") {
    return (
      <OptionsBacktestView
        project={project}
        onBack={() => setSimulationType("verdict")}
      />
    );
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Strategy Evaluation &amp; Verdict Lab</Heading>
              {project && <Token label={`Project: ${project.name}`} color="purple" />}
              <Token label="Gate 1 Foundation" color="blue" />
            </HStack>

            <HStack gap={2}>
              <Button
                label="Options Credit Spreads (Alpaca)"
                variant="secondary"
                size="sm"
                onClick={() => setSimulationType("options")}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <UnifiedWorkbench project={project} />
        </LayoutContent>
      }
    />
  );
}
