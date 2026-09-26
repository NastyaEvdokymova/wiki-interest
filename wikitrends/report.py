"""One-page PDF report. reportlab is imported lazily."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from . import charts
from .confidence import LIMITATIONS

CONF_LABEL = {"high": "high", "medium": "medium", "low": "low"}


def _styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H", parent=ss["Heading2"], fontSize=12, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["BodyText"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=7.5, leading=9.5, textColor="#555555"))
    return ss


def _register_cyrillic() -> str:
    """reportlab's built-in fonts lack Cyrillic (article titles may use it), so look for DejaVu on the system."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Body", path))
            bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            pdfmetrics.registerFont(TTFont("BodyBold", bold if Path(bold).exists() else path))
            # Without a family, <b> markup inside Paragraph silently loses the bold face.
            pdfmetrics.registerFontFamily(
                "Body", normal="Body", bold="BodyBold", italic="Body", boldItalic="BodyBold"
            )
            return "Body"
    return "Helvetica"


def build_report(state: dict, out_path: str | Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image, KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "The PDF needs reportlab: install the report extra "
            "(`uv sync --extra report`)."
        ) from exc

    font = _register_cyrillic()
    bold = "BodyBold" if font == "Body" else "Helvetica-Bold"
    ss = _styles()
    for style in ("H", "Body", "Small", "Title"):
        ss[style].fontName = bold if style in ("H", "Title") else font

    results = state.get("results", [])
    flow = []

    flow.append(Paragraph(f"Topic interest: {state.get('label', state.get('qid', ''))}", ss["Title"]))
    flow.append(
        Paragraph(
            f"{state.get('qid', '')} · period {state.get('period', '')} · "
            f"metric {state.get('metric', 'share')} · report date {date.today().isoformat()}",
            ss["Small"],
        )
    )
    flow.append(Spacer(1, 4 * mm))

    # One-sentence verdict
    flow.append(Paragraph("Summary", ss["H"]))
    for line in state.get("verdicts", []):
        flow.append(Paragraph(f"• {line}", ss["Body"]))
    flow.append(Spacer(1, 3 * mm))

    # Chart
    with tempfile.TemporaryDirectory() as tmp:
        chart_path = Path(tmp) / "chart.png"
        try:
            charts.monthly_chart(results, chart_path, metric=state.get("metric", "share"))
            flow.append(Image(str(chart_path), width=160 * mm, height=64 * mm))
        except RuntimeError as exc:
            flow.append(Paragraph(f"Chart unavailable: {exc}", ss["Small"]))
        flow.append(Spacer(1, 3 * mm))

        # Per-language table
        flow.append(Paragraph("By language", ss["H"]))
        rows = [["Lang", "Article", "Views/mo", "Per M", "Trend, %/yr", "Signif.", "Confidence"]]
        for r in results:
            if r.get("error"):
                rows.append([r["lang"], r.get("title", ""), "—", "—", "—", "—", "no data"])
                continue
            rows.append(
                [
                    r["lang"],
                    r["title"][:28],
                    f"{r['current']['monthly_views']:,}".replace(",", " "),
                    f"{r['current']['share_per_million']:.2f}",
                    f"{r['trend']['change_pct_per_year']:+.1f}",
                    "yes" if r["trend"]["significant"] else "no",
                    CONF_LABEL.get(r.get("confidence", {}).get("level"), "—"),
                ]
            )
        table = Table(rows, colWidths=[14 * mm, 48 * mm, 24 * mm, 20 * mm, 26 * mm, 16 * mm, 24 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("FONTNAME", (0, 0), (-1, 0), bold),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        flow.append(table)
        flow.append(Spacer(1, 3 * mm))

        # Recommendation
        rec = state.get("recommendation")
        if rec:
            flow.append(Paragraph("Recommendation", ss["H"]))
            flow.append(Paragraph(rec["text"], ss["Body"]))
            # Older sessions have no "why"/"excluded": the report still builds without them.
            if rec.get("why"):
                flow.append(Paragraph("Why this order: " + ". ".join(rec["why"]) + ".", ss["Small"]))
            excluded = state.get("excluded", [])
            if excluded:
                flow.append(
                    Paragraph(
                        "Excluded from the ranking: "
                        + "; ".join(f"<b>{e['lang']}</b>: {e['reason']}" for e in excluded)
                        + ".",
                        ss["Small"],
                    )
                )
            flow.append(
                Paragraph(
                    f"Criteria: {rec['criteria']}. The score is computed by code with this formula; "
                    "low confidence lowers the score.",
                    ss["Small"],
                )
            )
            flow.append(Spacer(1, 3 * mm))

        # Assumptions and limitations
        # Two dense paragraphs so the report stays on one page.
        flow.append(Paragraph("Assumptions and limitations", ss["H"]))
        per_lang = [
            f"<b>{r['lang']}</b>: " + "; ".join(r.get("confidence", {}).get("reasons", [])[:3])
            for r in results
            if r.get("confidence", {}).get("reasons")
        ]
        if per_lang:
            flow.append(Paragraph(". ".join(per_lang) + ".", ss["Small"]))
        flow.append(Paragraph(" ".join(LIMITATIONS), ss["Small"]))

        out = Path(out_path)
        doc = SimpleDocTemplate(
            str(out),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=14 * mm,
            bottomMargin=12 * mm,
            title=f"Topic interest: {state.get('label', '')}",
        )
        # Many languages or long reasons would spill onto page two; shrink to fit instead.
        doc.build([KeepInFrame(doc.width, doc.height, flow, mode="shrink")])
    return out
