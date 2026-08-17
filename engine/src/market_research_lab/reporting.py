"""Reporting and document export generators for Market Research Lab."""

from __future__ import annotations

import csv
import html
import io
from typing import Any


def generate_valuation_html_report(
    result_data: dict[str, Any],
    manifest_data: dict[str, Any],
) -> str:
    """Generate a self-contained, human-readable HTML valuation report."""
    method_rev = html.escape(str(result_data.get("method_revision") or "unversioned"))
    run_id = html.escape(str(manifest_data.get("id") or result_data.get("run_id") or "N/A"))
    calc_at = html.escape(str(result_data.get("calculated_at") or "N/A"))
    dataset_versions = result_data.get("dataset_version_ids", [])
    warnings = result_data.get("warnings", [])

    is_dcf = "forecast_cash_flows" in result_data or "value_per_share" in result_data
    symbol = html.escape(str(result_data.get("symbol") or result_data.get("target", {}).get("symbol", "")))
    name = html.escape(str(result_data.get("name") or result_data.get("target", {}).get("name", "")))
    currency = html.escape(str(result_data.get("currency") or result_data.get("target", {}).get("currency", "USD")))

    doc = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>Valuation Report — {symbol} ({method_rev})</title>",
        "  <style>",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #1e293b; max-width: 960px; margin: 40px auto; padding: 0 20px; }",
        "    h1, h2, h3 { color: #0f172a; margin-top: 28px; }",
        "    .meta { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; }",
        "    .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }",
        "    .metric-card { background: #f1f5f9; border-radius: 6px; padding: 12px 16px; }",
        "    .metric-value { font-size: 1.5rem; font-weight: 700; color: #0f172a; }",
        "    .metric-label { font-size: 0.85rem; color: #64748b; text-transform: uppercase; }",
        "    table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 0.95rem; }",
        "    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }",
        "    th { background: #f8fafc; font-weight: 600; color: #475569; }",
        "    .num { text-align: right; font-variant-numeric: tabular-nums; }",
        "    .warning { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; margin: 16px 0; border-radius: 4px; }",
        "    .badge { display: inline-block; background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin: 2px; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>Valuation Report: {symbol} — {name}</h1>",
        '  <div class="meta">',
        '    <div class="meta-grid">',
        f"      <div><strong>Method:</strong> {method_rev}</div>",
        f"      <div><strong>Run ID:</strong> {run_id}</div>",
        f"      <div><strong>Calculated:</strong> {calc_at}</div>",
        f"      <div><strong>Currency:</strong> {currency}</div>",
        f"      <div><strong>Sample Status:</strong> Out-of-sample (Point-in-time calculation)</div>",
        "    </div>",
        '    <div style="margin-top: 12px;"><strong>Dataset Versions:</strong> ' +
        "".join(f'<span class="badge">{html.escape(str(ds))}</span>' for ds in dataset_versions) +
        "    </div>",
        "  </div>",
    ]

    if warnings:
        doc.append('  <div class="warning"><strong>Warnings:</strong><ul>')
        for w in warnings:
            doc.append(f"    <li>{html.escape(str(w))}</li>")
        doc.append("  </ul></div>")

    if is_dcf:
        vps = result_data.get("value_per_share")
        ev = result_data.get("enterprise_value")
        eq_val = result_data.get("equity_value")
        tv_contrib = result_data.get("terminal_value_contribution")
        vps_str = f"{currency} {vps:.2f}" if vps is not None else "—"
        ev_str = f"{currency} {ev:.2f}" if ev is not None else "—"
        eq_str = f"{currency} {eq_val:.2f}" if eq_val is not None else "—"
        tv_str = f"{tv_contrib * 100:.1f}%" if tv_contrib is not None else "—"

        doc.append("  <h2>Valuation Summary</h2>")
        doc.append('  <div class="meta-grid">')
        doc.append(f'    <div class="metric-card"><div class="metric-label">Value Per Share</div><div class="metric-value">{vps_str}</div></div>')
        doc.append(f'    <div class="metric-card"><div class="metric-label">Enterprise Value</div><div class="metric-value">{ev_str}</div></div>')
        doc.append(f'    <div class="metric-card"><div class="metric-label">Equity Value</div><div class="metric-value">{eq_str}</div></div>')
        doc.append(f'    <div class="metric-card"><div class="metric-label">Terminal Contribution</div><div class="metric-value">{tv_str}</div></div>')
        doc.append("  </div>")

        # Key Inputs / Assumptions Table
        inputs = result_data.get("inputs")
        if isinstance(inputs, dict):
            doc.append("  <h3>Valuation Assumptions</h3>")
            doc.append("  <table>")
            doc.append("    <thead><tr><th>Assumption</th><th class=\"num\">Value</th></tr></thead>")
            doc.append("    <tbody>")
            doc.append(f"      <tr><td>Base Revenue</td><td class=\"num\">{currency} {inputs.get('base_revenue', 0):.2f}</td></tr>")
            doc.append(f"      <tr><td>Revenue Growth Rate</td><td class=\"num\">{inputs.get('revenue_growth_rate', 0)*100:.1f}%</td></tr>")
            doc.append(f"      <tr><td>Operating Margin</td><td class=\"num\">{inputs.get('operating_margin', 0)*100:.1f}%</td></tr>")
            doc.append(f"      <tr><td>Effective Tax Rate</td><td class=\"num\">{inputs.get('tax_rate', 0)*100:.1f}%</td></tr>")
            doc.append(f"      <tr><td>Reinvestment Rate (% NOPAT)</td><td class=\"num\">{inputs.get('reinvestment_rate', 0)*100:.1f}%</td></tr>")
            doc.append(f"      <tr><td>WACC / Discount Rate</td><td class=\"num\">{inputs.get('wacc', 0)*100:.2f}%</td></tr>")
            doc.append(f"      <tr><td>Perpetual Terminal Growth Rate</td><td class=\"num\">{inputs.get('terminal_growth_rate', 0)*100:.2f}%</td></tr>")
            doc.append(f"      <tr><td>Shares Outstanding</td><td class=\"num\">{inputs.get('shares_outstanding', 0):.2f}</td></tr>")
            doc.append(f"      <tr><td>Total Debt</td><td class=\"num\">{currency} {inputs.get('total_debt', 0):.2f}</td></tr>")
            doc.append(f"      <tr><td>Cash & Equivalents</td><td class=\"num\">{currency} {inputs.get('cash', 0):.2f}</td></tr>")
            doc.append("    </tbody>")
            doc.append("  </table>")

        # Forecast Cash Flows Table
        cfs = result_data.get("forecast_cash_flows", [])
        if cfs:
            doc.append("  <h3>Forecast Cash Flows</h3>")
            doc.append("  <table>")
            doc.append('    <thead><tr><th>Year</th><th class="num">Revenue</th><th class="num">Growth</th><th class="num">EBIT</th><th class="num">NOPAT</th><th class="num">Reinvestment</th><th class="num">FCFF</th><th class="num">DF</th><th class="num">PV</th></tr></thead>')
            doc.append("    <tbody>")
            for cf in cfs:
                doc.append(f"      <tr><td>Year {cf.get('year')}</td><td class=\"num\">{cf.get('revenue', 0):.2f}</td><td class=\"num\">{cf.get('revenue_growth', 0)*100:.1f}%</td><td class=\"num\">{cf.get('operating_income', 0):.2f}</td><td class=\"num\">{cf.get('nopat', 0):.2f}</td><td class=\"num\">{cf.get('reinvestment', 0):.2f}</td><td class=\"num\">{cf.get('free_cash_flow', 0):.2f}</td><td class=\"num\">{cf.get('discount_factor', 0):.4f}</td><td class=\"num\">{cf.get('present_value', 0):.2f}</td></tr>")
            doc.append("    </tbody>")
            doc.append("  </table>")

        # Scenarios Table
        scenarios = result_data.get("scenarios", [])
        if scenarios:
            doc.append("  <h3>Scenario Analysis</h3>")
            doc.append("  <table>")
            doc.append('    <thead><tr><th>Scenario</th><th class="num">WACC</th><th class="num">Terminal Growth</th><th class="num">Revenue Growth</th><th class="num">Operating Margin</th><th class="num">Per Share Value</th></tr></thead>')
            doc.append("    <tbody>")
            for sc in scenarios:
                svps = sc.get("value_per_share")
                svps_str = f"{currency} {svps:.2f}" if svps is not None else "—"
                wacc_sc = sc.get("wacc", 0) * 100
                tg_sc = sc.get("terminal_growth_rate", 0) * 100
                rg_sc = sc.get("revenue_growth_rate", 0) * 100
                om_sc = sc.get("operating_margin", 0) * 100
                doc.append(f"      <tr><td><strong>{html.escape(str(sc.get('name')))}</strong></td><td class=\"num\">{wacc_sc:.1f}%</td><td class=\"num\">{tg_sc:.1f}%</td><td class=\"num\">{rg_sc:.1f}%</td><td class=\"num\">{om_sc:.1f}%</td><td class=\"num\"><strong>{svps_str}</strong></td></tr>")
            doc.append("    </tbody>")
            doc.append("  </table>")

    else:
        # Comparable Company Multiples Table
        target = result_data.get("target", {})
        peers = result_data.get("peers", [])
        medians = result_data.get("peer_medians", {})

        doc.append("  <h2>Trading Multiples</h2>")
        doc.append("  <table>")
        doc.append('    <thead><tr><th>Security</th><th class="num">P/E</th><th class="num">EV / Revenue</th><th class="num">EV / EBITDA</th><th class="num">FCF Yield</th></tr></thead>')
        doc.append("    <tbody>")
        for comp in [target, *peers, medians]:
            c_name = html.escape(str(comp.get("name", "")))
            pe = comp.get("price_to_earnings")
            ev_rev = comp.get("ev_to_revenue")
            ev_ebitda = comp.get("ev_to_ebitda")
            fcf_y = comp.get("free_cash_flow_yield")
            pe_str = f"{pe:.2f}x" if pe is not None else "—"
            ev_rev_str = f"{ev_rev:.2f}x" if ev_rev is not None else "—"
            ev_ebitda_str = f"{ev_ebitda:.2f}x" if ev_ebitda is not None else "—"
            fcf_y_str = f"{fcf_y * 100:.2f}%" if fcf_y is not None else "—"
            doc.append(f"      <tr><td>{c_name}</td><td class=\"num\">{pe_str}</td><td class=\"num\">{ev_rev_str}</td><td class=\"num\">{ev_ebitda_str}</td><td class=\"num\">{fcf_y_str}</td></tr>")
        doc.append("    </tbody>")
        doc.append("  </table>")

    doc.append('  <footer style="margin-top: 40px; color: #94a3b8; font-size: 0.8rem;">Market Research Lab — Personal Investment Analysis Monolith</footer>')
    doc.append("</body>")
    doc.append("</html>")

    return "\n".join(doc)


def generate_valuation_csv(result_data: dict[str, Any]) -> str:
    """Generate a tabular CSV export for valuation results."""
    output = io.StringIO()
    writer = csv.writer(output)

    is_dcf = "forecast_cash_flows" in result_data or "value_per_share" in result_data

    if is_dcf:
        writer.writerow(["Valuation Method", "FCFF DCF"])
        writer.writerow(["Method Revision", result_data.get("method_revision", "")])
        writer.writerow(["Run ID", result_data.get("run_id", "")])
        writer.writerow(["Security", result_data.get("symbol", "")])
        writer.writerow(["Currency", result_data.get("currency", "USD")])
        writer.writerow(["Calculated At", result_data.get("calculated_at", "")])
        writer.writerow(["Value Per Share", result_data.get("value_per_share", "")])
        writer.writerow(["Enterprise Value", result_data.get("enterprise_value", "")])
        writer.writerow(["Equity Value", result_data.get("equity_value", "")])
        writer.writerow(["Terminal Value Contribution", result_data.get("terminal_value_contribution", "")])
        writer.writerow([])

        # Forecast cash flows table
        cfs = result_data.get("forecast_cash_flows", [])
        if cfs:
            writer.writerow(["Forecast Year", "Revenue", "Growth", "Operating Income", "Tax", "NOPAT", "Reinvestment", "FCFF", "Discount Factor", "Present Value"])
            for cf in cfs:
                writer.writerow([
                    cf.get("year"),
                    cf.get("revenue"),
                    cf.get("revenue_growth"),
                    cf.get("operating_income"),
                    cf.get("tax"),
                    cf.get("nopat"),
                    cf.get("reinvestment"),
                    cf.get("free_cash_flow"),
                    cf.get("discount_factor"),
                    cf.get("present_value"),
                ])
            writer.writerow([])

        # Scenarios
        scenarios = result_data.get("scenarios", [])
        if scenarios:
            writer.writerow(["Scenario", "WACC", "Terminal Growth", "Revenue Growth", "Operating Margin", "Enterprise Value", "Value Per Share"])
            for sc in scenarios:
                writer.writerow([
                    sc.get("name"),
                    sc.get("wacc"),
                    sc.get("terminal_growth_rate"),
                    sc.get("revenue_growth_rate"),
                    sc.get("operating_margin"),
                    sc.get("enterprise_value"),
                    sc.get("value_per_share"),
                ])
    else:
        writer.writerow(["Valuation Method", "Trading Comparables"])
        writer.writerow(["Method Revision", result_data.get("method_revision", "")])
        writer.writerow(["Run ID", result_data.get("run_id", "")])
        writer.writerow(["Calculated At", result_data.get("calculated_at", "")])
        writer.writerow([])

        writer.writerow(["Security", "Symbol", "Currency", "P/E", "EV/Revenue", "EV/EBITDA", "Free Cash Flow Yield"])
        target = result_data.get("target", {})
        peers = result_data.get("peers", [])
        medians = result_data.get("peer_medians", {})
        for comp in [target, *peers, medians]:
            writer.writerow([
                comp.get("name", ""),
                comp.get("symbol", ""),
                comp.get("currency", ""),
                comp.get("price_to_earnings", ""),
                comp.get("ev_to_revenue", ""),
                comp.get("ev_to_ebitda", ""),
                comp.get("free_cash_flow_yield", ""),
            ])

    return output.getvalue()
