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
  TextInput,
  TextArea,
  Banner,
  EmptyState,
} from "@astryxdesign/core";
import type { Project } from "../api/client";

interface SecurityItem {
  id: string;
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  thesisUpdated?: string;
  thesisPreview?: string;
}

interface ResearchViewProps {
  project?: Project;
}

const SAMPLE_SECURITIES: SecurityItem[] = [
  {
    id: "sec-aapl",
    symbol: "AAPL",
    name: "Apple Inc.",
    exchange: "NASDAQ",
    currency: "USD",
    thesisUpdated: "2026-08-10",
    thesisPreview: "High ecosystem lock-in and growing services margin offset hardware cyclicality.",
  },
  {
    id: "sec-msft",
    symbol: "MSFT",
    name: "Microsoft Corporation",
    exchange: "NASDAQ",
    currency: "USD",
    thesisUpdated: "2026-08-08",
    thesisPreview: "Enterprise cloud scale and recurring SaaS cash flow support valuation.",
  },
  {
    id: "sec-spy",
    symbol: "SPY",
    name: "SPDR S&P 500 ETF Trust",
    exchange: "NYSE Arca",
    currency: "USD",
  },
];

export function ResearchView({ project }: ResearchViewProps) {
  const [watchlist, setWatchlist] = useState<SecurityItem[]>(SAMPLE_SECURITIES);
  const [selectedSecurity, setSelectedSecurity] = useState<SecurityItem | null>(SAMPLE_SECURITIES[0]);
  const [searchQuery, setSearchQuery] = useState("");
  const [thesisContent, setThesisContent] = useState(
    `# Investment Thesis: AAPL\n\n## Summary\nStrong pricing power and high-margin services segment.\n\n## Evidence\n- Services revenue expanded 12% YoY.\n- Installed base exceeds 2.2B active devices.\n\n## Risks\n- Greater China sales pressure.\n- Antitrust scrutiny on App Store fees.\n\n## Catalysts\n- On-device AI feature adoption.\n- Share repurchase acceleration.`,
  );
  const [isSaved, setIsSaved] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");

  const filteredSecurities = watchlist.filter(
    (s) =>
      s.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  function handleAddSymbol() {
    if (!newSymbol.trim()) return;
    const symbolClean = newSymbol.trim().toUpperCase();
    if (watchlist.some((s) => s.symbol === symbolClean)) return;

    const newItem: SecurityItem = {
      id: `sec-${symbolClean.toLowerCase()}`,
      symbol: symbolClean,
      name: `${symbolClean} Corporation`,
      exchange: "US",
      currency: "USD",
    };
    setWatchlist((prev) => [newItem, ...prev]);
    setSelectedSecurity(newItem);
    setNewSymbol("");
    setThesisContent(`# Investment Thesis: ${symbolClean}\n\n## Summary\nState your thesis summary here.\n\n## Evidence\n- Key evidence points.\n\n## Risks\n- Key investment risks.\n\n## Catalysts\n- Forward catalysts.`);
  }

  function handleSaveThesis() {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>
                Security Research & Watchlist
              </Heading>
              <Badge label={`${watchlist.length} Watched`} variant="purple" />
              {project && (
                <Token label={`Project: ${project.name}`} color="blue" />
              )}
            </HStack>

            <HStack gap={2}>
              <TextInput
                label="Search symbol or name"
                isLabelHidden
                placeholder="Search symbol or name…"
                value={searchQuery}
                onChange={(val) => setSearchQuery(typeof val === "string" ? val : "")}
                width={200}
              />
              <TextInput
                label="Add ticker"
                isLabelHidden
                placeholder="Add ticker (e.g. NVDA)"
                value={newSymbol}
                onChange={(val) => setNewSymbol(typeof val === "string" ? val : "")}
                width={160}
              />
              <Button
                label="Add to Watchlist"
                variant="primary"
                size="sm"
                onClick={handleAddSymbol}
                isDisabled={!newSymbol.trim()}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={0} isScrollable>
          {filteredSecurities.length === 0 ? (
            <EmptyState
              title="No Securities Found"
              description="No securities match your search query or watchlist."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Symbol</TableHeaderCell>
                  <TableHeaderCell>Company / Name</TableHeaderCell>
                  <TableHeaderCell>Exchange</TableHeaderCell>
                  <TableHeaderCell>Currency</TableHeaderCell>
                  <TableHeaderCell>Thesis Status</TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSecurities.map((item) => {
                  const isSelected = selectedSecurity?.id === item.id;
                  return (
                    <TableRow
                      key={item.id}
                      onClick={() => setSelectedSecurity(item)}
                      style={{
                        cursor: "pointer",
                        backgroundColor: isSelected
                          ? "var(--color-background-wash, rgba(255, 255, 255, 0.08))"
                          : undefined,
                      }}
                    >
                      <TableCell>
                        <Text weight="bold">{item.symbol}</Text>
                      </TableCell>
                      <TableCell>{item.name}</TableCell>
                      <TableCell>
                        <Token label={item.exchange} color="gray" />
                      </TableCell>
                      <TableCell>{item.currency}</TableCell>
                      <TableCell>
                        {item.thesisUpdated ? (
                          <Token label={`Thesis Active (${item.thesisUpdated})`} color="green" />
                        ) : (
                          <Token label="Draft Pending" color="gray" />
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          label="Remove"
                          variant="secondary"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setWatchlist((prev) => prev.filter((s) => s.id !== item.id));
                            if (selectedSecurity?.id === item.id) {
                              setSelectedSecurity(null);
                            }
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </LayoutContent>
      }
      end={
        <LayoutPanel
          width={450}
          hasDivider
          isScrollable
          label="Research Thesis"
        >
          {selectedSecurity ? (
            <VStack gap={4} style={{ padding: "16px" }}>
              <HStack justify="between" align="center">
                <VStack gap={0}>
                  <Heading level={3}>
                    {selectedSecurity.symbol} — {selectedSecurity.name}
                  </Heading>
                  <Text type="supporting">
                    {selectedSecurity.exchange} · {selectedSecurity.currency}
                  </Text>
                </VStack>
                <Button label="Save Thesis" variant="primary" size="sm" onClick={handleSaveThesis} />
              </HStack>

              {isSaved && (
                <Banner status="success" title="Thesis Saved">
                  Research thesis updated and persisted to project file.
                </Banner>
              )}

              <VStack gap={1}>
                <Text weight="semibold">
                  Markdown Research Thesis
                </Text>
                <TextArea
                  label="Markdown Thesis Text"
                  isLabelHidden
                  value={thesisContent}
                  onChange={(val) => setThesisContent(typeof val === "string" ? val : "")}
                  rows={14}
                />
              </VStack>

              <VStack gap={2}>
                <Text weight="semibold">
                  Linked Models & Valuations
                </Text>
                <Table>
                  <TableBody>
                    <TableRow>
                      <TableCell><Text weight="medium">FCFF DCF Valuation</Text></TableCell>
                      <TableCell><Token label="v1 (Base Case)" color="blue" /></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="medium">Trading Comparables</Text></TableCell>
                      <TableCell><Token label="v1 (Peer Median)" color="blue" /></TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><Text weight="medium">Moving Avg Strategy</Text></TableCell>
                      <TableCell><Token label="Ready" color="gray" /></TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </VStack>
            </VStack>
          ) : (
            <EmptyState
              title="Select a Security"
              description="Click a security in your watchlist to view and edit its Research Thesis."
            />
          )}
        </LayoutPanel>
      }
    />
  );
}
