import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Banner,
  Button,
  Dialog,
  DialogHeader,
  EmptyState,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  LayoutPanel,
  Markdown,
  SegmentedControl,
  SegmentedControlItem,
  Selector,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  TextArea,
  TextInput,
  Token,
  VStack,
} from "@astryxdesign/core";
import {
  api,
  type Project,
  type Security,
  type SecuritySummary,
  type WatchlistItem,
} from "../api/client";

interface ResearchViewProps {
  project?: Project;
  focusSecurityId?: string | null;
}

export function ResearchView({ project, focusSecurityId }: ResearchViewProps) {
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([]);
  const [selectedSecurityId, setSelectedSecurityId] = useState<string | null>(null);
  const [selectedSecurity, setSelectedSecurity] = useState<Security | null>(null);
  const [securitySummary, setSecuritySummary] = useState<SecuritySummary | null>(null);
  const [thesisContent, setThesisContent] = useState<string>("");
  const [thesisUpdatedAt, setThesisUpdatedAt] = useState<string | null>(null);
  const [thesisMode, setThesisMode] = useState<"edit" | "preview">("edit");

  // Filters & Sorting state (RES-006)
  const [searchQuery, setSearchQuery] = useState("");
  const [exchangeFilter, setExchangeFilter] = useState("all");
  const [thesisFilter, setThesisFilter] = useState("all");
  const [sortBy, setSortBy] = useState<"symbol" | "name" | "exchange" | "thesis_updated_at">("symbol");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  // Loading & error states
  const [isLoadingWatchlist, setIsLoadingWatchlist] = useState(false);
  const [isSavingThesis, setIsSavingThesis] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Add Security Dialog state
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [addSearchQuery, setAddSearchQuery] = useState("");
  const [catalogueResults, setCatalogueResults] = useState<Security[]>([]);
  const [isSearchingCatalogue, setIsSearchingCatalogue] = useState(false);
  const [isAddingSecurity, setIsAddingSecurity] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Dynamic exchange options (RES-006)
  const exchangeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const item of watchlistItems) {
      if (item.security.exchange) {
        set.add(item.security.exchange);
      }
    }
    return [
      { value: "all", label: "All Exchanges" },
      ...Array.from(set).map((ex) => ({ value: ex, label: ex })),
    ];
  }, [watchlistItems]);

  // Focus a Security opened from another view, such as an Alert link
  useEffect(() => {
    if (focusSecurityId) {
      setSelectedSecurityId(focusSecurityId);
    }
  }, [focusSecurityId]);

  // Fetch watchlist when project or filters change
  useEffect(() => {
    if (!project) {
      setWatchlistItems([]);
      setSelectedSecurityId(null);
      return;
    }

    let isMounted = true;
    setIsLoadingWatchlist(true);

    api
      .getWatchlist(project.id, {
        query: searchQuery || undefined,
        exchange: exchangeFilter !== "all" ? exchangeFilter : undefined,
        thesis_status: thesisFilter !== "all" ? thesisFilter : undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: 100,
      })
      .then((res) => {
        if (!isMounted) return;
        setWatchlistItems(res.items);
        if (focusSecurityId) {
          // An Alert-linked Security owns the selection; leave it in place.
          return;
        }
        // Select first if current selection is invalid
        if (res.items.length > 0) {
          if (!selectedSecurityId || !res.items.some((i) => i.security.security_id === selectedSecurityId)) {
            setSelectedSecurityId(res.items[0].security.security_id);
            setSelectedSecurity(res.items[0].security);
          }
        } else {
          setSelectedSecurityId(null);
          setSelectedSecurity(null);
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        console.error("Failed to load watchlist:", err);
      })
      .finally(() => {
        if (isMounted) setIsLoadingWatchlist(false);
      });

    return () => {
      isMounted = false;
    };
  }, [project, searchQuery, exchangeFilter, thesisFilter, sortBy, sortOrder, focusSecurityId]);

  // Load selected security details and research thesis
  useEffect(() => {
    if (!project || !selectedSecurityId) {
      setSecuritySummary(null);
      setThesisContent("");
      setThesisUpdatedAt(null);
      return;
    }

    let isMounted = true;

    // Details and thesis load independently: a Security opened from an Alert
    // may not be watched yet, so a missing thesis must not hide its data.
    void api
      .getSecurityDetails(selectedSecurityId, { project_id: project.id })
      .then((summary) => {
        if (!isMounted) return;
        setSecuritySummary(summary);
        setSelectedSecurity(summary.security);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        console.error("Failed to load security details:", err);
      });

    void api
      .getThesis(project.id, selectedSecurityId)
      .then((thesis) => {
        if (!isMounted) return;
        setThesisContent(thesis.content);
        setThesisUpdatedAt(thesis.updated_at ?? null);
      })
      .catch(() => {
        if (!isMounted) return;
        setThesisContent("");
        setThesisUpdatedAt(null);
      });

    return () => {
      isMounted = false;
    };
  }, [project, selectedSecurityId]);

  // Search catalogue when add dialog query changes
  useEffect(() => {
    if (!isAddDialogOpen) return;

    let isMounted = true;
    setIsSearchingCatalogue(true);

    api
      .listSecurities({ query: addSearchQuery || undefined, limit: 20 })
      .then((res) => {
        if (!isMounted) return;
        setCatalogueResults(res);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        console.error("Failed to search catalogue:", err);
      })
      .finally(() => {
        if (isMounted) setIsSearchingCatalogue(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isAddDialogOpen, addSearchQuery]);

  async function handleAddSecurity(identifier: string) {
    if (!project || !identifier.trim()) return;

    setIsAddingSecurity(true);
    setAddError(null);

    try {
      const updated = await api.addToWatchlist(project.id, {
        identifier: identifier.trim(),
      });
      setWatchlistItems(updated.items);
      setIsAddDialogOpen(false);
      setAddSearchQuery("");
      const matched = updated.items.find(
        (i) =>
          i.security.symbol.toUpperCase() === identifier.trim().toUpperCase() ||
          i.security.security_id === identifier.trim(),
      );
      if (matched) {
        setSelectedSecurityId(matched.security.security_id);
        setSelectedSecurity(matched.security);
      }
    } catch (err: unknown) {
      setAddError(
        err instanceof Error
          ? err.message
          : `Security '${identifier}' was not found in the local catalogue.`,
      );
    } finally {
      setIsAddingSecurity(false);
    }
  }

  async function handleRemoveSecurity(securityId: string) {
    if (!project) return;

    try {
      const updated = await api.removeFromWatchlist(project.id, securityId);
      setWatchlistItems(updated.items);
      if (selectedSecurityId === securityId) {
        if (updated.items.length > 0) {
          setSelectedSecurityId(updated.items[0].security.security_id);
          setSelectedSecurity(updated.items[0].security);
        } else {
          setSelectedSecurityId(null);
          setSelectedSecurity(null);
        }
      }
    } catch (err: unknown) {
      console.error("Failed to remove security from watchlist:", err);
    }
  }

  async function handleSaveThesis() {
    if (!project || !selectedSecurityId) return;

    setIsSavingThesis(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const updated = await api.saveThesis(project.id, selectedSecurityId, {
        content: thesisContent,
      });
      setThesisContent(updated.content);
      setThesisUpdatedAt(updated.updated_at ?? null);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);

      // Refresh watchlist item status token
      setWatchlistItems((prev) =>
        prev.map((item) =>
          item.security.security_id === selectedSecurityId
            ? {
                ...item,
                has_thesis: true,
                thesis_updated_at: updated.updated_at,
                thesis_preview: updated.summary || undefined,
              }
            : item,
        ),
      );
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Failed to save research thesis.");
    } finally {
      setIsSavingThesis(false);
    }
  }

  function toggleSort(field: "symbol" | "name" | "exchange" | "thesis_updated_at") {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder("asc");
    }
  }

  if (!project) {
    return (
      <EmptyState
        title="No Project Selected"
        description="Select or create a Project to view and manage watchlists and research theses."
      />
    );
  }

  return (
    <>
      <Layout
        height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Security Research & Watchlist</Heading>
              <Badge label={String(watchlistItems.length)} variant="purple" />
              <Token label={`Project: ${project.name}`} color="blue" />
            </HStack>

            <HStack gap={2} align="center">
              <TextInput
                label="Search symbol or name"
                isLabelHidden
                placeholder="Filter watchlist…"
                value={searchQuery}
                onChange={(val) => setSearchQuery(typeof val === "string" ? val : "")}
                width={180}
              />
              <Selector
                label="Exchange"
                isLabelHidden
                options={exchangeOptions}
                value={exchangeFilter}
                onChange={(val) => setExchangeFilter(val)}
                width={140}
              />
              <Selector
                label="Thesis Status"
                isLabelHidden
                options={[
                  { value: "all", label: "All Theses" },
                  { value: "has_thesis", label: "Has Thesis" },
                  { value: "no_thesis", label: "No Thesis" },
                ]}
                value={thesisFilter}
                onChange={(val) => setThesisFilter(val)}
                width={130}
              />
              <Button
                label="+ Add Security"
                variant="primary"
                size="sm"
                onClick={() => setIsAddDialogOpen(true)}
              />
            </HStack>
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent padding={0} isScrollable>
          {isLoadingWatchlist && watchlistItems.length === 0 ? (
            <VStack align="center" justify="center" style={{ minHeight: "var(--spacing-32, 200px)" }}>
              <Spinner label="Loading watchlist…" />
            </VStack>
          ) : watchlistItems.length === 0 ? (
            <EmptyState
              title="No Watched Securities"
              description={
                searchQuery || exchangeFilter !== "all" || thesisFilter !== "all"
                  ? "No securities match the selected filters."
                  : "Add securities to your project watchlist to start research and valuation."
              }
              actions={
                <Button
                  label="Add Security to Watchlist"
                  variant="primary"
                  onClick={() => setIsAddDialogOpen(true)}
                />
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell onClick={() => toggleSort("symbol")} style={{ cursor: "pointer" }}>
                    <HStack align="center" gap={1}>
                      <Text weight="semibold">Symbol</Text>
                      {sortBy === "symbol" && <Text type="supporting">{sortOrder === "asc" ? "▲" : "▼"}</Text>}
                    </HStack>
                  </TableHeaderCell>
                  <TableHeaderCell onClick={() => toggleSort("name")} style={{ cursor: "pointer" }}>
                    <HStack align="center" gap={1}>
                      <Text weight="semibold">Company / Name</Text>
                      {sortBy === "name" && <Text type="supporting">{sortOrder === "asc" ? "▲" : "▼"}</Text>}
                    </HStack>
                  </TableHeaderCell>
                  <TableHeaderCell onClick={() => toggleSort("exchange")} style={{ cursor: "pointer" }}>
                    <HStack align="center" gap={1}>
                      <Text weight="semibold">Exchange</Text>
                      {sortBy === "exchange" && <Text type="supporting">{sortOrder === "asc" ? "▲" : "▼"}</Text>}
                    </HStack>
                  </TableHeaderCell>
                  <TableHeaderCell>Currency</TableHeaderCell>
                  <TableHeaderCell onClick={() => toggleSort("thesis_updated_at")} style={{ cursor: "pointer" }}>
                    <HStack align="center" gap={1}>
                      <Text weight="semibold">Thesis Status</Text>
                      {sortBy === "thesis_updated_at" && <Text type="supporting">{sortOrder === "asc" ? "▲" : "▼"}</Text>}
                    </HStack>
                  </TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {watchlistItems.map((item) => {
                  const isSelected = selectedSecurityId === item.security.security_id;
                  return (
                    <TableRow
                      key={item.security.security_id}
                      onClick={() => {
                        setSelectedSecurityId(item.security.security_id);
                        setSelectedSecurity(item.security);
                      }}
                      style={{
                        cursor: "pointer",
                        backgroundColor: isSelected
                          ? "var(--color-background-wash, rgba(255, 255, 255, 0.08))"
                          : undefined,
                      }}
                    >
                      <TableCell>
                        <Text weight="bold">{item.security.symbol}</Text>
                      </TableCell>
                      <TableCell>
                        <VStack gap={0}>
                          <Text>{item.security.name}</Text>
                          {item.thesis_preview && (
                            <Text type="supporting" isTruncated style={{ maxWidth: "var(--spacing-64, 280px)" }}>
                              {item.thesis_preview}
                            </Text>
                          )}
                        </VStack>
                      </TableCell>
                      <TableCell>
                        <Token label={item.security.exchange || "US"} color="gray" />
                      </TableCell>
                      <TableCell>{item.security.currency}</TableCell>
                      <TableCell>
                        {item.has_thesis ? (
                          <Token
                            label={`Thesis Active (${item.thesis_updated_at ? item.thesis_updated_at.split("T")[0] : "saved"})`}
                            color="green"
                          />
                        ) : (
                          <Token label="No Thesis" color="gray" />
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          label="Remove"
                          variant="secondary"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleRemoveSecurity(item.security.security_id);
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
        <LayoutPanel width={480} hasDivider isScrollable label="Security Detail & Thesis">
          {selectedSecurity ? (
            <VStack gap={4} style={{ padding: "var(--spacing-4, 16px)" }}>
              {/* Header */}
              <HStack justify="between" align="start">
                <VStack gap={0}>
                  <Heading level={3}>
                    {selectedSecurity.symbol} — {selectedSecurity.name}
                  </Heading>
                  <Text type="supporting">
                    {selectedSecurity.exchange || "US"} · {selectedSecurity.currency} · ID: {selectedSecurity.security_id}
                  </Text>
                </VStack>
                <Token label="Watched" color="purple" />
              </HStack>

              {/* Research Thesis Header & Controls */}
              <VStack gap={2}>
                <HStack justify="between" align="center">
                  <Text weight="semibold">Research Thesis</Text>
                  <HStack gap={2} align="center">
                    <SegmentedControl
                      value={thesisMode}
                      onChange={(val) => setThesisMode(val as "edit" | "preview")}
                      size="sm"
                    >
                      <SegmentedControlItem value="edit" label="Edit" />
                      <SegmentedControlItem value="preview" label="Preview" />
                    </SegmentedControl>
                    <Button
                      label="Save Thesis"
                      variant="primary"
                      size="sm"
                      onClick={handleSaveThesis}
                      isLoading={isSavingThesis}
                    />
                  </HStack>
                </HStack>

                {saveSuccess && (
                  <Banner status="success" title="Thesis Saved">
                    Research thesis saved to project research file.
                  </Banner>
                )}

                {saveError && (
                  <Banner status="error" title="Save Error">
                    {saveError}
                  </Banner>
                )}

                {thesisUpdatedAt && (
                  <Text type="supporting">
                    Last updated: {new Date(thesisUpdatedAt).toLocaleString()}
                  </Text>
                )}

                {thesisMode === "edit" ? (
                  <TextArea
                    label="Markdown Research Thesis"
                    isLabelHidden
                    value={thesisContent}
                    onChange={(val) => setThesisContent(typeof val === "string" ? val : "")}
                    rows={14}
                    placeholder="Enter thesis markdown with ## Summary, ## Evidence, ## Risks, ## Catalysts..."
                  />
                ) : (
                  <VStack
                    gap={2}
                    style={{
                      padding: "var(--spacing-3, 12px)",
                      borderRadius: "var(--radius-sm, 4px)",
                      backgroundColor: "var(--color-background-surface, rgba(255, 255, 255, 0.04))",
                      minHeight: "var(--spacing-48, 200px)",
                    }}
                  >
                    <Markdown autolink="gfm">{thesisContent || "_No thesis content written yet._"}</Markdown>
                  </VStack>
                )}
              </VStack>

              {/* Linked Market Data Availability (RES-005) */}
              <VStack gap={2}>
                <Text weight="semibold">Linked Market Datasets</Text>
                {securitySummary ? (
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell>
                          <Text weight="medium">Daily Bars</Text>
                        </TableCell>
                        <TableCell>
                          {securitySummary.daily_bars_count > 0 ? (
                            <VStack gap={0}>
                              <Text>
                                {securitySummary.daily_bars_count} bars ({securitySummary.daily_bars_start} to{" "}
                                {securitySummary.daily_bars_end})
                              </Text>
                              {securitySummary.latest_close !== null && (
                                <Text type="supporting">
                                  Latest Close: ${securitySummary.latest_close.toFixed(2)}
                                </Text>
                              )}
                            </VStack>
                          ) : (
                            <Text type="supporting">None</Text>
                          )}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>
                          <Text weight="medium">Corporate Actions</Text>
                        </TableCell>
                        <TableCell>
                          {securitySummary.corporate_actions_count > 0 ? (
                            <Text>{securitySummary.corporate_actions_count} actions</Text>
                          ) : (
                            <Text type="supporting">None</Text>
                          )}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>
                          <Text weight="medium">Fundamentals</Text>
                        </TableCell>
                        <TableCell>
                          {securitySummary.fundamentals_count > 0 ? (
                            <VStack gap={0}>
                              <Text>{securitySummary.fundamentals_count} facts</Text>
                              <Text type="supporting">
                                {securitySummary.fundamentals_fiscal_periods.join(", ")}
                              </Text>
                            </VStack>
                          ) : (
                            <Text type="supporting">None</Text>
                          )}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>
                          <Text weight="medium">Covering Datasets</Text>
                        </TableCell>
                        <TableCell>
                          {securitySummary.covering_dataset_versions.length > 0 ? (
                            <HStack gap={1} style={{ flexWrap: "wrap" }}>
                              {securitySummary.covering_dataset_versions.map((vid) => (
                                <Token key={vid} label={vid.slice(0, 8)} color="blue" />
                              ))}
                            </HStack>
                          ) : (
                            <Text type="supporting">No datasets covering this security</Text>
                          )}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                ) : (
                  <Text type="supporting">Loading market data availability…</Text>
                )}
              </VStack>

              {/* Downstream Valuations, Runs, & Alerts (RES-005) */}
              <VStack gap={2}>
                <Text weight="semibold">Downstream Models & Signals</Text>
                <Table>
                  <TableBody>
                    <TableRow>
                      <TableCell>
                        <Text weight="medium">Saved Valuations</Text>
                      </TableCell>
                      <TableCell>
                        {securitySummary?.valuations && securitySummary.valuations.length > 0 ? (
                          <VStack gap={1}>
                            {securitySummary.valuations.map((v, idx) => (
                              <Token
                                key={idx}
                                label={`${String(v.name || "Valuation")} (${String(v.revision || "draft")})`}
                                color="blue"
                              />
                            ))}
                          </VStack>
                        ) : (
                          <Text type="supporting">No Valuations saved yet</Text>
                        )}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>
                        <Text weight="medium">Backtest Runs</Text>
                      </TableCell>
                      <TableCell>
                        {securitySummary?.runs && securitySummary.runs.length > 0 ? (
                          <VStack gap={1}>
                            {securitySummary.runs.map((r, idx) => (
                              <Token
                                key={idx}
                                label={`Run ${String(r.id || "").slice(0, 8)} (${String(r.status || "pending")})`}
                                color="gray"
                              />
                            ))}
                          </VStack>
                        ) : (
                          <Text type="supporting">No Runs executed yet</Text>
                        )}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>
                        <Text weight="medium">Live Alerts</Text>
                      </TableCell>
                      <TableCell>
                        {securitySummary?.alerts && securitySummary.alerts.length > 0 ? (
                          <VStack gap={1}>
                            {securitySummary.alerts.map((a, idx) => (
                              <Token key={idx} label={String(a.name || "Alert")} color="yellow" />
                            ))}
                          </VStack>
                        ) : (
                          <Text type="supporting">No active alerts configured for this security</Text>
                        )}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </VStack>
            </VStack>
          ) : (
            <EmptyState
              title="Select a Security"
              description="Click a security in your watchlist to view its data linkage and edit its Research Thesis."
            />
          )}
        </LayoutPanel>
      }
    />
      {/* Add Security Dialog */}
      <Dialog
        isOpen={isAddDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setIsAddDialogOpen(false);
            setAddError(null);
          }
        }}
      >
        <DialogHeader
          title="Add Security to Watchlist"
          subtitle="Search available securities in the local Market Dataset catalogue."
        />
        <VStack gap={3} style={{ padding: "var(--spacing-4, 16px)" }}>
          {addError && (
            <Banner status="error" title="Catalogue Error">
              {addError}
            </Banner>
          )}

          <TextInput
            label="Search Catalogue"
            placeholder="Search symbol or name (e.g. AAPL, Apple, MSFT)…"
            value={addSearchQuery}
            onChange={(val) => setAddSearchQuery(typeof val === "string" ? val : "")}
            hasAutoFocus
          />

          <VStack gap={1} style={{ maxHeight: "var(--spacing-64, 240px)", overflowY: "auto" }}>
            {isSearchingCatalogue ? (
              <VStack align="center" style={{ padding: "var(--spacing-4, 16px)" }}>
                <Spinner label="Searching catalogue…" />
              </VStack>
            ) : catalogueResults.length === 0 ? (
              <Text type="supporting" style={{ padding: "var(--spacing-2, 8px)" }}>
                {addSearchQuery
                  ? "No matching securities found in catalogue. Ingest a dataset first to register securities."
                  : "Type a symbol or company name to search."}
              </Text>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Symbol</TableHeaderCell>
                    <TableHeaderCell>Name</TableHeaderCell>
                    <TableHeaderCell>Exchange</TableHeaderCell>
                    <TableHeaderCell>Action</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {catalogueResults.map((sec) => {
                    const isAlreadyWatched = watchlistItems.some(
                      (w) => w.security.security_id === sec.security_id,
                    );
                    return (
                      <TableRow key={sec.security_id}>
                        <TableCell>
                          <Text weight="bold">{sec.symbol}</Text>
                        </TableCell>
                        <TableCell>{sec.name}</TableCell>
                        <TableCell>
                          <Token label={sec.exchange || "US"} color="gray" />
                        </TableCell>
                        <TableCell>
                          {isAlreadyWatched ? (
                            <Token label="Watched" color="purple" />
                          ) : (
                            <Button
                              label="Add"
                              variant="primary"
                              size="sm"
                              isLoading={isAddingSecurity}
                              onClick={() => void handleAddSecurity(sec.symbol)}
                            />
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </VStack>

          <HStack justify="end" gap={2}>
            <Button
              label="Close"
              variant="secondary"
              onClick={() => setIsAddDialogOpen(false)}
            />
          </HStack>
        </VStack>
      </Dialog>
    </>
  );
}
