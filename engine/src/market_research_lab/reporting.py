"""Reporting and document export generators for Market Research Lab."""

from __future__ import annotations

import csv
import html
import io

from .json_types import JsonValue


def generate_valuation_html_report(
    result_data: dict[str, JsonValue],
    manifest_data: dict[str, JsonValue],
) -> str:
    """Generate a self-contained, human-readable HTML valuation report."""
    method_rev = html.escape(str(result_data.get("method_revision") or "unversioned"))
    run_id = html.escape(str(manifest_data.get("id") or result_data.get("run_id") or "N/A"))
    calc_at = html.escape(str(result_data.get("calculated_at") or "N/A"))
    dataset_versions = result_data.get("dataset_version_ids")
    dataset_version_list = dataset_versions if isinstance(dataset_versions, list) else []
    raw_warnings = result_data.get("warnings")
    warnings = raw_warnings if isinstance(raw_warnings, list) else []

    is_dcf = "forecast_cash_flows" in result_data or "value_per_share" in result_data
    target_raw = result_data.get("target")
    target_dict = target_raw if isinstance(target_raw, dict) else {}
    symbol = html.escape(str(result_data.get("symbol") or target_dict.get("symbol") or ""))
    name = html.escape(str(result_data.get("name") or target_dict.get("name") or ""))
    currency = html.escape(str(result_data.get("currency") or target_dict.get("currency") or "USD"))

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
        "      <div><strong>Sample Status:</strong> Out-of-sample (Point-in-time calculation)</div>",
        "    </div>",
        '    <div style="margin-top: 12px;"><strong>Dataset Versions:</strong> '
        + "".join(
            f'<span class="badge">{html.escape(str(ds))}</span>' for ds in dataset_version_list
        )
        + "    </div>",
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
        vps_str = (
            f"{currency} {float(vps):.2f}"
            if vps is not None and isinstance(vps, (int, float))
            else "—"
        )
        ev_str = (
            f"{currency} {float(ev):.2f}"
            if ev is not None and isinstance(ev, (int, float))
            else "—"
        )
        eq_str = (
            f"{currency} {float(eq_val):.2f}"
            if eq_val is not None and isinstance(eq_val, (int, float))
            else "—"
        )
        tv_str = (
            f"{float(tv_contrib) * 100:.1f}%"
            if tv_contrib is not None and isinstance(tv_contrib, (int, float))
            else "—"
        )

        doc.append("  <h2>Valuation Summary</h2>")
        doc.append('  <div class="meta-grid">')
        doc.append(
            f'    <div class="metric-card"><div class="metric-label">Value Per Share</div><div class="metric-value">{vps_str}</div></div>'
        )
        doc.append(
            f'    <div class="metric-card"><div class="metric-label">Enterprise Value</div><div class="metric-value">{ev_str}</div></div>'
        )
        doc.append(
            f'    <div class="metric-card"><div class="metric-label">Equity Value</div><div class="metric-value">{eq_str}</div></div>'
        )
        doc.append(
            f'    <div class="metric-card"><div class="metric-label">Terminal Contribution</div><div class="metric-value">{tv_str}</div></div>'
        )
        doc.append("  </div>")

        # Key Inputs / Assumptions Table
        inputs = result_data.get("inputs")
        if isinstance(inputs, dict):
            doc.append("  <h3>Valuation Assumptions</h3>")
            doc.append("  <table>")
            doc.append('    <thead><tr><th>Assumption</th><th class="num">Value</th></tr></thead>')
            doc.append("    <tbody>")
            doc.append(
                f'      <tr><td>Base Revenue</td><td class="num">{currency} {float(inputs.get("base_revenue", 0)):.2f}</td></tr>'
            )
            doc.append(
                f'      <tr><td>Revenue Growth Rate</td><td class="num">{float(inputs.get("revenue_growth_rate", 0)) * 100:.1f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>Operating Margin</td><td class="num">{float(inputs.get("operating_margin", 0)) * 100:.1f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>Effective Tax Rate</td><td class="num">{float(inputs.get("tax_rate", 0)) * 100:.1f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>Reinvestment Rate (% NOPAT)</td><td class="num">{float(inputs.get("reinvestment_rate", 0)) * 100:.1f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>WACC / Discount Rate</td><td class="num">{float(inputs.get("wacc", 0)) * 100:.2f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>Perpetual Terminal Growth Rate</td><td class="num">{float(inputs.get("terminal_growth_rate", 0)) * 100:.2f}%</td></tr>'
            )
            doc.append(
                f'      <tr><td>Shares Outstanding</td><td class="num">{float(inputs.get("shares_outstanding", 0)):.2f}</td></tr>'
            )
            doc.append(
                f'      <tr><td>Total Debt</td><td class="num">{currency} {float(inputs.get("total_debt", 0)):.2f}</td></tr>'
            )
            doc.append(
                f'      <tr><td>Cash & Equivalents</td><td class="num">{currency} {float(inputs.get("cash", 0)):.2f}</td></tr>'
            )
            doc.append("    </tbody>")
            doc.append("  </table>")

        # Forecast Cash Flows Table
        raw_cfs = result_data.get("forecast_cash_flows")
        cfs = raw_cfs if isinstance(raw_cfs, list) else []
        if cfs:
            doc.append("  <h3>Forecast Cash Flows</h3>")
            doc.append("  <table>")
            doc.append(
                '    <thead><tr><th>Year</th><th class="num">Revenue</th><th class="num">Growth</th><th class="num">EBIT</th><th class="num">NOPAT</th><th class="num">Reinvestment</th><th class="num">FCFF</th><th class="num">DF</th><th class="num">PV</th></tr></thead>'
            )
            doc.append("    <tbody>")
            for cf in cfs:
                if isinstance(cf, dict):
                    doc.append(
                        f'      <tr><td>Year {cf.get("year")}</td><td class="num">{float(cf.get("revenue", 0)):.2f}</td><td class="num">{float(cf.get("revenue_growth", 0)) * 100:.1f}%</td><td class="num">{float(cf.get("operating_income", 0)):.2f}</td><td class="num">{float(cf.get("nopat", 0)):.2f}</td><td class="num">{float(cf.get("reinvestment", 0)):.2f}</td><td class="num">{float(cf.get("free_cash_flow", 0)):.2f}</td><td class="num">{float(cf.get("discount_factor", 0)):.4f}</td><td class="num">{float(cf.get("present_value", 0)):.2f}</td></tr>'
                    )
            doc.append("    </tbody>")
            doc.append("  </table>")

        # Scenarios Table
        raw_scenarios = result_data.get("scenarios")
        scenarios = raw_scenarios if isinstance(raw_scenarios, list) else []
        if scenarios:
            doc.append("  <h3>Scenario Analysis</h3>")
            doc.append("  <table>")
            doc.append(
                '    <thead><tr><th>Scenario</th><th class="num">WACC</th><th class="num">Terminal Growth</th><th class="num">Revenue Growth</th><th class="num">Operating Margin</th><th class="num">Per Share Value</th></tr></thead>'
            )
            doc.append("    <tbody>")
            for sc in scenarios:
                if isinstance(sc, dict):
                    svps = sc.get("value_per_share")
                    svps_str = (
                        f"{currency} {float(svps):.2f}"
                        if svps is not None and isinstance(svps, (int, float))
                        else "—"
                    )
                    wacc_sc = float(sc.get("wacc", 0)) * 100
                    tg_sc = float(sc.get("terminal_growth_rate", 0)) * 100
                    rg_sc = float(sc.get("revenue_growth_rate", 0)) * 100
                    om_sc = float(sc.get("operating_margin", 0)) * 100
                    doc.append(
                        f'      <tr><td><strong>{html.escape(str(sc.get("name")))}</strong></td><td class="num">{wacc_sc:.1f}%</td><td class="num">{tg_sc:.1f}%</td><td class="num">{rg_sc:.1f}%</td><td class="num">{om_sc:.1f}%</td><td class="num"><strong>{svps_str}</strong></td></tr>'
                    )
            doc.append("    </tbody>")
            doc.append("  </table>")

    else:
        # Comparable Company Multiples Table
        target = result_data.get("target")
        target_dict = target if isinstance(target, dict) else {}
        peers_raw = result_data.get("peers")
        peers_list = peers_raw if isinstance(peers_raw, list) else []
        medians_raw = result_data.get("peer_medians")
        medians_dict = medians_raw if isinstance(medians_raw, dict) else {}

        doc.append("  <h2>Trading Multiples</h2>")
        doc.append("  <table>")
        doc.append(
            '    <thead><tr><th>Security</th><th class="num">P/E</th><th class="num">EV / Revenue</th><th class="num">EV / EBITDA</th><th class="num">FCF Yield</th></tr></thead>'
        )
        doc.append("    <tbody>")
        for comp in [target_dict, *peers_list, medians_dict]:
            if isinstance(comp, dict):
                c_name = html.escape(str(comp.get("name", "")))
                pe = comp.get("price_to_earnings")
                ev_rev = comp.get("ev_to_revenue")
                ev_ebitda = comp.get("ev_to_ebitda")
                fcf_y = comp.get("free_cash_flow_yield")
                pe_str = (
                    f"{float(pe):.2f}x" if pe is not None and isinstance(pe, (int, float)) else "—"
                )
                ev_rev_str = (
                    f"{float(ev_rev):.2f}x"
                    if ev_rev is not None and isinstance(ev_rev, (int, float))
                    else "—"
                )
                ev_ebitda_str = (
                    f"{float(ev_ebitda):.2f}x"
                    if ev_ebitda is not None and isinstance(ev_ebitda, (int, float))
                    else "—"
                )
                fcf_y_str = (
                    f"{float(fcf_y) * 100:.2f}%"
                    if fcf_y is not None and isinstance(fcf_y, (int, float))
                    else "—"
                )
                doc.append(
                    f'      <tr><td>{c_name}</td><td class="num">{pe_str}</td><td class="num">{ev_rev_str}</td><td class="num">{ev_ebitda_str}</td><td class="num">{fcf_y_str}</td></tr>'
                )
        doc.append("    </tbody>")
        doc.append("  </table>")

    doc.append(
        '  <footer style="margin-top: 40px; color: #94a3b8; font-size: 0.8rem;">Market Research Lab — Personal Investment Analysis Monolith</footer>'
    )
    doc.append("</body>")
    doc.append("</html>")

    return "\n".join(doc)


def generate_valuation_csv(result_data: dict[str, JsonValue]) -> str:
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
        writer.writerow(
            ["Terminal Value Contribution", result_data.get("terminal_value_contribution", "")]
        )
        writer.writerow([])

        # Forecast cash flows table
        raw_cfs = result_data.get("forecast_cash_flows")
        cfs = raw_cfs if isinstance(raw_cfs, list) else []
        if cfs:
            writer.writerow(
                [
                    "Forecast Year",
                    "Revenue",
                    "Growth",
                    "Operating Income",
                    "Tax",
                    "NOPAT",
                    "Reinvestment",
                    "FCFF",
                    "Discount Factor",
                    "Present Value",
                ]
            )
            for cf in cfs:
                if isinstance(cf, dict):
                    writer.writerow(
                        [
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
                        ]
                    )
            writer.writerow([])

        # Scenarios
        raw_scenarios = result_data.get("scenarios")
        scenarios = raw_scenarios if isinstance(raw_scenarios, list) else []
        if scenarios:
            writer.writerow(
                [
                    "Scenario",
                    "WACC",
                    "Terminal Growth",
                    "Revenue Growth",
                    "Operating Margin",
                    "Enterprise Value",
                    "Value Per Share",
                ]
            )
            for sc in scenarios:
                if isinstance(sc, dict):
                    writer.writerow(
                        [
                            sc.get("name"),
                            sc.get("wacc"),
                            sc.get("terminal_growth_rate"),
                            sc.get("revenue_growth_rate"),
                            sc.get("operating_margin"),
                            sc.get("enterprise_value"),
                            sc.get("value_per_share"),
                        ]
                    )
    else:
        writer.writerow(["Valuation Method", "Trading Comparables"])
        writer.writerow(["Method Revision", result_data.get("method_revision", "")])
        writer.writerow(["Run ID", result_data.get("run_id", "")])
        writer.writerow(["Calculated At", result_data.get("calculated_at", "")])
        writer.writerow([])

        writer.writerow(
            [
                "Security",
                "Symbol",
                "Currency",
                "P/E",
                "EV/Revenue",
                "EV/EBITDA",
                "Free Cash Flow Yield",
            ]
        )
        target = result_data.get("target")
        target_dict = target if isinstance(target, dict) else {}
        peers_raw = result_data.get("peers")
        peers_list = peers_raw if isinstance(peers_raw, list) else []
        medians_raw = result_data.get("peer_medians")
        medians_dict = medians_raw if isinstance(medians_raw, dict) else {}
        for comp in [target_dict, *peers_list, medians_dict]:
            if isinstance(comp, dict):
                writer.writerow(
                    [
                        comp.get("name", ""),
                        comp.get("symbol", ""),
                        comp.get("currency", ""),
                        comp.get("price_to_earnings", ""),
                        comp.get("ev_to_revenue", ""),
                        comp.get("ev_to_ebitda", ""),
                        comp.get("free_cash_flow_yield", ""),
                    ]
                )

    return output.getvalue()


def generate_predictive_model_html_report(
    result_data: dict[str, JsonValue],
    manifest_data: dict[str, JsonValue],
) -> str:
    """Generate a self-contained report with labelled chronological model metrics."""
    model_name = html.escape(
        str(result_data.get("display_name") or result_data.get("model_name") or "Predictive Model")
    )
    run_id = html.escape(str(result_data.get("run_id") or manifest_data.get("id") or "N/A"))
    revision_values = manifest_data.get("definition_revisions")
    revisions = revision_values if isinstance(revision_values, list) else []
    revision = html.escape(
        str(result_data.get("model_revision") or (revisions[0] if revisions else "unversioned"))
    )
    datasets_raw = manifest_data.get("dataset_versions")
    datasets = datasets_raw if isinstance(datasets_raw, list) else []
    evaluation_raw = result_data.get("evaluation")
    evaluation = evaluation_raw if isinstance(evaluation_raw, dict) else {}
    splits_raw = evaluation.get("splits") or result_data.get("splits")
    splits = splits_raw if isinstance(splits_raw, list) else []
    metrics_raw = evaluation.get("period_metrics") or result_data.get("period_metrics")
    period_metrics = metrics_raw if isinstance(metrics_raw, list) else []
    folds_raw = evaluation.get("folds") or result_data.get("folds")
    folds = folds_raw if isinstance(folds_raw, list) else []
    parameters_raw = manifest_data.get("parameters")
    parameters = parameters_raw if isinstance(parameters_raw, dict) else {}
    preprocessing = (
        result_data.get("artifact", {}).get("preprocessing", {})
        if isinstance(result_data.get("artifact"), dict)
        else {}
    )
    evaluation_mode = html.escape(
        str(evaluation.get("mode") or result_data.get("evaluation_mode") or "holdout")
    )
    warnings_raw = result_data.get("warnings")
    warnings = warnings_raw if isinstance(warnings_raw, list) else []

    doc = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>{model_name} — Chronological Evaluation</title>",
        "  <style>",
        "    body { font-family: sans-serif; line-height: 1.5; color: #1e293b; "
        "max-width: 960px; margin: 40px auto; padding: 0 20px; }",
        "    h1, h2 { color: #0f172a; }",
        "    .meta { background: #f8fafc; border: 1px solid #e2e8f0; "
        "border-radius: 8px; padding: 16px; }",
        "    table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; }",
        "    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; }",
        "    th { background: #f8fafc; }",
        "    .note { background: #eff6ff; border-left: 4px solid #2563eb; padding: 12px 16px; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>{model_name}</h1>",
        f'  <div class="meta"><strong>Run:</strong> {run_id}<br>'
        f'<strong>Definition Revision:</strong> {revision}<br>'
        f'<strong>Dataset Versions:</strong> '
        f'{html.escape(", ".join(str(dataset) for dataset in datasets))}<br>'
        f'<strong>Evaluation Mode:</strong> {evaluation_mode}<br>'
        '<strong>Metric Scope:</strong> In-sample training; held-out validation and '
        'out-of-sample</div>',
        '  <p class="note">The initial fit uses training observations only. Each later '
        'fold uses only data available before its target date.</p>',
        "  <h2>Chronological Periods</h2>",
        "  <table>",
        "    <thead><tr><th>Period</th><th>Target Dates</th><th>Feature Dates</th>"
        "<th>Observations</th><th>Fit Scope</th></tr></thead>",
        "    <tbody>",
    ]
    for split in splits:
        if isinstance(split, dict):
            period = split.get("period", "")
            period_label = "out-of-sample" if period == "test" else period
            doc.append(
                "      <tr>"
                f"<td>{html.escape(str(period_label))}</td>"
                f"<td>{html.escape(str(split.get('start', '')))} to "
                f"{html.escape(str(split.get('end', '')))}</td>"
                f"<td>{html.escape(str(split.get('feature_start', '')))} to "
                f"{html.escape(str(split.get('feature_end', '')))}</td>"
                f"<td>{html.escape(str(split.get('observations', '')))}</td>"
                f"<td>{html.escape(str(split.get('fit_scope', '')))}</td>"
                "</tr>"
            )
    doc.extend(["    </tbody>", "  </table>"])
    if folds:
        doc.extend(
            [
                "  <h2>Walk-forward Folds</h2>",
                "  <table>",
                "    <thead><tr><th>Fold</th><th>Period</th><th>Prediction Session</th>"
                "<th>Target Date</th><th>Training Feature Dates</th>"
                "<th>Training Observations</th><th>Fit Scope</th><th>MAE</th>"
                "<th>RMSE</th></tr></thead>",
                "    <tbody>",
            ]
        )
        for fold in folds:
            if not isinstance(fold, dict):
                continue
            fold_metrics = fold.get("metrics")
            fold_metrics_dict = fold_metrics if isinstance(fold_metrics, dict) else {}
            period = fold.get("period", "")
            period_label = "out-of-sample" if period == "test" else period
            doc.append(
                "      <tr>"
                f"<td>{html.escape(str(fold.get('fold_index', '')))}</td>"
                f"<td>{html.escape(str(period_label))}</td>"
                f"<td>{html.escape(str(fold.get('prediction_session_date', '')))}</td>"
                f"<td>{html.escape(str(fold.get('target_date', '')))}</td>"
                f"<td>{html.escape(str(fold.get('training_start', '')))} to "
                f"{html.escape(str(fold.get('training_end', '')))}</td>"
                f"<td>{html.escape(str(fold.get('training_observations', '')))}</td>"
                f"<td>{html.escape(str(fold.get('fit_scope', '')))}</td>"
                f"<td>{html.escape(str(fold_metrics_dict.get('mae', '')))}</td>"
                f"<td>{html.escape(str(fold_metrics_dict.get('rmse', '')))}</td>"
                "</tr>"
            )
        doc.extend(["    </tbody>", "  </table>"])
    doc.extend(["  <h2>Period Metrics</h2>", "  <table>"])
    doc.append(
        "    <thead><tr><th>Period</th><th>Observations</th><th>Metric</th>"
        "<th>Value</th></tr></thead>"
    )
    doc.append("    <tbody>")
    for period_metric in period_metrics:
        if not isinstance(period_metric, dict):
            continue
        metric_values = period_metric.get("metrics")
        if not isinstance(metric_values, dict):
            continue
        for metric_name, metric_value in metric_values.items():
            period = period_metric.get("period", "")
            period_label = "out-of-sample" if period == "test" else period
            doc.append(
                "      <tr>"
                f"<td>{html.escape(str(period_label))}</td>"
                f"<td>{html.escape(str(period_metric.get('observations', '')))}</td>"
                f"<td>{html.escape(str(metric_name))}</td>"
                f"<td>{html.escape(str(metric_value))}</td>"
                "</tr>"
            )
    doc.extend(
        ["    </tbody>", "  </table>", "  <h2>Assumptions and Provenance</h2>", "  <table>"]
    )
    doc.append("    <tbody>")
    for label, value in (
        ("Target", result_data.get("target", "")),
        ("Horizon", result_data.get("horizon", "")),
        ("Features", result_data.get("features", "")),
        ("Parameters", parameters),
        ("Preprocessing", preprocessing),
    ):
        doc.append(
            f"      <tr><th>{html.escape(label)}</th>"
            f"<td>{html.escape(str(value))}</td></tr>"
        )
    doc.extend(
        [
            "    </tbody>",
            "  </table>",
            "  <h2>Warnings</h2>",
            "  <ul>",
        ]
    )
    if warnings:
        for warning in warnings:
            doc.append(f"    <li>{html.escape(str(warning))}</li>")
    else:
        doc.append("    <li>No warnings recorded.</li>")
    doc.extend(
        [
            "  </ul>",
            "  <footer>Market Research Lab — Predictive Model Run</footer>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(doc)


def generate_predictive_model_csv(result_data: dict[str, JsonValue]) -> str:
    """Generate a CSV export with period-labelled metrics and predictions."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Predictive Model", result_data.get("model_name", "")])
    writer.writerow(["Run ID", result_data.get("run_id", "")])
    writer.writerow(["Model Revision", result_data.get("model_revision", "")])
    writer.writerow([])
    writer.writerow(["Period", "Observations", "Metric", "Value"])
    metrics_raw = result_data.get("period_metrics")
    period_metrics = metrics_raw if isinstance(metrics_raw, list) else []
    for period_metric in period_metrics:
        if not isinstance(period_metric, dict):
            continue
        values = period_metric.get("metrics")
        if not isinstance(values, dict):
            continue
        period = period_metric.get("period", "")
        period_label = "out-of-sample" if period == "test" else period
        for metric_name, metric_value in values.items():
            writer.writerow(
                [
                    period_label,
                    period_metric.get("observations", ""),
                    metric_name,
                    metric_value,
                ]
            )
    writer.writerow([])
    writer.writerow(
        [
            "Fold",
            "Period",
            "Prediction Session",
            "Target Date",
            "Training Start",
            "Training End",
            "Training Observations",
            "Fit Scope",
            "Metric",
            "Value",
        ]
    )
    folds_raw = result_data.get("folds")
    folds = folds_raw if isinstance(folds_raw, list) else []
    for fold in folds:
        if not isinstance(fold, dict):
            continue
        metrics_raw = fold.get("metrics")
        fold_metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
        for metric_name, metric_value in fold_metrics.items():
            writer.writerow(
                [
                    fold.get("fold_index", ""),
                    fold.get("period", ""),
                    fold.get("prediction_session_date", ""),
                    fold.get("target_date", ""),
                    fold.get("training_start", ""),
                    fold.get("training_end", ""),
                    fold.get("training_observations", ""),
                    fold.get("fit_scope", ""),
                    metric_name,
                    metric_value,
                ]
            )
    writer.writerow([])
    writer.writerow(
        [
            "Session Date",
            "Target Date",
            "Period",
            "Feature Value",
            "Predicted Value",
            "Actual Target",
        ]
    )
    predictions_raw = result_data.get("predictions")
    predictions = predictions_raw if isinstance(predictions_raw, list) else []
    for prediction in predictions:
        if isinstance(prediction, dict):
            writer.writerow(
                [
                    prediction.get("session_date", ""),
                    prediction.get("target_date", ""),
                    prediction.get("period", ""),
                    prediction.get("feature_value", ""),
                    prediction.get("predicted_value", ""),
                    prediction.get("actual_target", ""),
                ]
            )
    return output.getvalue()


# ---------------------------------------------------------------------------
# Backtest HTML and CSV Exporters
# ---------------------------------------------------------------------------


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
    commission_rate = float(execution.get("commission_rate", 0.0))
    slippage_rate = float(execution.get("slippage_rate", 0.0))
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

    universe_display = ", ".join(universe_list) if universe_list else security_id
    title_symbol = (
        universe_display
        if len(universe_list) <= 3
        else f"{universe_list[0]} +{len(universe_list) - 1} more"
    )

    doc = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>Backtest Report — {title_symbol} ({strategy_name}:{strategy_rev})</title>",
        "  <style>",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #1e293b; max-width: 1040px; margin: 40px auto; padding: 0 20px; }",
        "    h1, h2, h3 { color: #0f172a; margin-top: 28px; }",
        "    .meta { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; }",
        "    .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }",
        "    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }",
        "    .metric-card { background: #f1f5f9; border-radius: 6px; padding: 12px 16px; border: 1px solid #e2e8f0; }",
        "    .metric-value { font-size: 1.4rem; font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }",
        "    .metric-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }",
        "    table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 0.9rem; }",
        "    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; }",
        "    th { background: #f8fafc; font-weight: 600; color: #475569; position: sticky; top: 0; }",
        "    .num { text-align: right; font-variant-numeric: tabular-nums; }",
        "    .warning { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; margin: 16px 0; border-radius: 4px; }",
        "    .rejection { background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; margin: 16px 0; border-radius: 4px; }",
        "    .badge { display: inline-block; background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin: 2px; }",
        "    .badge-bench { background: #fef3c7; color: #92400e; }",
        "    .badge-buy { background: #dcfce7; color: #166534; }",
        "    .badge-sell { background: #fef2f2; color: #991b1b; }",
        "    .scroll-table { max-height: 400px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 24px; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>Backtest Report: {title_symbol} — {strategy_name}</h1>",
        '  <div class="meta">',
        '    <div class="meta-grid">',
        f"      <div><strong>Strategy:</strong> {strategy_name} ({strategy_rev})</div>",
        f"      <div><strong>Run ID:</strong> {run_id}</div>",
        f"      <div><strong>Simulation Range:</strong> {start_date} to {end_date}</div>",
        f"      <div><strong>Starting Cash:</strong> ${starting_cash:,.2f} USD</div>",
        "      <div><strong>Sample Status:</strong> Out-of-sample (Point-in-time sequential simulation)</div>",
        f"      <div><strong>Execution:</strong> Next-bar open ({schedule})</div>",
        f"      <div><strong>Benchmark:</strong> {benchmark_id if benchmark_id else 'None'}</div>",
        "    </div>",
        '    <div style="margin-top: 12px;"><strong>Universe Securities:</strong> '
        + "".join(f'<span class="badge">{html.escape(str(s))}</span>' for s in universe_list)
        + "    </div>",
        '    <div style="margin-top: 8px;"><strong>Dataset Versions:</strong> '
        + "".join(
            f'<span class="badge">{html.escape(str(ds))}</span>' for ds in dataset_version_list
        )
        + "    </div>",
        "  </div>",
    ]

    if warnings:
        doc.append('  <div class="warning"><strong>Warnings:</strong><ul>')
        for w in warnings:
            doc.append(f"    <li>{html.escape(str(w))}</li>")
        doc.append("  </ul></div>")

    if rejections:
        doc.append('  <div class="rejection"><strong>Constraint Rejections:</strong><ul>')
        for r in rejections:
            if isinstance(r, dict):
                doc.append(
                    f"    <li><strong>{r.get('session_date')}: {r.get('security_id')}</strong> [{r.get('rule')}] {html.escape(str(r.get('reason')))}</li>"
                )
            else:
                doc.append(f"    <li>{html.escape(str(r))}</li>")
        doc.append("  </ul></div>")

    # Headline Performance Metrics
    doc.append("  <h2>Performance Overview</h2>")
    doc.append('  <div class="metric-grid">')
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Total Return</div><div class="metric-value">{total_return * 100:+.2f}%</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Annualized Return</div><div class="metric-value">{ann_return * 100:+.2f}%</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Annual Volatility</div><div class="metric-value">{ann_vol * 100:.2f}%</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Sharpe Ratio</div><div class="metric-value">{sharpe:.2f}</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Sortino Ratio</div><div class="metric-value">{sortino:.2f}</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Max Drawdown</div><div class="metric-value">{max_dd * 100:.2f}%</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Calmar Ratio</div><div class="metric-value">{calmar:.2f}</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Hit Rate / Win Rate</div><div class="metric-value">{hit_rate_str}</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Turnover</div><div class="metric-value">{turnover:.2f}x</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Gross / Net Exposure</div><div class="metric-value">{gross_exp * 100:.0f}% / {net_exp * 100:.0f}%</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Benchmark Relative</div><div class="metric-value">{bench_rel_str}</div></div>'
    )
    doc.append(
        f'    <div class="metric-card"><div class="metric-label">Trades / Fills</div><div class="metric-value">{num_trades} / {num_fills}</div></div>'
    )
    doc.append("  </div>")

    # Execution Assumptions Table
    doc.append("  <h2>Execution Model & Strategy Assumptions</h2>")
    doc.append("  <table>")
    doc.append(
        '    <thead><tr><th>Parameter / Assumption</th><th class="num">Value</th></tr></thead>'
    )
    doc.append("    <tbody>")
    doc.append(
        f'      <tr><td>Universe</td><td class="num">{html.escape(", ".join(universe_list))}</td></tr>'
    )
    if benchmark_id:
        doc.append(f'      <tr><td>Benchmark Security</td><td class="num">{benchmark_id}</td></tr>')
    doc.append(f'      <tr><td>Strategy</td><td class="num">{strategy_name}</td></tr>')
    doc.append(f'      <tr><td>Strategy Revision</td><td class="num">{strategy_rev}</td></tr>')
    doc.append(f'      <tr><td>Price Field</td><td class="num">{price_field}</td></tr>')
    doc.append(f'      <tr><td>Rebalance Schedule</td><td class="num">{schedule}</td></tr>')
    borrow_fee_rate = float(execution.get("borrow_fee_rate", 0.0))
    raw_unavail = execution.get("unavailable_borrow", [])
    unavailable_borrow = raw_unavail if isinstance(raw_unavail, list) else []

    doc.append(
        f'      <tr><td>Commission Rate</td><td class="num">{commission_rate * 10000:.1f} bps ({commission_rate * 100:.3f}%)</td></tr>'
    )
    doc.append(
        f'      <tr><td>Slippage Rate</td><td class="num">{slippage_rate * 10000:.1f} bps ({slippage_rate * 100:.3f}%)</td></tr>'
    )
    if borrow_fee_rate > 0.0:
        doc.append(
            f'      <tr><td>Borrow Fee Rate</td><td class="num">{borrow_fee_rate * 10000:.1f} bps ({borrow_fee_rate * 100:.3f}% p.a.)</td></tr>'
        )
    if unavailable_borrow:
        doc.append(
            f'      <tr><td>Unavailable Borrow</td><td class="num">{html.escape(", ".join(str(u) for u in unavailable_borrow))}</td></tr>'
        )

    params_raw = spec.get("parameters")
    if isinstance(params_raw, dict):
        for k, v in sorted(params_raw.items()):
            doc.append(
                f'      <tr><td>Strategy Parameter: {html.escape(k)}</td><td class="num">{html.escape(str(v))}</td></tr>'
            )
    doc.append("    </tbody>")
    doc.append("  </table>")

    # Closed Trades Table
    raw_trades = result_data.get("trades")
    trades = raw_trades if isinstance(raw_trades, list) else []
    doc.append(f"  <h2>Closed Trades ({len(trades)})</h2>")
    if trades:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Trade ID</th><th>Security</th><th>Entry Date</th><th>Exit Date</th><th class="num">Entry Price</th><th class="num">Exit Price</th><th class="num">Quantity</th><th class="num">Costs</th><th class="num">PnL ($)</th><th class="num">Return (%)</th></tr></thead>'
        )
        doc.append("      <tbody>")
        for tr in trades:
            if isinstance(tr, dict):
                pnl = float(tr.get("pnl", 0.0))
                ret_pct = float(tr.get("return_pct", 0.0))
                entry_cost = float(tr.get("entry_cost", 0.0))
                exit_proceeds = float(tr.get("exit_proceeds", 0.0))
                doc.append(
                    f'        <tr><td>{html.escape(str(tr.get("trade_id")))}</td><td><strong>{html.escape(str(tr.get("security_id")))}</strong></td><td>{tr.get("entry_date")}</td><td>{tr.get("exit_date")}</td><td class="num">${float(tr.get("entry_price", 0)):.2f}</td><td class="num">${float(tr.get("exit_price", 0)):.2f}</td><td class="num">{float(tr.get("quantity", 0)):.2f}</td><td class="num">${(entry_cost - exit_proceeds + pnl):.2f}</td><td class="num" style="color: {"#166534" if pnl >= 0 else "#991b1b"};"><strong>${pnl:+,.2f}</strong></td><td class="num" style="color: {"#166534" if ret_pct >= 0 else "#991b1b"};">{ret_pct * 100:+.2f}%</td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")
    else:
        doc.append("  <p><em>No round-trip trades completed during this Backtest run.</em></p>")

    # Fills Table
    raw_fills = result_data.get("fills")
    fills = raw_fills if isinstance(raw_fills, list) else []
    doc.append(f"  <h2>Simulated Execution Fills ({len(fills)})</h2>")
    if fills:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Date</th><th>Side</th><th>Security</th><th class="num">Quantity</th><th class="num">Fill Price</th><th class="num">Notional</th><th class="num">Commission</th><th class="num">Slippage</th><th>Rationale</th></tr></thead>'
        )
        doc.append("      <tbody>")
        for fill in fills:
            if isinstance(fill, dict):
                side = str(fill.get("side", "")).upper()
                badge_class = "badge-buy" if side == "BUY" else "badge-sell"
                doc.append(
                    f'        <tr><td>{fill.get("session_date")}</td><td><span class="badge {badge_class}">{side}</span></td><td><strong>{html.escape(str(fill.get("security_id")))}</strong></td><td class="num">{float(fill.get("quantity", 0)):.2f}</td><td class="num">${float(fill.get("price", 0)):.2f}</td><td class="num">${float(fill.get("notional", 0)):,.2f}</td><td class="num">${float(fill.get("commission", 0)):.2f}</td><td class="num">${float(fill.get("slippage_cost", 0)):.2f}</td><td><small>{html.escape(str(fill.get("rationale", "")))}</small></td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")
    else:
        doc.append("  <p><em>No fills occurred during this Backtest run.</em></p>")

    # Mark-to-market Ledger Table
    raw_ledger = result_data.get("ledger")
    ledger = raw_ledger if isinstance(raw_ledger, list) else []
    doc.append(f"  <h2>Daily Mark-to-Market Ledger ({len(ledger)} sessions)</h2>")
    if ledger:
        doc.append('  <div class="scroll-table">')
        doc.append("    <table>")
        doc.append(
            '      <thead><tr><th>Session Date</th><th class="num">Target Weight</th><th>Positions Breakdown</th><th class="num">Cash Balance</th><th class="num">Position Value</th><th class="num">Portfolio Value</th><th class="num">Gross Exp</th><th class="num">Net Exp</th><th class="num">Borrow Fees</th></tr></thead>'
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

                gross_exp = float(row.get("gross_exposure", 0))
                net_exp = float(row.get("net_exposure", 0))
                borrow_fee = float(row.get("borrow_fees", 0.0))
                doc.append(
                    f'        <tr><td>{row.get("session_date")}</td><td class="num">{weight_str}</td><td><small>{pos_summary}</small></td><td class="num">${float(row.get("cash", 0)):,.2f}</td><td class="num">${float(row.get("position_value", 0)):,.2f}</td><td class="num"><strong>${float(row.get("portfolio_value", 0)):,.2f}</strong></td><td class="num">{gross_exp * 100:.0f}%</td><td class="num">{net_exp * 100:.0f}%</td><td class="num">${borrow_fee:,.2f}</td></tr>'
                )
        doc.append("      </tbody>")
        doc.append("    </table>")
        doc.append("  </div>")

    doc.append(
        '  <footer style="margin-top: 40px; color: #94a3b8; font-size: 0.8rem;">Market Research Lab — Personal Investment Analysis Monolith</footer>'
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
                ]
            )

    return output.getvalue()
