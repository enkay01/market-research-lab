"""Reporting and document export generators for Market Research Lab."""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass

from .json_types import JsonValue


@dataclass(frozen=True)
class ReportMetaInfo:
    title_symbol: str
    strategy_name: str
    strategy_rev: str
    run_id: str
    start_date: str
    end_date: str
    starting_cash: float
    schedule: str
    benchmark_id: str
    universe_list: list[str]
    dataset_version_list: list[str]


@dataclass(frozen=True)
class ExecutionAssumptionsInfo:
    spec: dict[str, JsonValue]
    execution: dict[str, JsonValue]
    universe_list: list[str]
    benchmark_id: str
    strategy_name: str
    strategy_rev: str
    price_field: str
    schedule: str

# ---------------------------------------------------------------------------
# Backtest HTML and CSV Exporters
# ---------------------------------------------------------------------------



def _render_html_header(title_symbol: str, strategy_name: str, strategy_rev: str) -> list[str]:
    return [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>Backtest Report — {title_symbol} ({strategy_name}:{strategy_rev})</title>",
        "  <style>",
        (
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,"
            " sans-serif; line-height: 1.5; color: #1e293b; max-width: 1040px; margin: 40px auto;"
            " padding: 0 20px; }"
        ),
        "    h1, h2, h3 { color: #0f172a; margin-top: 28px; }",
        (
            "    .meta { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;"
            " padding: 16px; margin-bottom: 24px; }"
        ),
        (
            "    .meta-grid { display: grid; grid-template-columns: repeat(auto-fit,"
            " minmax(220px, 1fr)); gap: 12px; }"
        ),
        (
            "    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit,"
            " minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }"
        ),
        (
            "    .metric-card { background: #f1f5f9; border-radius: 6px; padding: 12px 16px;"
            " border: 1px solid #e2e8f0; }"
        ),
        (
            "    .metric-value { font-size: 1.4rem; font-weight: 700; color: #0f172a;"
            " font-variant-numeric: tabular-nums; }"
        ),
        (
            "    .metric-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase;"
            " letter-spacing: 0.04em; }"
        ),
        (
            "    table { width: 100%; border-collapse: collapse; margin: 16px 0 24px;"
            " font-size: 0.9rem; }"
        ),
        (
            "    th, td { text-align: left; padding: 8px 10px;"
            " border-bottom: 1px solid #e2e8f0; }"
        ),
        (
            "    th { background: #f8fafc; font-weight: 600; color: #475569; position: sticky;"
            " top: 0; }"
        ),
        "    .num { text-align: right; font-variant-numeric: tabular-nums; }",
        (
            "    .warning { background: #fffbeb; border-left: 4px solid #f59e0b;"
            " padding: 12px 16px; margin: 16px 0; border-radius: 4px; }"
        ),
        (
            "    .rejection { background: #fef2f2; border-left: 4px solid #ef4444;"
            " padding: 12px 16px; margin: 16px 0; border-radius: 4px; }"
        ),
        (
            "    .badge { display: inline-block; background: #e0e7ff; color: #3730a3;"
            " padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin: 2px; }"
        ),
        "    .badge-bench { background: #fef3c7; color: #92400e; }",
        "    .badge-buy { background: #dcfce7; color: #166534; }",
        "    .badge-sell { background: #fef2f2; color: #991b1b; }",
        (
            "    .scroll-table { max-height: 400px; overflow-y: auto; border: 1px solid #e2e8f0;"
            " border-radius: 6px; margin-bottom: 24px; }"
        ),
        "  </style>",
        "</head>",
        "<body>",
    ]


def _render_meta_box(meta: ReportMetaInfo) -> list[str]:
    return [
        f"  <h1>Backtest Report: {meta.title_symbol} — {meta.strategy_name}</h1>",
        '  <div class="meta">',
        '    <div class="meta-grid">',
        f"      <div><strong>Strategy:</strong> {meta.strategy_name} ({meta.strategy_rev})</div>",
        f"      <div><strong>Run ID:</strong> {meta.run_id}</div>",
        f"      <div><strong>Simulation Range:</strong> {meta.start_date} to {meta.end_date}</div>",
        f"      <div><strong>Starting Cash:</strong> ${meta.starting_cash:,.2f} USD</div>",
        (
            "      <div><strong>Sample Status:</strong> Out-of-sample "
            "(Point-in-time sequential simulation)</div>"
        ),
        f"      <div><strong>Execution:</strong> Next-bar open ({meta.schedule})</div>",
        f"      <div><strong>Benchmark:</strong> {meta.benchmark_id if meta.benchmark_id else 'None'}</div>",
        "    </div>",
        '    <div style="margin-top: 12px;"><strong>Universe Securities:</strong> '
        + "".join(f'<span class="badge">{html.escape(str(s))}</span>' for s in meta.universe_list)
        + "    </div>",
        '    <div style="margin-top: 8px;"><strong>Dataset Versions:</strong> '
        + "".join(
            f'<span class="badge">{html.escape(str(ds))}</span>' for ds in meta.dataset_version_list
        )
        + "    </div>",
        "  </div>",
    ]


def _render_warnings_and_rejections(
    warnings: list[JsonValue],
    rejections: list[JsonValue],
) -> list[str]:
    doc: list[str] = []
    if warnings:
        doc.append('  <div class="warning"><strong>Warnings:</strong><ul>')
        for w in warnings:
            doc.append(f"    <li>{html.escape(str(w))}</li>")
        doc.append("  </ul></div>")

    if rejections:
        doc.append('  <div class="rejection"><strong>Constraint Rejections:</strong><ul>')
        for r in rejections:
            if isinstance(r, dict):
                r_date = r.get("session_date")
                r_sec = r.get("security_id")
                r_rule = r.get("rule")
                r_reason = html.escape(str(r.get("reason")))
                doc.append(
                    f"    <li><strong>{r_date}: {r_sec}</strong> [{r_rule}] {r_reason}</li>"
                )
            else:
                doc.append(f"    <li>{html.escape(str(r))}</li>")
        doc.append("  </ul></div>")
    return doc


def _render_performance_metrics_grid(metrics: dict[str, JsonValue]) -> list[str]:
    total_return = float(metrics.get("total_return", 0.0))
    ann_return = float(metrics.get("annualized_return", 0.0))
    ann_vol = float(metrics.get("annualized_volatility", 0.0))
    sharpe = float(metrics.get("sharpe_ratio", 0.0))
    sortino = float(metrics.get("sortino_ratio", 0.0))
    max_dd = float(metrics.get("max_drawdown", 0.0))
    calmar = float(metrics.get("calmar_ratio", 0.0))
    turnover = float(metrics.get("turnover", 0.0))
    gross_exp = float(metrics.get("gross_exposure", 0.0))
    net_exp = float(metrics.get("net_exposure", 0.0))
    hit_rate = metrics.get("hit_rate")
    bench_rel = metrics.get("benchmark_relative_return")
    num_trades = int(metrics.get("num_trades", 0))
    num_fills = int(metrics.get("num_fills", 0))

    hit_rate_str = f"{float(hit_rate) * 100:.1f}%" if hit_rate is not None else "—"
    bench_rel_str = f"{float(bench_rel) * 100:+.2f}%" if bench_rel is not None else "—"

    return [
        "  <h2>Performance Overview</h2>",
        '  <div class="metric-grid">',
        '    <div class="metric-card"><div class="metric-label">Total Return</div>'
        f'<div class="metric-value">{total_return * 100:+.2f}%</div></div>',
        '    <div class="metric-card"><div class="metric-label">Annualized Return</div>'
        f'<div class="metric-value">{ann_return * 100:+.2f}%</div></div>',
        '    <div class="metric-card"><div class="metric-label">Annual Volatility</div>'
        f'<div class="metric-value">{ann_vol * 100:.2f}%</div></div>',
        '    <div class="metric-card"><div class="metric-label">Sharpe Ratio</div>'
        f'<div class="metric-value">{sharpe:.2f}</div></div>',
        '    <div class="metric-card"><div class="metric-label">Sortino Ratio</div>'
        f'<div class="metric-value">{sortino:.2f}</div></div>',
        '    <div class="metric-card"><div class="metric-label">Max Drawdown</div>'
        f'<div class="metric-value">{max_dd * 100:.2f}%</div></div>',
        '    <div class="metric-card"><div class="metric-label">Calmar Ratio</div>'
        f'<div class="metric-value">{calmar:.2f}</div></div>',
        '    <div class="metric-card"><div class="metric-label">Hit Rate / Win Rate</div>'
        f'<div class="metric-value">{hit_rate_str}</div></div>',
        '    <div class="metric-card"><div class="metric-label">Turnover</div>'
        f'<div class="metric-value">{turnover:.2f}x</div></div>',
        '    <div class="metric-card"><div class="metric-label">Gross / Net Exposure</div>'
        f'<div class="metric-value">{gross_exp * 100:.0f}% / {net_exp * 100:.0f}%</div></div>',
        '    <div class="metric-card"><div class="metric-label">Benchmark Relative</div>'
        f'<div class="metric-value">{bench_rel_str}</div></div>',
        '    <div class="metric-card"><div class="metric-label">Trades / Fills</div>'
        f'<div class="metric-value">{num_trades} / {num_fills}</div></div>',
        "  </div>",
    ]


def _render_execution_assumptions_table(info: ExecutionAssumptionsInfo) -> list[str]:
    commission_rate = float(info.execution.get("commission_rate", 0.0))
    slippage_rate = float(info.execution.get("slippage_rate", 0.0))
    cash_interest_rate = float(info.execution.get("cash_interest_rate", 0.0))
    borrow_fee_rate = float(info.execution.get("borrow_fee_rate", 0.0))
    raw_unavail = info.execution.get("unavailable_borrow", [])
    unavailable_borrow = raw_unavail if isinstance(raw_unavail, list) else []
    max_leverage = float(info.execution.get("max_leverage", 1.0))
    margin_req = float(info.execution.get("margin_requirement", 1.0))
    maint_margin = float(info.execution.get("maintenance_margin", 0.25))
    leverage_mode = html.escape(str(info.execution.get("leverage_mode") or "reject"))

    doc = [
        "  <h2>Execution Model & Strategy Assumptions</h2>",
        "  <table>",
        '    <thead><tr><th>Parameter / Assumption</th><th class="num">Value</th></tr></thead>',
        "    <tbody>",
        '      <tr><td>Universe</td><td class="num">'
        f'{html.escape(", ".join(info.universe_list))}</td></tr>',
    ]
    if info.benchmark_id:
        doc.append(f'      <tr><td>Benchmark Security</td><td class="num">{info.benchmark_id}</td></tr>')
    doc.append(f'      <tr><td>Strategy</td><td class="num">{info.strategy_name}</td></tr>')
    doc.append(f'      <tr><td>Strategy Revision</td><td class="num">{info.strategy_rev}</td></tr>')
    doc.append(f'      <tr><td>Price Field</td><td class="num">{info.price_field}</td></tr>')
    doc.append(f'      <tr><td>Rebalance Schedule</td><td class="num">{info.schedule}</td></tr>')
    doc.append(
        '      <tr><td>Commission Rate</td><td class="num">'
        f'{commission_rate * 10000:.1f} bps ({commission_rate * 100:.3f}%)</td></tr>'
    )
    doc.append(
        '      <tr><td>Slippage Rate</td>'
        f'<td class="num">{slippage_rate * 10000:.1f} bps ({slippage_rate * 100:.3f}%)</td></tr>'
    )
    doc.append(
        '      <tr><td>Cash Interest Rate</td>'
        f'<td class="num">{cash_interest_rate * 10000:.1f} bps '
        f'({cash_interest_rate * 100:.3f}% p.a., signed)</td></tr>'
    )
    if borrow_fee_rate > 0.0:
        doc.append(
            '      <tr><td>Borrow Fee Rate</td>'
            f'<td class="num">{borrow_fee_rate * 10000:.1f} bps '
            f'({borrow_fee_rate * 100:.3f}% p.a.)</td></tr>'
        )
    if unavailable_borrow:
        unavail_str = html.escape(", ".join(str(u) for u in unavailable_borrow))
        doc.append(f'      <tr><td>Unavailable Borrow</td><td class="num">{unavail_str}</td></tr>')
    doc.append(
        '      <tr><td>Max Leverage Limit</td>'
        f'<td class="num">{max_leverage:.2f}x ({max_leverage * 100:.0f}% gross exposure)</td></tr>'
    )
    doc.append(f'      <tr><td>Margin Requirement</td><td class="num">{margin_req * 100:.1f}%</td></tr>')
    doc.append(f'      <tr><td>Maintenance Margin</td><td class="num">{maint_margin * 100:.1f}%</td></tr>')
    doc.append(f'      <tr><td>Leverage Constraint Mode</td><td class="num">{leverage_mode}</td></tr>')

    params_raw = info.spec.get("parameters")
    if isinstance(params_raw, dict):
        for k, v in sorted(params_raw.items()):
            doc.append(
                f'      <tr><td>Strategy Parameter: {html.escape(k)}</td>'
                f'<td class="num">{html.escape(str(v))}</td></tr>'
            )
    doc.append("    </tbody>")
    doc.append("  </table>")
    return doc


def _render_cost_attribution_table(
    costs: dict[str, JsonValue],
    portfolio_impact: dict[str, JsonValue],
) -> list[str]:
    doc = [
        "  <h2>Cost Attribution</h2>",
        "  <table>",
        '    <thead><tr><th>Category</th><th class="num">Amount</th>'
        '<th class="num">Portfolio Impact</th></tr></thead>',
        "    <tbody>",
    ]
    for label, key in (
        ("Commission", "total_commission"),
        ("Slippage", "total_slippage"),
        ("Borrow Fees", "total_borrow_fees"),
        ("Cash Interest", "total_cash_interest"),
    ):
        amount = float(costs.get(key, 0.0))
        impact_key = key.removeprefix("total_")
        impact = float(portfolio_impact.get(impact_key, 0.0))
        doc.append(
            f'      <tr><td>{label}</td><td class="num">${amount:+,.2f}</td>'
            f'<td class="num">${impact:+,.2f}</td></tr>'
        )
    net_costs = float(costs.get("total_costs", 0.0))
    net_impact = float(portfolio_impact.get("net", 0.0))
    doc.append(
        '      <tr><td><strong>Net Costs</strong></td>'
        f'<td class="num"><strong>${net_costs:+,.2f}</strong></td>'
        f'<td class="num"><strong>${net_impact:+,.2f}</strong></td></tr>'
    )
    doc.append("    </tbody>")
    doc.append("  </table>")
    return doc


def _render_closed_trades_table(trades: list[JsonValue]) -> list[str]:
    doc = [f"  <h2>Closed Trades ({len(trades)})</h2>"]
    if trades:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Trade ID</th><th>Security</th><th>Entry Date</th>'
            '<th>Exit Date</th><th class="num">Entry Price</th><th class="num">Exit Price</th>'
            '<th class="num">Quantity</th><th class="num">Costs</th><th class="num">PnL ($)</th>'
            '<th class="num">Return (%)</th></tr></thead>'
        )
        doc.append("      <tbody>")
        for tr in trades:
            if isinstance(tr, dict):
                pnl = float(tr.get("pnl", 0.0))
                ret_pct = float(tr.get("return_pct", 0.0))
                entry_cost = float(tr.get("entry_cost", 0.0))
                exit_proceeds = float(tr.get("exit_proceeds", 0.0))
                tr_id = html.escape(str(tr.get("trade_id")))
                tr_sec = html.escape(str(tr.get("security_id")))
                tr_en_date = tr.get("entry_date")
                tr_ex_date = tr.get("exit_date")
                tr_en_p = float(tr.get("entry_price", 0))
                tr_ex_p = float(tr.get("exit_price", 0))
                tr_qty = float(tr.get("quantity", 0))
                tr_costs = entry_cost - exit_proceeds + pnl
                pnl_color = "#166534" if pnl >= 0 else "#991b1b"
                ret_color = "#166534" if ret_pct >= 0 else "#991b1b"
                doc.append(
                    f'        <tr><td>{tr_id}</td><td><strong>{tr_sec}</strong></td>'
                    f'<td>{tr_en_date}</td><td>{tr_ex_date}</td>'
                    f'<td class="num">${tr_en_p:.2f}</td><td class="num">${tr_ex_p:.2f}</td>'
                    f'<td class="num">{tr_qty:.2f}</td><td class="num">${tr_costs:.2f}</td>'
                    f'<td class="num" style="color: {pnl_color};">'
                    f'<strong>${pnl:+,.2f}</strong></td>'
                    f'<td class="num" style="color: {ret_color};">{ret_pct * 100:+.2f}%</td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")
    else:
        doc.append("  <p><em>No round-trip trades completed during this Backtest run.</em></p>")
    return doc


def _render_fills_table(fills: list[JsonValue]) -> list[str]:
    doc = [f"  <h2>Simulated Execution Fills ({len(fills)})</h2>"]
    if fills:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Date</th><th>Side</th><th>Security</th>'
            '<th class="num">Quantity</th><th class="num">Fill Price</th>'
            '<th class="num">Notional</th><th class="num">Commission</th>'
            '<th class="num">Slippage</th><th>Rationale</th></tr></thead>'
        )
        doc.append("      <tbody>")
        for fill in fills:
            if isinstance(fill, dict):
                side = str(fill.get("side", "")).upper()
                badge_class = "badge-buy" if side == "BUY" else "badge-sell"
                f_date = fill.get("session_date")
                f_sec = html.escape(str(fill.get("security_id")))
                f_qty = float(fill.get("quantity", 0))
                f_p = float(fill.get("price", 0))
                f_not = float(fill.get("notional", 0))
                f_comm = float(fill.get("commission", 0))
                f_slip = float(fill.get("slippage_cost", 0))
                f_rat = html.escape(str(fill.get("rationale", "")))
                doc.append(
                    f'        <tr><td>{f_date}</td>'
                    f'<td><span class="badge {badge_class}">{side}</span></td>'
                    f'<td><strong>{f_sec}</strong></td><td class="num">{f_qty:.2f}</td>'
                    f'<td class="num">${f_p:.2f}</td><td class="num">${f_not:,.2f}</td>'
                    f'<td class="num">${f_comm:.2f}</td><td class="num">${f_slip:.2f}</td>'
                    f'<td><small>{f_rat}</small></td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")
    else:
        doc.append("  <p><em>No fills occurred during this Backtest run.</em></p>")
    return doc


def _render_ledger_table(ledger: list[JsonValue]) -> list[str]:
    doc = [f"  <h2>Daily Mark-to-Market Ledger ({len(ledger)} sessions)</h2>"]
    if ledger:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Session Date</th><th class="num">Target Weight</th>'
            '<th>Positions Breakdown</th><th class="num">Cash Balance</th>'
            '<th class="num">Position Value</th><th class="num">Portfolio Value</th>'
            '<th class="num">Gross Exp</th><th class="num">Net Exp</th>'
            '<th class="num">Borrow Fees</th><th class="num">Cash Interest</th></tr></thead>'
        )
        doc.append("      <tbody>")
        for row in ledger:
            if isinstance(row, dict):
                weight = row.get("signal_weight")
                weight_str = (
                    f"{float(weight) * 100:.0f}%"
                    if weight is not None and isinstance(weight, (int, float))
                    else "—"
                )
                raw_positions = row.get("positions")
                positions_dict = raw_positions if isinstance(raw_positions, dict) else {}
                if positions_dict:
                    pos_parts = []
                    for sym, pos_data in positions_dict.items():
                        if isinstance(pos_data, dict):
                            sh = float(pos_data.get("shares", 0))
                            val = float(pos_data.get("position_value", 0))
                            pos_parts.append(f"{html.escape(sym)}: {sh:.2f} sh (${val:,.2f})")
                    pos_summary = "<br>".join(pos_parts) if pos_parts else "Flat"
                else:
                    shares_held = float(row.get("shares", 0))
                    pos_summary = f"{shares_held:.2f} sh" if abs(shares_held) > 0.0001 else "Flat"

                r_date = row.get("session_date")
                r_cash = float(row.get("cash", 0))
                r_pval = float(row.get("position_value", 0))
                r_port = float(row.get("portfolio_value", 0))
                gross_exp = float(row.get("gross_exposure", 0))
                net_exp = float(row.get("net_exposure", 0))
                borrow_fee = float(row.get("borrow_fees", 0.0))
                cash_interest = float(row.get("cash_interest", 0.0))
                doc.append(
                    f'        <tr><td>{r_date}</td><td class="num">{weight_str}</td>'
                    f'<td><small>{pos_summary}</small></td>'
                    f'<td class="num">${r_cash:,.2f}</td><td class="num">${r_pval:,.2f}</td>'
                    f'<td class="num"><strong>${r_port:,.2f}</strong></td>'
                    f'<td class="num">{gross_exp * 100:.0f}%</td>'
                    f'<td class="num">{net_exp * 100:.0f}%</td>'
                    f'<td class="num">${borrow_fee:,.2f}</td>'
                    f'<td class="num">${cash_interest:+,.2f}</td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")
    return doc


def generate_backtest_html_report(
    result_data: dict[str, JsonValue],
    manifest_data: dict[str, JsonValue],
) -> str:
    """Generate a self-contained, human-readable HTML Backtest report."""
    spec_raw = result_data.get("specification")
    spec = spec_raw if isinstance(spec_raw, dict) else {}
    strategy_name = html.escape(str(spec.get("strategy_name") or "unnamed_strategy"))
    strategy_rev = html.escape(
        str(
            result_data.get("strategy_revision")
            or spec.get("strategy_revision")
            or manifest_data.get("definition_revisions", [""])[0]
            or "v1"
        )
    )
    run_id = html.escape(str(result_data.get("run_id") or manifest_data.get("id") or "N/A"))
    security_id = html.escape(str(spec.get("security_id") or "N/A"))
    start_date = html.escape(str(spec.get("start_date") or ""))
    end_date = html.escape(str(spec.get("end_date") or ""))
    starting_cash = float(spec.get("starting_cash", 100000.0))

    exec_raw = spec.get("execution")
    execution = exec_raw if isinstance(exec_raw, dict) else {}
    schedule = html.escape(str(execution.get("schedule") or "daily"))
    price_field = html.escape(str(spec.get("price_field") or "close"))

    dataset_versions = manifest_data.get("dataset_versions")
    if not dataset_versions:
        dataset_versions = (
            [spec.get("dataset_version_id")] if spec.get("dataset_version_id") else []
        )
    dataset_version_list = (
        dataset_versions if isinstance(dataset_versions, list) else [str(dataset_versions)]
    )

    universe_raw = spec.get("universe") or manifest_data.get("universe")
    if not universe_raw:
        universe_raw = [security_id] if security_id and security_id != "N/A" else []
    universe_list = universe_raw if isinstance(universe_raw, list) else [str(universe_raw)]
    benchmark_id = html.escape(
        str(spec.get("benchmark_security_id") or manifest_data.get("benchmark_security_id") or "")
    )

    raw_warnings = result_data.get("warnings")
    warnings = raw_warnings if isinstance(raw_warnings, list) else []

    raw_rejections = result_data.get("rejections")
    rejections = raw_rejections if isinstance(raw_rejections, list) else []

    metrics_raw = result_data.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}

    result_manifest_raw = result_data.get("manifest")
    result_manifest = result_manifest_raw if isinstance(result_manifest_raw, dict) else {}
    costs_raw = result_manifest.get("costs")
    costs = costs_raw if isinstance(costs_raw, dict) else {}
    portfolio_impact_raw = costs.get("portfolio_impact")
    portfolio_impact = portfolio_impact_raw if isinstance(portfolio_impact_raw, dict) else {}

    universe_display = ", ".join(universe_list) if universe_list else security_id
    title_symbol = (
        universe_display
        if len(universe_list) <= 3
        else f"{universe_list[0]} +{len(universe_list) - 1} more"
    )

    doc: list[str] = []
    doc.extend(_render_html_header(title_symbol, strategy_name, strategy_rev))
    meta_info = ReportMetaInfo(
        title_symbol=title_symbol,
        strategy_name=strategy_name,
        strategy_rev=strategy_rev,
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        starting_cash=starting_cash,
        schedule=schedule,
        benchmark_id=benchmark_id,
        universe_list=universe_list,
        dataset_version_list=dataset_version_list,
    )
    doc.extend(_render_meta_box(meta_info))
    doc.extend(_render_warnings_and_rejections(warnings, rejections))
    doc.extend(_render_performance_metrics_grid(metrics))
    exec_info = ExecutionAssumptionsInfo(
        spec=spec,
        execution=execution,
        universe_list=universe_list,
        benchmark_id=benchmark_id,
        strategy_name=strategy_name,
        strategy_rev=strategy_rev,
        price_field=price_field,
        schedule=schedule,
    )
    doc.extend(_render_execution_assumptions_table(exec_info))
    doc.extend(_render_cost_attribution_table(costs, portfolio_impact))

    raw_trades = result_data.get("trades")
    trades = raw_trades if isinstance(raw_trades, list) else []
    doc.extend(_render_closed_trades_table(trades))

    raw_fills = result_data.get("fills")
    fills = raw_fills if isinstance(raw_fills, list) else []
    doc.extend(_render_fills_table(fills))

    raw_ledger = result_data.get("ledger")
    ledger = raw_ledger if isinstance(raw_ledger, list) else []
    doc.extend(_render_ledger_table(ledger))

    doc.append(
        '  <footer style="margin-top: 40px; color: #94a3b8; font-size: 0.8rem;">'
        'Market Research Lab — Personal Investment Analysis Monolith</footer>'
    )
    doc.append("</body>")
    doc.append("</html>")

    return "\n".join(doc)


def generate_backtest_csv(result_data: dict[str, JsonValue]) -> str:
    """Generate a comprehensive multi-section CSV export for Backtest results."""
    output = io.StringIO()
    writer = csv.writer(output)

    spec_raw = result_data.get("specification")
    spec = spec_raw if isinstance(spec_raw, dict) else {}
    metrics_raw = result_data.get("metrics")
    metrics = metrics_raw if isinstance(metrics_raw, dict) else {}

    # Section 1: Run Metadata & Specification
    writer.writerow(["Backtest Run Specification", ""])
    writer.writerow(["Run ID", result_data.get("run_id", "")])
    writer.writerow(["Strategy Name", spec.get("strategy_name", "")])
    writer.writerow(
        [
            "Strategy Revision",
            result_data.get("strategy_revision") or spec.get("strategy_revision", ""),
        ]
    )
    writer.writerow(["Security ID", spec.get("security_id", "")])
    universe_str = (
        ", ".join(spec.get("universe", [])) if spec.get("universe") else spec.get("security_id", "")
    )
    writer.writerow(["Universe", universe_str])
    writer.writerow(["Benchmark Security", spec.get("benchmark_security_id", "None")])
    writer.writerow(["Dataset Version ID", spec.get("dataset_version_id", "")])
    writer.writerow(["Start Date", spec.get("start_date", "")])
    writer.writerow(["End Date", spec.get("end_date", "")])
    writer.writerow(["Starting Cash", spec.get("starting_cash", "")])
    writer.writerow(["Price Field", spec.get("price_field", "close")])
    writer.writerow(["Sample Status", "Out-of-sample (Point-in-time sequential simulation)"])

    exec_raw = spec.get("execution")
    if isinstance(exec_raw, dict):
        writer.writerow(["Schedule", exec_raw.get("schedule", "daily")])
        writer.writerow(["Commission Rate", exec_raw.get("commission_rate", 0.0)])
        writer.writerow(["Slippage Rate", exec_raw.get("slippage_rate", 0.0)])
        writer.writerow(["Allow Shorting", exec_raw.get("allow_shorting", True)])
        writer.writerow(["Borrow Fee Rate", exec_raw.get("borrow_fee_rate", 0.0)])
        writer.writerow(["Cash Interest Rate", exec_raw.get("cash_interest_rate", 0.0)])
        raw_u = exec_raw.get("unavailable_borrow", [])
        u_str = ", ".join(str(x) for x in raw_u) if isinstance(raw_u, list) else str(raw_u)
        writer.writerow(["Unavailable Borrow", u_str])

    params_raw = spec.get("parameters")
    if isinstance(params_raw, dict):
        for k, v in sorted(params_raw.items()):
            writer.writerow([f"Parameter: {k}", v])
    writer.writerow([])

    # Section 2: Headline Performance Metrics
    writer.writerow(["Performance Metrics", ""])
    writer.writerow(["Total Return", metrics.get("total_return", "")])
    writer.writerow(["Annualized Return", metrics.get("annualized_return", "")])
    writer.writerow(["Annualized Volatility", metrics.get("annualized_volatility", "")])
    writer.writerow(["Sharpe Ratio", metrics.get("sharpe_ratio", "")])
    writer.writerow(["Sortino Ratio", metrics.get("sortino_ratio", "")])
    writer.writerow(["Max Drawdown", metrics.get("max_drawdown", "")])
    writer.writerow(["Calmar Ratio", metrics.get("calmar_ratio", "")])
    writer.writerow(["Hit Rate", metrics.get("hit_rate", "")])
    writer.writerow(["Turnover", metrics.get("turnover", "")])
    writer.writerow(["Gross Exposure", metrics.get("gross_exposure", "")])
    writer.writerow(["Net Exposure", metrics.get("net_exposure", "")])
    writer.writerow(["Benchmark Relative Return", metrics.get("benchmark_relative_return", "")])
    writer.writerow(["Number of Trades", metrics.get("num_trades", "")])
    writer.writerow(["Number of Fills", metrics.get("num_fills", "")])
    writer.writerow([])

    # Cost attribution
    result_manifest_raw = result_data.get("manifest")
    result_manifest = result_manifest_raw if isinstance(result_manifest_raw, dict) else {}
    costs_raw = result_manifest.get("costs")
    costs = costs_raw if isinstance(costs_raw, dict) else {}
    portfolio_impact_raw = costs.get("portfolio_impact")
    portfolio_impact = portfolio_impact_raw if isinstance(portfolio_impact_raw, dict) else {}
    writer.writerow(["Cost Attribution", ""])
    writer.writerow(["Total Commission", costs.get("total_commission", 0.0)])
    writer.writerow(["Total Slippage", costs.get("total_slippage", 0.0)])
    writer.writerow(["Total Borrow Fees", costs.get("total_borrow_fees", 0.0)])
    writer.writerow(["Total Cash Interest", costs.get("total_cash_interest", 0.0)])
    writer.writerow(["Net Costs", costs.get("total_costs", 0.0)])
    writer.writerow(["Portfolio Impact - Commission", portfolio_impact.get("commission", "")])
    writer.writerow(["Portfolio Impact - Slippage", portfolio_impact.get("slippage", "")])
    writer.writerow(["Portfolio Impact - Borrow Fees", portfolio_impact.get("borrow_fees", "")])
    writer.writerow(["Portfolio Impact - Cash Interest", portfolio_impact.get("cash_interest", "")])
    writer.writerow(["Portfolio Impact - Net", portfolio_impact.get("net", "")])
    writer.writerow([])

    # Warnings & Rejections
    raw_warnings = result_data.get("warnings")
    warnings = raw_warnings if isinstance(raw_warnings, list) else []
    if warnings:
        writer.writerow(["Warnings", ""])
        for w in warnings:
            writer.writerow(["Warning", str(w)])
        writer.writerow([])

    raw_rejections = result_data.get("rejections")
    rejections = raw_rejections if isinstance(raw_rejections, list) else []
    if rejections:
        writer.writerow(["Constraint Rejections", ""])
        for r in rejections:
            if isinstance(r, dict):
                writer.writerow(
                    [
                        r.get("session_date", ""),
                        r.get("security_id", ""),
                        r.get("rule", ""),
                        r.get("reason", ""),
                    ]
                )
            else:
                writer.writerow(["Rejection", str(r)])
        writer.writerow([])

    # Section 3: Closed Trades Log
    writer.writerow(["Closed Trades", ""])
    raw_trades = result_data.get("trades")
    trades = raw_trades if isinstance(raw_trades, list) else []
    writer.writerow(
        [
            "Trade ID",
            "Security ID",
            "Entry Date",
            "Exit Date",
            "Entry Price",
            "Exit Price",
            "Quantity",
            "Entry Cost",
            "Exit Proceeds",
            "PnL",
            "Return Pct",
        ]
    )
    for tr in trades:
        if isinstance(tr, dict):
            writer.writerow(
                [
                    tr.get("trade_id", ""),
                    tr.get("security_id", ""),
                    tr.get("entry_date", ""),
                    tr.get("exit_date", ""),
                    tr.get("entry_price", ""),
                    tr.get("exit_price", ""),
                    tr.get("quantity", ""),
                    tr.get("entry_cost", ""),
                    tr.get("exit_proceeds", ""),
                    tr.get("pnl", ""),
                    tr.get("return_pct", ""),
                ]
            )
    writer.writerow([])

    # Section 4: Simulated Fills Log
    writer.writerow(["Simulated Fills", ""])
    raw_fills = result_data.get("fills")
    fills = raw_fills if isinstance(raw_fills, list) else []
    writer.writerow(
        [
            "Trade ID",
            "Security ID",
            "Session Date",
            "Decision Time",
            "Side",
            "Quantity",
            "Fill Price",
            "Notional",
            "Commission",
            "Slippage Cost",
            "Rationale",
        ]
    )
    for fill in fills:
        if isinstance(fill, dict):
            writer.writerow(
                [
                    fill.get("trade_id", ""),
                    fill.get("security_id", ""),
                    fill.get("session_date", ""),
                    fill.get("decision_time", ""),
                    fill.get("side", ""),
                    fill.get("quantity", ""),
                    fill.get("price", ""),
                    fill.get("notional", ""),
                    fill.get("commission", ""),
                    fill.get("slippage_cost", ""),
                    fill.get("rationale", ""),
                ]
            )
    writer.writerow([])

    # Section 5: Daily Mark-to-Market Ledger
    writer.writerow(["Daily Portfolio Ledger", ""])
    raw_ledger = result_data.get("ledger")
    ledger = raw_ledger if isinstance(raw_ledger, list) else []
    writer.writerow(
        [
            "Session Date",
            "Signal Weight",
            "Positions",
            "Cash",
            "Position Value",
            "Portfolio Value",
            "Gross Exposure",
            "Net Exposure",
            "Borrow Fees",
            "Cash Interest",
        ]
    )
    for row in ledger:
        if isinstance(row, dict):
            raw_positions = row.get("positions")
            positions_dict = raw_positions if isinstance(raw_positions, dict) else {}
            if positions_dict:
                pos_summary = "; ".join(
                    f"{sym}:{pos.get('shares', 0)}sh"
                    for sym, pos in positions_dict.items()
                    if isinstance(pos, dict)
                )
            else:
                pos_summary = f"{row.get('shares', 0)}sh"
            writer.writerow(
                [
                    row.get("session_date", ""),
                    row.get("signal_weight", ""),
                    pos_summary,
                    row.get("cash", ""),
                    row.get("position_value", ""),
                    row.get("portfolio_value", ""),
                    row.get("gross_exposure", ""),
                    row.get("net_exposure", ""),
                    row.get("borrow_fees", 0.0),
                    row.get("cash_interest", 0.0),
                ]
            )

    return output.getvalue()


def generate_options_backtest_csv(result_data: dict[str, JsonValue]) -> str:
    """Generate a compact options spread ledger export."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Security",
            "Expiration",
            "Short Strike",
            "Long Strike",
            "Entry Credit",
            "Worst PnL",
            "Best PnL",
            "Full Possible Loss",
            "ROM",
            "Reliability",
            "Stop Changes",
            "Counterfactual",
            "Close Rule",
        ]
    )
    positions = result_data.get("positions", [])
    if isinstance(positions, list):
        for position in positions:
            if isinstance(position, dict):
                stop_movements = position.get("stop_movements", [])
                writer.writerow(
                    [
                        position.get("security_id", ""),
                        position.get("expiration", ""),
                        position.get("short_strike", ""),
                        position.get("long_strike", ""),
                        position.get("entry_credit", ""),
                        position.get("worst_net_pnl", ""),
                        position.get("best_net_pnl", ""),
                        position.get("full_possible_loss", ""),
                        position.get("return_on_margin_pct", ""),
                        position.get("reliability_pct", ""),
                        len(stop_movements) if isinstance(stop_movements, list) else 0,
                        position.get("counterfactual", ""),
                        position.get("close_rule", ""),
                    ]
                )
    return output.getvalue()


def generate_options_backtest_html(
    result_data: dict[str, JsonValue], manifest_data: dict[str, JsonValue]
) -> str:
    """Generate a self-contained options result report."""
    run_id = html.escape(str(result_data.get("run_id") or manifest_data.get("id") or "N/A"))
    summary = result_data.get("summary", {})
    rows = (
        "".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            for key, value in summary.items()
        )
        if isinstance(summary, dict)
        else ""
    )
    positions = result_data.get("positions", [])
    position_rows = ""
    if isinstance(positions, list):
        position_rows = "".join(
            "<tr>"
            f"<td>{html.escape(str(position.get('security_id', '')))}</td>"
            f"<td>{html.escape(str(position.get('expiration', '')))}</td>"
            f"<td>{html.escape(str(position.get('short_strike', '')))} / "
            f"{html.escape(str(position.get('long_strike', '')))}</td>"
            f"<td>{html.escape(str(position.get('worst_net_pnl', '')))}</td>"
            f"<td>{html.escape(str(position.get('best_net_pnl', '')))}</td>"
            f"<td>{html.escape(str(position.get('close_rule', '')))}</td></tr>"
            for position in positions
            if isinstance(position, dict)
        )
    warnings = result_data.get("warnings", [])
    warning_html = (
        "".join(f"<li>{html.escape(str(item))}</li>" for item in warnings)
        if isinstance(warnings, list)
        else ""
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>"
        f"Options Backtest {run_id}</title></head><body><h1>Options Backtest {run_id}</h1>"
        f"<p>Provider: {html.escape(str(manifest_data.get('provider', 'unknown')))}</p>"
        f"<p>Strategy revision: "
        f"{html.escape(str(manifest_data.get('strategy_revision', 'unknown')))}</p>"
        f"<table>{rows}</table><h2>Positions</h2><table>"
        f"<tr><th>Security</th><th>Expiry</th><th>Strikes</th><th>Worst PnL</th>"
        f"<th>Best PnL</th><th>Close Rule</th></tr>{position_rows}</table>"
        f"<h2>Warnings</h2><ul>{warning_html}</ul></body></html>"
    )
