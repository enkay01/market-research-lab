import { useEffect, useState } from "react";
import {
  Button,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  Text,
  VStack,
} from "@astryxdesign/core";
import { PrototypeSwitcher, type DesignVariant } from "../../components/PrototypeSwitcher";
import { Design1_QuantMultiPane } from "./Design1_QuantMultiPane";
import { Design2_CandlestickMaster } from "./Design2_CandlestickMaster";
import { Design3_HybridSplitCanvas } from "./Design3_HybridSplitCanvas";
import { Design4_GanttLifecycleMatrix } from "./Design4_GanttLifecycleMatrix";
import { Design5_DenseLedgerTearsheet } from "./Design5_DenseLedgerTearsheet";

interface OptionsDesignsPrototypeProps {
  onBackToStandard?: () => void;
}

export function OptionsDesignsPrototype({ onBackToStandard }: OptionsDesignsPrototypeProps) {
  const [variant, setVariant] = useState<DesignVariant>(() => {
    const params = new URLSearchParams(window.location.search);
    const v = params.get("variant");
    if (v === "1" || v === "2" || v === "3" || v === "4" || v === "5") {
      return v;
    }
    return "1";
  });

  const handleVariantChange = (newVar: DesignVariant) => {
    setVariant(newVar);
    const url = new URL(window.location.href);
    url.searchParams.set("variant", newVar);
    window.history.replaceState({}, "", url.toString());
  };

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const v = params.get("variant");
      if (v === "1" || v === "2" || v === "3" || v === "4" || v === "5") {
        setVariant(v);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={2}>
              <Heading level={2} style={{ fontSize: "18px", fontWeight: "bold", margin: 0 }}>
                Options Credit Spread Simulation
              </Heading>
              <Text size="sm" type="supporting" style={{ color: "#8b949e" }}>
                (Design {variant} of 5)
              </Text>
            </HStack>
            {onBackToStandard && (
              <Button
                label="Multi-Asset Backtest"
                variant="secondary"
                size="sm"
                onClick={onBackToStandard}
              />
            )}
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={3} isScrollable>
          <VStack gap={4} style={{ paddingBottom: "80px" }}>
            {variant === "1" && <Design1_QuantMultiPane />}
            {variant === "2" && <Design2_CandlestickMaster />}
            {variant === "3" && <Design3_HybridSplitCanvas />}
            {variant === "4" && <Design4_GanttLifecycleMatrix />}
            {variant === "5" && <Design5_DenseLedgerTearsheet />}
          </VStack>
          <PrototypeSwitcher current={variant} onChange={handleVariantChange} />
        </LayoutContent>
      }
    />
  );
}
