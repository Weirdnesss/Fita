"""
Renders a ProgressReport as a downloadable PDF. Uses the app's own brand
colors (see fitness_frontend/src/styles/tokens.css) and surfaces the
structured rule_based_insights numbers (previously only used to ground
the LLM narrative, never actually shown) as a stats panel up top -- so
the PDF reads as this app's document, not a generic text dump of the
same content the ReportDetail page shows.
"""

import io
import re
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Brand colors, matching fitness_frontend/src/styles/tokens.css exactly.
# The *_TINT values are the same colors blended 14% over white (mirrors
# the app's --*-tint CSS vars, which blend over its dark background
# instead -- recomputed for a white page rather than reused as-is).
CHILI = colors.HexColor("#e8491d")
CHILI_DIM = colors.HexColor("#b93a16")
CHILI_TINT = colors.HexColor("#fce6df")
BAMBOO = colors.HexColor("#4c9a6a")
BAMBOO_TINT = colors.HexColor("#e6f1ea")
TURMERIC = colors.HexColor("#d9a441")
TURMERIC_TINT = colors.HexColor("#faf2e4")
INK = colors.HexColor("#1c1f24")
INK_DIM = colors.HexColor("#6e7278")

_styles = getSampleStyleSheet()

# Codepoints an LLM commonly reaches for that mean "hyphen" but aren't
# themselves in cp1252 -- without this, _sanitize would just delete them
# outright (e.g. "3-4 days" -> "34 days", a real number that now reads as
# correct but wrong, which is worse than a visible rendering glitch: at
# least the glitch signals something's off). Deliberately narrow: only
# characters that are semantically "a hyphen" get normalized this way.
# En dash (U+2013) and em dash (U+2014) are excluded on purpose -- they
# already render fine (they're in cp1252) and have distinct typographic
# meaning (ranges, parenthetical breaks) that a hyphen doesn't share, so
# collapsing them here would lose real information, not just fix a glitch.
_HYPHEN_VARIANTS = str.maketrans({
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\u2012": "-",  # FIGURE DASH
    "\u2212": "-",  # MINUS SIGN
})

# The report prompt now asks the LLM for "62.8 kg" not "62.8kg", but that's
# a request, not a guarantee -- this is the same defense-in-depth as the
# hyphen normalization above: fix it at the source AND don't depend on
# compliance. `%` is deliberately excluded -- "55 %" would look wrong to
# most readers; convention keeps that one tight against the number.
_UNIT_SPACING = re.compile(r"(?<=[0-9])(kg|kcal|lbs?|cm|min|g)\b", re.IGNORECASE)


def _fix_unit_spacing(text):
    return _UNIT_SPACING.sub(r" \1", text)


def _sanitize(text):
    """
    Strips any character the base Helvetica font can't render (emoji,
    most symbol/dingbat ranges, box-drawing characters, etc.) -- those
    show up as a solid black placeholder glyph ("tofu") instead of
    failing loudly, which is worse: a silent black box in the middle of
    a sentence, not an error anyone would notice at generation time.
    This content is LLM-generated narration (progress_summary,
    workout_feedback, nutrition_feedback, key_takeaways,
    recommendations) -- free text the app doesn't otherwise constrain --
    so it's sanitized once here rather than trusting every caller to
    remember to.

    cp1252 (Windows-1252), not plain latin-1: PDF's WinAnsiEncoding is
    essentially cp1252, and the two differ exactly in the range that
    matters most for LLM output -- cp1252 has "smart" typography
    (curly quotes, en/em dashes, ellipsis, bullet) in 0x80-0x9F, while
    true latin-1 leaves that range as unprintable control characters
    and would silently drop all of it too. Genuine accented Latin
    characters (é, ñ, ü, ...) survive either way, since those are
    real codepoints in both encodings, not the thing being filtered.
    """
    text = text.translate(_HYPHEN_VARIANTS)
    text = _fix_unit_spacing(text)
    return text.encode("cp1252", errors="ignore").decode("cp1252")


def _collapse_spaces(text):
    """
    A stripped character sometimes had spaces on either side of it in
    the original text (e.g. "muscle \U0001F4AA gain") -- dropping just
    the emoji would otherwise leave a double space behind. Doesn't touch
    intentional newlines (_section splits key_takeaways on those before
    this ever runs), only horizontal whitespace.
    """
    return re.sub(r"[ \t]+", " ", text)

_WORDMARK = ParagraphStyle("Wordmark", parent=_styles["Title"], textColor=colors.white, fontSize=20, leading=24, spaceAfter=2)
_REPORT_TITLE = ParagraphStyle("ReportTitle", parent=_styles["Normal"], textColor=colors.white, fontSize=13, leading=16)
_META = ParagraphStyle("ReportMeta", parent=_styles["Normal"], textColor=INK_DIM, fontSize=9, spaceBefore=10, spaceAfter=18)
_HEADING = ParagraphStyle("SectionHeading", parent=_styles["Heading2"], textColor=CHILI_DIM, spaceBefore=18, spaceAfter=2)
_BODY = ParagraphStyle("SectionBody", parent=_styles["BodyText"], textColor=INK, leading=16)
_BULLET = ParagraphStyle("Bullet", parent=_styles["BodyText"], textColor=INK, leading=15)
_STAT_VALUE = ParagraphStyle("StatValue", parent=_styles["Normal"], fontSize=18, leading=22, alignment=1, fontName="Helvetica-Bold")
_STAT_LABEL = ParagraphStyle("StatLabel", parent=_styles["Normal"], fontSize=8, leading=10, alignment=1, textColor=INK_DIM)
_BADGE = ParagraphStyle("Badge", parent=_styles["Normal"], fontSize=8, leading=10, alignment=1, textColor=colors.white, fontName="Helvetica-Bold")


def _section(title, body_text):
    """One narrative field -- a heading plus its paragraph, or a bulleted
    list if the text is newline-separated (key_takeaways).

    body_text is LLM-generated free text, not developer-authored markup --
    it's escaped before going into Paragraph() (which parses a real,
    if small, XML-like markup language) so a stray '<b>' or other
    tag-shaped fragment in the model's output can't raise a parse error
    and crash PDF export. <br/> is reinserted for line breaks *after*
    escaping, so it still renders as an actual line break, not literal
    text.
    """
    if not body_text:
        return []
    body_text = _sanitize(body_text)
    body_text = _collapse_spaces(body_text)
    flow = [
        Paragraph(title, _HEADING),
        HRFlowable(width="100%", thickness=1.2, color=CHILI, spaceAfter=8),
    ]
    lines = [line.strip("-* ").strip() for line in body_text.split("\n") if line.strip()]
    if len(lines) > 1:
        flow.append(
            ListFlowable(
                [ListItem(Paragraph(_xml_escape(line), _BULLET)) for line in lines],
                bulletType="bullet",
                leftIndent=14,
            )
        )
    else:
        flow.append(Paragraph(_xml_escape(body_text).replace("\n", "<br/>"), _BODY))
    return flow


def _stat_card(value, label, accent_tint):
    """One cell of the stats-at-a-glance row: a big number over a small
    label, on a light brand-tinted background. Built as a nested single-cell
    Table (not a Paragraph) so it gets its own background color and padding
    independent of the outer row's cell spacing.
    """
    inner = Table(
        [[Paragraph(value, _STAT_VALUE)], [Paragraph(label, _STAT_LABEL)]],
        colWidths=[1.5 * inch],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_tint),
                ("TOPPADDING", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ]
        )
    )
    return inner


def _stats_panel(insights):
    """
    Pulls the same key_metrics numbers that already ground the LLM
    narrative (see rule_based_analyzer.py) into a visible row of stat
    cards -- previously computed but never actually shown to the user
    anywhere in the PDF.
    """
    nutrition = insights.get("nutrition_insights") or {}
    workout = insights.get("workout_insights") or {}
    weight = insights.get("weight_insights") or {}

    cards = []
    if workout.get("status") == "analyzed":
        m = workout["key_metrics"]
        cards.append(_stat_card(f"{m['workout_frequency']}/wk", "Workout Frequency", BAMBOO_TINT))
        cards.append(_stat_card(str(m["total_workouts"]), "Total Workouts", BAMBOO_TINT))
    if nutrition.get("status") == "analyzed":
        cards.append(_stat_card(f"{nutrition['overall_adherence']:.0f}%", "Nutrition Adherence", TURMERIC_TINT))
    if weight.get("status") == "analyzed" and weight["key_metrics"]["entries_logged"] >= 2:
        m = weight["key_metrics"]
        change = m["change_kg"]
        sign = "+" if change > 0 else ""
        cards.append(_stat_card(f"{sign}{change} kg", "Weight Change", CHILI_TINT))

    if not cards:
        return []

    # Up to 4 per row; wrap onto a second row if there are more.
    rows = [cards[i:i + 4] for i in range(0, len(cards), 4)]
    flow = [Paragraph("Stats at a Glance", _HEADING), HRFlowable(width="100%", thickness=1.2, color=CHILI, spaceAfter=8)]
    for row in rows:
        table = Table([row], colWidths=[1.6 * inch] * len(row))
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(table)
        flow.append(Spacer(1, 8))
    return flow


_PRIORITY_COLORS = {"HIGH": CHILI, "MEDIUM": TURMERIC, "LOW": BAMBOO}


def _recommendations_section(recommendations):
    if not recommendations:
        return []
    flow = [
        Paragraph("Recommendations", _HEADING),
        HRFlowable(width="100%", thickness=1.2, color=CHILI, spaceAfter=8),
    ]
    for rec in recommendations:
        priority = (rec.get("priority") or "").upper()
        badge_color = _PRIORITY_COLORS.get(priority, INK_DIM)
        badge = Table([[Paragraph(priority or "-", _BADGE)]], colWidths=[0.7 * inch])
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), badge_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        row = Table(
            [[badge, Paragraph(_xml_escape(_collapse_spaces(_sanitize(rec.get("recommendation", "")))), _BODY)]],
            colWidths=[0.8 * inch, 5.4 * inch],
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        flow.append(KeepTogether(row))
    return flow


def _header_band(report):
    """A colored title block, standing in for the old plain black Title
    text -- this is the one piece of the layout that only needs to
    appear once, at the top of page 1 (unlike the footer, which repeats
    on every page via the onPage callbacks in build_report_pdf)."""
    title = Table(
        [[Paragraph("FITNESS ASSISTANT", _WORDMARK)],
         [Paragraph(f"Progress Report #{report.report_number}", _REPORT_TITLE)]],
        colWidths=[6.5 * inch],
    )
    title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CHILI),
        ("TOPPADDING", (0, 0), (-1, 0), 18),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
    ]))
    return title


def _footer(canvas, doc):
    """Drawn on every page via onFirstPage/onLaterPages -- a thin brand
    rule plus page number, so a multi-page report doesn't just trail
    off with no page context once printed or saved standalone."""
    canvas.saveState()
    canvas.setStrokeColor(CHILI_TINT)
    canvas.setLineWidth(1)
    canvas.line(0.75 * inch, 0.6 * inch, letter[0] - 0.75 * inch, 0.6 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(INK_DIM)
    canvas.drawString(0.75 * inch, 0.4 * inch, "Fitness Assistant")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_report_pdf(report):
    """Returns the rendered PDF as raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0,
        bottomMargin=0.9 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    story = [
        _header_band(report),
        Paragraph(
            f"{report.period_start} &ndash; {report.period_end} &middot; "
            f"{report.get_report_type_display()} &middot; "
            f"{report.get_triggered_by_display()} &middot; "
            f"Generated {report.created_at.strftime('%b %d, %Y')}",
            _META,
        ),
    ]

    insights = report.rule_based_insights or {}
    story += _stats_panel(insights)

    story += _section("Progress Summary", report.progress_summary)
    story += _section("Workout Feedback", report.workout_feedback)
    story += _section("Nutrition Feedback", report.nutrition_feedback)
    story += _section("Key Takeaways", report.key_takeaways)
    story += _recommendations_section(insights.get("overall_recommendations") or [])

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
