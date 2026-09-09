"""
Renders a ProgressReport as a downloadable PDF. Kept deliberately simple --
one column, no charts/branding, just the same content the ReportDetail
page shows, in a form the user can save or share outside the app.
"""

import io
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

_styles = getSampleStyleSheet()

_TITLE = ParagraphStyle("ReportTitle", parent=_styles["Title"], spaceAfter=4)
_META = ParagraphStyle("ReportMeta", parent=_styles["Normal"], textColor=colors.grey, spaceAfter=18)
_HEADING = ParagraphStyle("SectionHeading", parent=_styles["Heading2"], spaceBefore=16, spaceAfter=6)
_BODY = ParagraphStyle("SectionBody", parent=_styles["BodyText"], leading=16)
_BULLET = ParagraphStyle("Bullet", parent=_styles["BodyText"], leading=15)


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
    flow = [Paragraph(title, _HEADING)]
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


def build_report_pdf(report):
    """Returns the rendered PDF as raw bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    story = [
        Paragraph(f"Progress Report #{report.report_number}", _TITLE),
        Paragraph(
            f"{report.period_start} &ndash; {report.period_end} &middot; "
            f"{report.get_report_type_display()} &middot; "
            f"{report.get_triggered_by_display()} &middot; "
            f"Generated {report.created_at.strftime('%b %d, %Y')}",
            _META,
        ),
    ]

    story += _section("Progress Summary", report.progress_summary)
    story += _section("Workout Feedback", report.workout_feedback)
    story += _section("Nutrition Feedback", report.nutrition_feedback)
    story += _section("Key Takeaways", report.key_takeaways)

    recommendations = (report.rule_based_insights or {}).get("overall_recommendations") or []
    if recommendations:
        story.append(Paragraph("Recommendations", _HEADING))
        story.append(
            ListFlowable(
                [
                    ListItem(
                        Paragraph(
                            f"<b>[{_xml_escape(rec.get('priority', '').upper())}]</b> "
                            f"{_xml_escape(rec.get('recommendation', ''))}",
                            _BULLET,
                        )
                    )
                    for rec in recommendations
                ],
                bulletType="bullet",
                leftIndent=14,
            )
        )

    story.append(Spacer(1, 24))
    doc.build(story)
    return buffer.getvalue()