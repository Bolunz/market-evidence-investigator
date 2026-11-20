"""Render the evidence report (Markdown + self-contained HTML with charts) and run artefacts."""
from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SECTION_TITLES = {
    "A_consumer_signal": "A. Consumer signal",
    "B_historical_context": "B. Historical context",
    "C_market_response": "C. Historical market response",
    "D_sales_evidence": "D. Observable sales and complaint evidence",
    "E_evidence_assessment": "E. Evidence assessment",
    "F_opportunity_hypotheses": "F. Opportunity hypotheses (for analyst evaluation)",
}
LEVEL_LABEL = {"observation": "Observation", "association": "Statistical association",
               "explanation": "Possible explanation", "hypothesis": "Opportunity hypothesis",
               "method_note": "Method note", "evidence_gap": "Evidence gap"}
PATH_TEXT = {
    "direct_response": "Direct market-response path: products positioned on the need were found and examined.",
    "no_direct_response": "No product in the focus segment was positioned on the need (specification path "
                          "not implemented in this version).",
    "insufficient_signal": "Insufficient evidence: no material, statistically supported complaint increase.",
    "not_assessed_market_response": "Not assessed: no sell-out or product-document source is connected. This "
                                    "is a data-availability boundary, not a finding that evidence is weak.",
    "not_assessed_signal": "Not assessed: no consumer-signal source is connected.",
}


METHOD_NOTES = [
    "- Unit of analysis is the PRODUCT, in both comparisons. Sales: each product's mean share of segment "
    "sell-out over its own first 12 months since first observed sale (cohort products enter within +/-6 months, "
    "so calendar windows differ by up to 6 months; share of segment removes common seasonality and market trend). "
    "Complaints: every product's rate over the SAME calendar months (the target's first 12 months), so "
    "market-wide complaint shifts are controlled but cohort products are at different lifecycle ages. The cohort "
    "is the same set for both tests; products with fewer than 30 comments are dropped from the complaint test "
    "(both n are reported).",
    "- Dependencies not modelled: products from the same manufacturer; cohort products sharing calendar shocks; "
    "segment shares summing to one (a strong product slightly lowers others' shares).",
    "- These are aggregate, product-level relationships. They do not describe individual consumers: a lower "
    "complaint rate among a product's commenters does not show that individual buyers chose it for battery life.",
    "- Test families (Benjamini-Hochberg within each): signal screening; confirmatory sales tests; confirmatory "
    "complaint tests; sensitivity + exploratory tests. Families are defined by the question a test answers; "
    "the pooled q across all tests and the grade under pooled correction are shown for comparison.",
]


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _charts(ledger, state) -> list[tuple[str, str, str]]:
    """(title, base64 png, evidence ids) for signal and sales evidence."""
    charts = []
    trends = [e for e in ledger.entries if e.tool == "signal_trend" and e.detail.get("series")]
    if trends:
        fig, ax = plt.subplots(figsize=(7.5, 3.4))
        focus = (state.get("plan") or {}).get("focus_segment")
        for e in trends:
            s = e.detail["series"]
            x = [r["period"] for r in s]
            y = [r["rate"] * 100 for r in s]
            lo = [r["ci_low"] * 100 for r in s]
            hi = [r["ci_high"] * 100 for r in s]
            seg = e.params.get("segment")
            lw = 2.4 if seg == focus else 1.2
            ax.plot(x, y, marker="o", lw=lw, label=f"{seg} ({e.evidence_id})")
            ax.fill_between(x, lo, hi, alpha=0.15)
        ax.set_ylabel("complaints per 100 comments")
        ax.set_title(f"{trends[0].params['theme'].title()} complaint rate by half-year (95% CI)")
        ax.legend(fontsize=7, frameon=False)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.grid(alpha=0.2)
        charts.append(("Consumer signal over time", _fig_to_b64(fig), ",".join(e.evidence_id for e in trends)))
    for e in ledger.entries:
        if e.tool != "launch_trajectory" or "target" not in e.detail:
            continue
        d = e.detail
        pct = lambda arr: [float("nan") if v is None else v * 100 for v in arr]  # noqa: E731
        fig, ax = plt.subplots(figsize=(6.5, 3.2))
        x = d["aligned_month"]
        ax.fill_between(x, pct(d["cohort_p25"]), pct(d["cohort_p75"]),
                        alpha=0.25, label="cohort interquartile range")
        ax.plot(x, pct(d["cohort_median"]), lw=1.5, label="cohort median")
        ax.plot(x, pct(d["target"]), lw=2.4, marker="o",
                label=e.params["product_id"])
        ax.set_xlabel("months since first observed sale")
        ax.set_ylabel("share of segment sell-out (%)")
        suffix = " (price-and-volume months excluded)" if e.params.get("exclude_price_volume_months") else ""
        ax.set_title(f"{e.params['product_id']} vs launch cohort{suffix}", fontsize=10)
        ax.legend(fontsize=7, frameon=False)
        ax.grid(alpha=0.2)
        charts.append((f"Launch-aligned sales: {e.params['product_id']}{suffix}", _fig_to_b64(fig), e.evidence_id))
    return charts


def build_markdown(state, checks, ledger, meta) -> str:
    claims = {c["claim_id"]: c for c in state["draft"]["claims"]}
    status = {c["claim_id"]: c for c in checks}
    lines = [f"# {state['draft']['title']}", ""]
    lines += [f"> **Run mode:** {meta['mode_label']} · **Data:** {meta['data_label']}",
              f"> **Path:** {PATH_TEXT.get(state.get('path'), state.get('path'))}", ""]
    if meta.get("synthetic"):
        lines += ["> All data in this report are synthetic (fictional manufacturers, models and figures). Passing "
                  "the synthetic evaluation shows the method and guardrails work; it does not establish "
                  "real-world validity.", ""]
    lines += ["Every statement below passed evidence verification. Each is labelled as an observation, a "
              "statistical association, a possible explanation, or an opportunity hypothesis, and cites "
              "ledger evidence (E###). Causal conclusions are not produced.", ""]
    for sec, title in SECTION_TITLES.items():
        items = [c for c in claims.values() if c["section"] == sec and status[c["claim_id"]]["status"] == "verified"]
        lines += [f"## {title}", ""]
        if not items:
            lines += ["_No verified statements in this section._", ""]
        for c in items:
            ids = sorted({i for a in c["assertions"] for i in a["evidence_ids"]})
            lines.append(f"- **{LEVEL_LABEL[c['level']]}** - {c['text']} `[{', '.join(ids) or 'no data citation'}]`")
        lines.append("")
    if state["draft"].get("follow_ups"):
        lines += ["### Suggested follow-up investigations", ""] + [f"- {f}" for f in state["draft"]["follow_ups"]] + [""]
    flagged = [c for c in checks if c["status"] == "flagged"]
    lines += ["## Flagged statements (failed verification; NOT findings)", ""]
    if not flagged:
        lines += ["_None._", ""]
    for c in flagged:
        lines.append(f"- ~~{claims[c['claim_id']]['text']}~~  \n  _Reason:_ {'; '.join(c['problems'])}")
    lines.append("")
    lines += ["## Evidence assessment (code rubric)", "",
              "| Subject | Grade | Grade (pooled FDR) | Sales | Complaints | First observed sale | Contradiction | Notes |",
              "|---|---|---|---|---|---|---|---|"]
    for e in ledger.by_type("confidence_assessment"):
        v = e.values
        if "product_id" in v:
            lines.append(f"| {v['product_id']} ({e.evidence_id}) | {v['grade']} | {v.get('grade_pooled', '')} | "
                         f"{v['sales_status']} | "
                         f"{v['complaint_status']} | {v['first_sale_reliability']} | {v['contradiction']} | "
                         f"{v['reasons']} |")
        else:
            lines.append(f"| {v.get('theme', '')} signal, {v.get('segment')} ({e.evidence_id}) | {v['grade']} | - | - | "
                         f"- | - | - | {v.get('reasons', '')} |")
    lines += ["", "Grades: Moderate (sales advantage AND lower complaints) > Weak (one of the two) > Not supported > "
              "Insufficient. Moderate is the ceiling for observational data. Only confirmatory (pre-declared) tests "
              "can support a grade; sensitivity re-runs can only restrict it; exploratory tests are reported, not graded.",
              "", "### Method notes: unit of analysis and test families", "", *METHOD_NOTES, ""]
    lines += ["## Investigation trail", ""]
    for t in meta["trace"]:
        lines.append(f"{t['step']}. `[{t['node']}:{t['kind']}]` {t['text']}")
    lines += ["", "## Evidence ledger", "",
              "| ID | Tool | Requested by | Summary | p | q (family) | q (pooled) | Status | Family |",
              "|---|---|---|---|---|---|---|---|---|"]
    for e in ledger.entries:
        p = f"{e.p_value:.3f}" if e.p_value is not None else ""
        q = f"{e.q_value:.3f}" if e.q_value is not None else ""
        qp = f"{e.q_pooled:.3f}" if getattr(e, "q_pooled", None) is not None else ""
        lines.append(f"| {e.evidence_id} | {e.tool} | {e.requested_by} | {e.summary.replace('|', '/')} | {p} | {q} | "
                     f"{qp} | {e.hypothesis_status or ''} | {getattr(e, 'test_family', '') or ''} |")
    u = meta.get("usage") or {}
    lines += ["", "## Run metadata", "", f"- Models: {meta.get('models')}",
              f"- LLM calls: {u.get('calls', 0)}; input tokens: {u.get('input_tokens', 0)}; "
              f"output tokens: {u.get('output_tokens', 0)}",
              f"- Tests run: {len(ledger.tests())} (Benjamini-Hochberg within each family; pooled q shown alongside)",
              f"- Cost: ${u.get('cost_usd', 0):.4f} (list prices; limits: {meta.get('limits')})",
              f"- Data file hashes: {json.dumps(ledger.data_hashes)}", ""]
    return "\n".join(lines)


def _md_to_html(md_text: str, charts) -> str:
    out, in_table, in_list = [], False, False
    for line in md_text.splitlines():
        esc = html.escape(line)
        esc = esc.replace("`", "")
        if line.startswith("|"):
            if set(line.replace("|", "").strip()) <= {"-"}:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = html.escape(line[2:]).replace("`", "")
            item = item.replace("**", "<b>", 1).replace("**", "</b>", 1)
            if item.startswith("~~"):
                item = "<s>" + item[2:].replace("~~", "</s>", 1)
            out.append(f"<li>{item}</li>")
            continue
        if in_list and not line.startswith("  "):
            out.append("</ul>")
            in_list = False
        if line.startswith("# "):
            out.append(f"<h1>{esc[2:]}</h1>")
        elif line.startswith("## "):
            title = esc[3:]
            out.append(f"<h2>{title}</h2>")
            if title.startswith("A. Consumer signal") or title.startswith("D. Observable"):
                for ct, b64, ids in charts:
                    if (title.startswith("A.") and ct.startswith("Consumer")) or \
                       (title.startswith("D.") and ct.startswith("Launch")):
                        out.append(f'<figure><img src="data:image/png;base64,{b64}"/>'
                                   f"<figcaption>{html.escape(ct)} [{ids}]</figcaption></figure>")
        elif line.startswith("### "):
            out.append(f"<h3>{esc[4:]}</h3>")
        elif line.startswith("> "):
            out.append(f"<p class='note'>{esc[5:].replace('**', '')}</p>")
        elif line.strip():
            out.append(f"<p>{esc.replace('**', '')}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:980px;margin:2rem auto;"
           "padding:0 1rem;color:#1d1d1f;line-height:1.5}h1{font-size:1.6rem}h2{margin-top:2rem;border-bottom:1px "
           "solid #ddd;padding-bottom:.2rem}table{border-collapse:collapse;font-size:.8rem;width:100%}"
           "td,th{border:1px solid #ddd;padding:4px 6px;vertical-align:top}th{background:#f5f5f7}"
           ".note{background:#f5f5f7;padding:.5rem .8rem;border-left:3px solid #888}"
           "figure{margin:1rem 0}img{max-width:100%}figcaption{font-size:.75rem;color:#666}s{color:#a00}")
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Evidence report</title><style>{css}</style>" \
           f"</head><body>{''.join(out)}</body></html>"


def write_outputs(out_dir: Path, state: dict, checks: list, ledger, meta: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_markdown(state, checks, ledger, meta)
    (out_dir / "report.md").write_text(md)
    (out_dir / "report.html").write_text(_md_to_html(md, _charts(ledger, state)))
    ledger.save(out_dir / "ledger.json")
    (out_dir / "state.json").write_text(json.dumps(state, indent=2, default=str))
    (out_dir / "checks.json").write_text(json.dumps(checks, indent=2))
    with (out_dir / "trace.jsonl").open("w") as f:
        for t in meta["trace"]:
            f.write(json.dumps(t, default=str) + "\n")
    run_meta = {k: v for k, v in meta.items() if k != "trace"}
    (out_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2, default=str))
    return {"report_md": str(out_dir / "report.md"), "report_html": str(out_dir / "report.html")}
