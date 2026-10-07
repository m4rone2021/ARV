"""
ARV Report Builder — Clean, professional PDF + Excel generation.
Aquarian Rock Ventures, Inc.
"""

import io
import re
from datetime import datetime, date, timedelta
from pathlib import Path as _Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, legal, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage, KeepTogether,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)


# ============================================================================
# BRAND
# ============================================================================
COMPANY = "Aquarian Rock Ventures, Inc."
TAGLINE = "General Engineering - Design, Build and Consultancy"
LOCATION = "Brgy. Lamak, Hilongos, Leyte, Philippines"
PHONE = "0917 724 4079 / 0963 116 9032"
EMAIL = "soarhigh03albert@gmail.com"

ASSETS = _Path(__file__).resolve().parent.parent / "assets"

# Brand palette — HDPE / water industry
NAVY = colors.HexColor("#0D3B66")
NAVY_DARK = colors.HexColor("#082A4A")
CYAN = colors.HexColor("#1B98E0")
AQUA = colors.HexColor("#7AC4E8")
PALE_BLUE = colors.HexColor("#C6E5F5")
SECTION_BG = colors.HexColor("#D6EAF8")
RED = colors.HexColor("#E63946")
GREEN = colors.HexColor("#2A9D8F")
AMBER = colors.HexColor("#F4A261")
LIGHT_BLUE = colors.HexColor("#E8F4FB")
GREY_LIGHT = colors.HexColor("#F8FAFC")
GREY_MED = colors.HexColor("#DCE2EC")
GREY_TEXT = colors.HexColor("#5A6472")
INK = colors.HexColor("#1F2937")

PAGE_SIZE = portrait(letter)

_RASTERIZE_ENABLED = True


# ============================================================================
# HELPERS
# ============================================================================
def _find_logo():
    for name in ("logo.png", "logo.jpg", "logo.jpeg"):
        p = ASSETS / name
        if p.exists():
            return p
    return None


def _clean(v):
    """Escape for reportlab Paragraphs. Collapses double-escapes."""
    if v is None:
        return ""
    s = str(v)
    if s.lower() in ("none", "nan", "nat", "<na>"):
        return ""
    # Strip ALL levels of HTML entity encoding for &amp;
    import re as _re2
    # Repeatedly un-escape until stable
    prev = None
    while prev != s:
        prev = s
        s = s.replace("&amp;amp;", "&amp;")
        s = s.replace("&amp;", "&")
        s = s.replace("&lt;", "<")
        s = s.replace("&gt;", ">")
    return s.replace("&", "&amp;")


def _fmt_qty(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return _clean(x)
    return str(int(x)) if x == int(x) else str(round(x, 3))


def _fmt_dt(v):
    s = str(v or "")
    if not s or s.lower() in ("none", "nan"):
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:19]


def _parse_date(d):
    if not d:
        return None
    try:
        return datetime.fromisoformat(str(d).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(d).split()[0], "%Y-%m-%d").date()
        except Exception:
            return None


def _watermark_text():
    return "AQUARIAN ROCK VENTURES, INC.  \u2022  ORIGINAL COPY  \u2022  DO NOT MODIFY"


def _generate_report_id():
    import random as _random
    now = datetime.now()
    suffix = "".join(_random.choices("0123456789ABCDEF", k=4))
    return "RPT-" + now.strftime("%Y%m%d-%H%M") + "-" + suffix


def _compute_hash(data_bytes):
    import hashlib
    return hashlib.sha256(data_bytes).hexdigest()[:12].upper()


def _draw_watermark(canvas, page_size, report_id=None, show_logo=True):
    w, h = page_size
    canvas.saveState()

    # Faint logo
    if show_logo:
        logo = _find_logo()
        if logo:
            try:
                canvas.setFillAlpha(0.04)
                canvas.setStrokeAlpha(0.04)
                lw = w * 0.55
                lh = lw * 0.38
                canvas.drawImage(str(logo),
                                 (w - lw) / 2, (h - lh) / 2,
                                 width=lw, height=lh,
                                 preserveAspectRatio=True, mask="auto")
                canvas.setFillAlpha(1.0)
                canvas.setStrokeAlpha(1.0)
            except Exception:
                pass

    # Diagonal tiled text
    canvas.setFillColor(NAVY)
    canvas.setFillAlpha(0.08)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.translate(w / 2, h / 2)
    canvas.rotate(30)
    text = _watermark_text()
    text_width = canvas.stringWidth(text, "Helvetica-Bold", 16)
    step_x = text_width + 40
    step_y = 60
    for y in range(-int(h), int(h) + step_y, step_y):
        for x in range(-int(w), int(w) + int(step_x), int(step_x)):
            canvas.drawString(x, y, text)
    canvas.setFillAlpha(1.0)
    canvas.restoreState()


def rasterize_pdf(pdf_bytes, dpi=150):
    """Convert each PDF page to an image and rebuild the PDF (anti-tamper)."""
    try:
        import fitz
    except ImportError:
        return pdf_bytes
    try:
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        dst_doc = fitz.open()
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for page in src_doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            new_page = dst_doc.new_page(width=page.rect.width, height=page.rect.height)
            rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
            new_page.insert_image(rect, stream=img_bytes)
        out = dst_doc.tobytes()
        src_doc.close()
        dst_doc.close()
        return out
    except Exception as e:
        print("[rasterize_pdf] Failed:", e)
        return pdf_bytes


# ============================================================================
# PAGE TEMPLATE
# ============================================================================
class ARVDocTemplate(BaseDocTemplate):
    def __init__(self, buffer, report_title, report_id=None, content_hash=None, **kwargs):
        self.report_title = report_title
        self.report_id = report_id or _generate_report_id()
        self.content_hash = content_hash or "PENDING"
        super().__init__(buffer, **kwargs)
        cover_frame = Frame(self.leftMargin, self.bottomMargin,
                            self.width, self.height - 20 * mm, id="cover")
        content_frame = Frame(self.leftMargin, self.bottomMargin,
                              self.width, self.height, id="content")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=self._cover_page),
            PageTemplate(id="content", frames=[content_frame], onPage=self._content_page),
        ])

    def _cover_page(self, canvas, doc):
        canvas.saveState()
        w, h = PAGE_SIZE
        _draw_watermark(canvas, PAGE_SIZE, self.report_id)
        canvas.setFillColor(GREY_TEXT)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(w / 2, 18 * mm,
            "ORIGINAL COPY \u2022 Any modification voids this report.")
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawCentredString(w / 2, 13 * mm,
            "Report ID: " + self.report_id + "   |   Integrity: " + self.content_hash)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(GREY_TEXT)
        canvas.drawCentredString(w / 2, 9 * mm,
            "Generated by ARV Inventory Management System \u2022 "
            + datetime.now().strftime("%Y-%m-%d %H:%M"))
        canvas.restoreState()

    def _content_page(self, canvas, doc):
        canvas.saveState()
        w, h = PAGE_SIZE
        _draw_watermark(canvas, PAGE_SIZE, self.report_id)

        # Header band
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 15 * mm, w, 15 * mm, fill=1, stroke=0)
        canvas.setFillColor(RED)
        canvas.rect(0, h - 16 * mm, w * 0.5, 1 * mm, fill=1, stroke=0)
        canvas.setFillColor(AMBER)
        canvas.rect(w * 0.5, h - 16 * mm, w * 0.5, 1 * mm, fill=1, stroke=0)

        logo = _find_logo()
        if logo:
            try:
                canvas.drawImage(str(logo), 10 * mm, h - 13 * mm,
                                 width=22 * mm, height=10 * mm,
                                 preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawRightString(w - 10 * mm, h - 7 * mm, COMPANY)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#B8C4D8"))
        canvas.drawRightString(w - 10 * mm, h - 11 * mm, self.report_title)

        # Footer
        canvas.setFillColor(GREY_LIGHT)
        canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(GREY_MED)
        canvas.rect(0, 10 * mm, w, 0.3 * mm, fill=1, stroke=0)

        canvas.setFillColor(GREY_TEXT)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(10 * mm, 5 * mm, "Hilongos, Leyte  \u2022  0917 724 4079")

        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.drawCentredString(
            w / 2, 5 * mm,
            "Report ID: " + self.report_id + "   |   Integrity: " + self.content_hash,
        )
        canvas.setFillColor(GREY_TEXT)
        canvas.setFont("Helvetica", 5.5)
        canvas.drawCentredString(
            w / 2, 2.5 * mm,
            "ORIGINAL COPY \u2014 Do not modify. Request a fresh original for authentic version.",
        )

        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawRightString(w - 10 * mm, 5 * mm, "Page " + str(canvas.getPageNumber()))
        canvas.setFillColor(GREY_TEXT)
        canvas.setFont("Helvetica", 6)
        canvas.drawRightString(w - 10 * mm, 2 * mm,
                               datetime.now().strftime("%Y-%m-%d %H:%M"))
        canvas.restoreState()


# ============================================================================
# STYLE HELPERS
# ============================================================================
def _style_section():
    return ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=12,
                          textColor=colors.white, alignment=0, leading=14)


def _style_body():
    return ParagraphStyle("b", fontName="Helvetica", fontSize=9.5,
                          textColor=INK, leading=13)


def _style_small():
    return ParagraphStyle("sm", fontName="Helvetica", fontSize=8,
                          textColor=GREY_TEXT, leading=11)


def _style_label():
    return ParagraphStyle("lb", fontName="Helvetica-Bold", fontSize=9,
                          textColor=NAVY, leading=12)


# ============================================================================
# FLOWABLE BUILDERS
# ============================================================================
def _section_bar(text, color=NAVY):
    tbl = Table([[Paragraph(text, _style_section())]],
                colWidths=[505], rowHeights=[22])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _kpi_row(summary):
    items = list(summary.items())[:5]
    if not items:
        return Spacer(1, 1)
    card_w = 515 / len(items)
    cards = []
    for k, v in items:
        card = Table([
            [Paragraph(str(k).upper(), ParagraphStyle(
                "kl", fontName="Helvetica-Bold", fontSize=7,
                textColor=colors.HexColor("#B8C4D8"), alignment=1, leading=9))],
            [Paragraph(_fmt_qty(v), ParagraphStyle(
                "kv", fontName="Helvetica-Bold", fontSize=18,
                textColor=colors.white, alignment=1, leading=20))],
        ], colWidths=[card_w - 3])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (0, 0), 8),
            ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 1), (0, 1), 0),
            ("BOTTOMPADDING", (0, 1), (0, 1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        cards.append(card)
    outer = Table([cards], colWidths=[card_w] * len(cards))
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return outer


def _info_grid(rows, label_w=200, value_w=315):
    data = [[Paragraph(str(k), _style_label()),
             Paragraph(str(v), _style_body())] for k, v in rows]
    t = Table(data, colWidths=[label_w, value_w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, GREY_MED),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY_MED),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _data_table(headers, rows, col_widths=None, font_size=7.5, header_size=8, numeric_cols=None):
    """Single Table. Callers chunk manually to control pagination."""
    FULL_WIDTH = 505

    def _trunc(v, n=120):
        s = _clean(v)
        return s if len(s) <= n else s[: n - 1] + "\u2026"

    n = len(headers)
    if col_widths is None:
        col_widths = [FULL_WIDTH / n] * n
    else:
        col_widths = [max(float(w), 20.0) for w in col_widths]
        s = sum(col_widths)
        if s > FULL_WIDTH:
            col_widths = [w * (FULL_WIDTH / s) for w in col_widths]

    numeric_cols = numeric_cols or set()

    header_style = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=header_size,
                                  textColor=colors.white, leading=header_size + 2, alignment=1)
    cell_style = ParagraphStyle("td", fontName="Helvetica", fontSize=font_size,
                                textColor=INK, leading=font_size + 2, alignment=0)
    cell_right = ParagraphStyle("tdr", parent=cell_style, alignment=2)

    data = [[Paragraph(_trunc(h, 40), header_style) for h in headers]]
    for r in rows:
        row_cells = []
        for ci, c in enumerate(r):
            if ci in numeric_cols:
                row_cells.append(Paragraph(_trunc(c), cell_right))
            else:
                row_cells.append(Paragraph(_trunc(c), cell_style))
        data.append(row_cells)

    t = Table(data, colWidths=col_widths, repeatRows=0)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.2, GREY_MED),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY_MED),
    ]))
    return t


def _append_chunked_table(story, headers, rows, col_widths=None,
                          font_size=7.5, header_size=8, numeric_cols=None,
                          chunk_size=10, spacer=4):
    """Append one or more tables to story, one per page.

    Each chunk is preceded by a PageBreak (except the first) so ReportLab
    always starts fresh and the table is never split mid-render.
    """
    if not rows:
        return
    chunks = [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]
    for ci, chunk in enumerate(chunks):
        if ci > 0:
            story.append(PageBreak())
        t = _data_table(headers, chunk, col_widths=col_widths,
                        font_size=font_size, header_size=header_size,
                        numeric_cols=numeric_cols)
        story.append(t)


def _status_color(status):
    s = str(status).upper()
    if s in ("OK", "IN STOCK"):
        return GREEN
    if s == "LOW":
        return AMBER
    if s in ("OUT", "OUT OF STOCK"):
        return RED
    return GREY_MED


# ============================================================================
# SECTION BUILDERS
# ============================================================================
def _build_cover(story, report_type, period_label, prepared_by):
    story.append(Spacer(1, 45 * mm))
    logo = _find_logo()
    if logo:
        try:
            img = RLImage(str(logo), width=95 * mm, height=36 * mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 22 * mm))
        except Exception:
            pass

    story.append(Paragraph(COMPANY, ParagraphStyle(
        "c1", fontName="Helvetica-Bold", fontSize=22, textColor=NAVY,
        alignment=1, spaceAfter=12, leading=28)))
    story.append(Paragraph(TAGLINE, ParagraphStyle(
        "c2", fontName="Helvetica", fontSize=10, textColor=GREY_TEXT,
        alignment=1, spaceAfter=30, leading=14)))

    title_block = Table([
        [Paragraph(report_type.upper(), ParagraphStyle(
            "tt", fontName="Helvetica-Bold", fontSize=22,
            textColor=colors.white, alignment=1, leading=28))],
        [Paragraph(period_label, ParagraphStyle(
            "tp", fontName="Helvetica", fontSize=11,
            textColor=colors.HexColor("#D3DCEC"), alignment=1, leading=15))],
    ], colWidths=[420])
    title_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 22),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 22),
    ]))
    title_block.hAlign = "CENTER"
    story.append(title_block)
    story.append(Spacer(1, 10 * mm))

    meta = Table([
        ["Prepared By", prepared_by, "Date Generated",
         datetime.now().strftime("%B %d, %Y"),
         "Time", datetime.now().strftime("%H:%M")],
    ], colWidths=[55, 105, 60, 105, 30, 60])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE),
        ("BACKGROUND", (2, 0), (2, 0), LIGHT_BLUE),
        ("BACKGROUND", (4, 0), (4, 0), LIGHT_BLUE),
        ("FONT", (0, 0), (0, 0), "Helvetica-Bold", 8),
        ("FONT", (2, 0), (2, 0), "Helvetica-Bold", 8),
        ("FONT", (4, 0), (4, 0), "Helvetica-Bold", 8),
        ("FONT", (1, 0), (1, 0), "Helvetica", 9),
        ("FONT", (3, 0), (3, 0), "Helvetica", 9),
        ("FONT", (5, 0), (5, 0), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (0, 0), NAVY),
        ("TEXTCOLOR", (2, 0), (2, 0), NAVY),
        ("TEXTCOLOR", (4, 0), (4, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY_MED),
        ("LINEAFTER", (0, 0), (0, 0), 0.3, GREY_MED),
        ("LINEAFTER", (1, 0), (1, 0), 0.3, GREY_MED),
        ("LINEAFTER", (2, 0), (2, 0), 0.3, GREY_MED),
        ("LINEAFTER", (3, 0), (3, 0), 0.3, GREY_MED),
        ("LINEAFTER", (4, 0), (4, 0), 0.3, GREY_MED),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    meta.hAlign = "CENTER"
    story.append(meta)
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph(LOCATION + "  |  " + PHONE + "  |  " + EMAIL,
                           ParagraphStyle("foot", fontName="Helvetica", fontSize=8,
                                          textColor=GREY_TEXT, alignment=1)))


def _summary_paragraph(summary, report_type, period_label):
    parts = []
    parts.append("This report provides an overview of inventory activity for <b>"
                 + period_label + "</b> covering <b>" + report_type + "</b>.")
    if summary.get("Total Items"):
        parts.append("The catalog contains <b>" + str(summary["Total Items"])
                     + "</b> unique items totaling <b>"
                     + _fmt_qty(summary.get("Total Units On-Hand", 0))
                     + "</b> units on hand.")
    low = summary.get("Low Stock") or summary.get("Low Stock Items")
    out = summary.get("Out of Stock")
    if low or out:
        parts.append("Status: <b>" + str(low or 0) + "</b> low stock, <b>"
                     + str(out or 0) + "</b> out of stock.")
    if summary.get("Total Transactions"):
        parts.append("Activity: <b>" + str(summary["Total Transactions"])
                     + "</b> total lines.")
    return " ".join(parts)


def _recommendations(summary, snapshot_items, supplier_groups=None):
    """Generate recommendation tuples (level, text)."""
    recs = []

    out_items = []
    low_items = []
    for it in snapshot_items or []:
        st = str(it.get("Status", "")).upper()
        name = it.get("Item", "")
        if st == "OUT":
            out_items.append(name)
        elif st == "LOW":
            low_items.append(name)

    if out_items:
        CHUNK = 25
        chunks = [out_items[i:i + CHUNK] for i in range(0, len(out_items), CHUNK)]
        for ci, chunk in enumerate(chunks):
            names = "  \u2022  ".join(chunk)
            header = (
                "<b>" + str(len(out_items)) + " items are completely out of stock</b>. "
                "Immediate reorder required (part " + str(ci + 1) + " of " + str(len(chunks)) + "):<br/><br/>"
                if len(chunks) > 1 else
                "<b>" + str(len(out_items)) + " items are completely out of stock</b>. "
                "Immediate reorder required:<br/><br/>"
            )
            recs.append(("HIGH", header + "<font color='#5A6472'>" + names + "</font>"))

    if low_items:
        CHUNK = 25
        chunks = [low_items[i:i + CHUNK] for i in range(0, len(low_items), CHUNK)]
        for ci, chunk in enumerate(chunks):
            names = "  \u2022  ".join(chunk)
            header = (
                "<b>" + str(len(low_items)) + " items are below minimum threshold</b>. "
                "Review reorder levels (part " + str(ci + 1) + " of " + str(len(chunks)) + "):<br/><br/>"
                if len(chunks) > 1 else
                "<b>" + str(len(low_items)) + " items are below minimum threshold</b>. "
                "Review reorder levels:<br/><br/>"
            )
            recs.append(("MEDIUM", header + "<font color='#5A6472'>" + names + "</font>"))

    if not out_items and not low_items and summary.get("Total Items"):
        recs.append(("OK", "All items are above minimum thresholds. No immediate action required."))

    if summary.get("Cancelled"):
        recs.append(("MEDIUM", str(summary["Cancelled"])
                     + " scheduled deliveries cancelled this period. Review causes."))

    if not recs:
        recs.append(("OK", "No anomalies detected in this reporting period."))
    return recs


def _rec_bar_color(level):
    return {"HIGH": RED, "MEDIUM": AMBER, "INFO": NAVY, "OK": GREEN}.get(level, GREY_MED)


def _build_recommendations(story, summary, snapshot_items):
    story.append(_section_bar("Recommendations", color=RED))
    story.append(Spacer(1, 5 * mm))
    for level, text in _recommendations(summary, snapshot_items):
        c = _rec_bar_color(level)
        box = Table([[
            Paragraph("<b>" + level + "</b>", ParagraphStyle(
                "lvl", fontName="Helvetica-Bold", fontSize=9,
                textColor=colors.white, alignment=1, leading=11)),
            Paragraph(text, ParagraphStyle(
                "rt", fontName="Helvetica", fontSize=9.5,
                textColor=INK, leading=13)),
        ]], colWidths=[45, 470])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), c),
            ("BACKGROUND", (1, 0), (1, 0), GREY_LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.3, GREY_MED),
        ]))
        story.append(box)
        story.append(Spacer(1, 4 * mm))


def _build_summary_by_category(story, snapshot_items):
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Summary by Category"))
    story.append(Spacer(1, 5 * mm))

    cat_totals = {}
    for item in snapshot_items:
        cat = item.get("Category") or "(Uncategorized)"
        try:
            onhand = float(item.get("On-Hand", 0) or 0)
        except (TypeError, ValueError):
            onhand = 0.0
        cat_totals.setdefault(cat, {"items": 0, "onhand": 0.0, "out": 0, "low": 0})
        cat_totals[cat]["items"] += 1
        cat_totals[cat]["onhand"] += onhand
        st = str(item.get("Status", "")).upper()
        if st == "OUT":
            cat_totals[cat]["out"] += 1
        elif st == "LOW":
            cat_totals[cat]["low"] += 1

    rows = []
    for cat in sorted(cat_totals.keys()):
        d = cat_totals[cat]
        rows.append([cat, str(d["items"]), _fmt_qty(d["onhand"]),
                     str(d["low"]), str(d["out"])])

    # Small table — keep together on one page
    t = _data_table(
        ["Category", "Items", "Total On-Hand", "Low", "Out"],
        rows, col_widths=[240, 60, 100, 55, 60],
        font_size=8, numeric_cols={1, 2, 3, 4})
    story.append(KeepTogether(t))


def _build_summary_by_item_snapshot(story, snapshot_items):
    """Single clean table. ReportLab splits naturally with header repeated."""
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Summary by Item"))
    story.append(Spacer(1, 5 * mm))

    sorted_items = sorted(
        snapshot_items,
        key=lambda r: (str(r.get("Category", "")), str(r.get("Item", ""))),
    )

    # Keep all columns
    if sorted_items and "Min" in sorted_items[0]:
        sorted_items = [{k: v for k, v in r.items() if k != "Min"} for r in sorted_items]

    headers = ["Item", "Category", "Unit", "On-Hand", "Reserved", "Available", "Status"]
    numeric_idx = {3, 4, 5}  # On-Hand, Reserved, Available

    # Build rows
    rows = []
    for r in sorted_items:
        rows.append([
            r.get("Item", ""),
            r.get("Category", ""),
            r.get("Unit", ""),
            _fmt_qty(r.get("On-Hand", 0)),
            _fmt_qty(r.get("Reserved", 0)),
            _fmt_qty(r.get("Available", 0)),
            r.get("Status", ""),
        ])

    # Column widths — totals to 515pt (letter portrait width)
    col_widths = [150, 130, 40, 55, 55, 60, 25]

    # Styles
    header_style = ParagraphStyle(
        "th2", fontName="Helvetica-Bold", fontSize=8,
        textColor=colors.white, leading=10, alignment=1,
    )
    cell_style = ParagraphStyle(
        "td2", fontName="Helvetica", fontSize=8,
        textColor=INK, leading=10,
    )
    cell_right = ParagraphStyle("tdr2", parent=cell_style, alignment=2)
    cell_center = ParagraphStyle("tdc2", parent=cell_style, alignment=1)

    # Build data
    data = [[Paragraph(h, header_style) for h in headers]]
    for r in rows:
        row_cells = []
        for ci, v in enumerate(r):
            if ci in numeric_idx:
                row_cells.append(Paragraph(_clean(v), cell_right))
            elif ci == 6:  # Status column — center aligned
                row_cells.append(Paragraph(_clean(v), cell_center))
            else:
                row_cells.append(Paragraph(_clean(v), cell_style))
        data.append(row_cells)

    # ONE table with repeatRows=1
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.15, GREY_MED),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY_MED),
    ]))

    # Color the status cells
    status_styles = []
    for ri, r in enumerate(rows, start=1):
        st_color = _status_color(r[6])
        status_styles.append(("TEXTCOLOR", (6, ri), (6, ri), st_color))
        status_styles.append(("FONT", (6, ri), (6, ri), "Helvetica-Bold", 8))
    t.setStyle(TableStyle(status_styles))

    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<i>Total: " + str(len(sorted_items)) + " items. Current balance for all categories.</i>",
        ParagraphStyle("foot", fontName="Helvetica-Oblique", fontSize=8,
                       textColor=GREY_TEXT),
    ))


def _build_summary_by_item_tx(story, by_item):
    """For transaction-based reports: Item / Unit / Type / Total Qty"""
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Summary by Item"))
    story.append(Spacer(1, 5 * mm))

    headers = ["Item", "Unit", "Type", "Total Qty"]
    rows = [[
        r.get("Item", ""),
        r.get("Unit", ""),
        r.get("Type", ""),
        _fmt_qty(r.get("Total Qty", 0)),
    ] for r in by_item]

    _append_chunked_table(story, headers, rows,
        col_widths=[230, 60, 90, 90],
        font_size=8, numeric_cols={3})


def _build_low_stock_detail(story, snapshot_items):
    low_items = [r for r in snapshot_items if str(r.get("Status", "")).upper() == "LOW"]
    if not low_items:
        return
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Low Stock Detail", color=AMBER))
    story.append(Spacer(1, 5 * mm))
    rows = []
    for r in low_items:
        try:
            avail = float(r.get("Available", 0) or 0)
            mn = float(r.get("Min", 0) or 0)
        except (TypeError, ValueError):
            avail, mn = 0.0, 0.0
        rows.append([r.get("Item", ""), r.get("Category", ""), r.get("Unit", ""),
                     _fmt_qty(avail), _fmt_qty(mn), _fmt_qty(max(0, mn - avail))])
    _append_chunked_table(story,
        ["Item", "Category", "Unit", "Available", "Min", "Shortage"],
        rows, col_widths=[150, 130, 45, 60, 60, 70],
        font_size=8, numeric_cols={3, 4, 5})


def _build_out_of_stock_detail(story, snapshot_items):
    out_items = [r for r in snapshot_items if str(r.get("Status", "")).upper() == "OUT"]
    if not out_items:
        return
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Out-of-Stock Detail", color=RED))
    story.append(Spacer(1, 5 * mm))
    rows = [[r.get("Item", ""), r.get("Category", ""), r.get("Unit", "")]
            for r in out_items]
    t = _data_table(
        ["Item", "Category", "Unit"], rows,
        col_widths=[230, 200, 85], font_size=8.5)
    story.append(KeepTogether(t))


def _build_deliveries_log(story, deliveries):
    """Deliveries log — grouped by dispatch_id with item breakdown."""
    today = date.today()
    week_ago = today - timedelta(days=7)

    logged_today, completed_today, pending_due, upcoming = [], [], [], []

    for d in deliveries:
        st_val = str(d.get("status", "")).strip()
        exp = _parse_date(d.get("expected_date"))
        comp = _parse_date(d.get("completed_at") or d.get("updated_at"))
        created = _parse_date(d.get("created_at"))

        if created == today:
            logged_today.append(d)
        if st_val == "Completed" and comp == today:
            completed_today.append(d)
        if st_val == "Pending" and exp and exp <= today:
            pending_due.append(d)
        if st_val in ("Pending", "In Transit") and exp and exp > today:
            upcoming.append(d)

    if not logged_today:
        logged_today = [d for d in deliveries
                        if _parse_date(d.get("created_at"))
                        and _parse_date(d.get("created_at")) >= week_ago][:25]
    if not completed_today:
        completed_today = [d for d in deliveries
                           if str(d.get("status", "")).strip() == "Completed"
                           and _parse_date(d.get("completed_at") or d.get("updated_at"))
                           and _parse_date(d.get("completed_at") or d.get("updated_at")) >= week_ago][:25]

    # Styles
    dispatch_style = ParagraphStyle(
        "dh", fontName="Helvetica-Bold", fontSize=10,
        textColor=colors.white, leading=12,
    )
    meta_label_style = ParagraphStyle(
        "ml", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=NAVY, leading=11,
    )
    meta_value_style = ParagraphStyle(
        "mv", fontName="Helvetica", fontSize=8.5,
        textColor=INK, leading=11,
    )
    item_header_style = ParagraphStyle(
        "ih", fontName="Helvetica-Bold", fontSize=8,
        textColor=NAVY, leading=10,
    )
    item_cell_style = ParagraphStyle(
        "ic", fontName="Helvetica", fontSize=8,
        textColor=INK, leading=10,
    )
    item_cell_right = ParagraphStyle("icr", parent=item_cell_style, alignment=2)
    total_style = ParagraphStyle(
        "tt", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, leading=11,
    )

    def render_dispatch_group(dispatch_id, items):
        """Render one dispatch batch: header + meta + item breakdown + subtotal."""
        first = items[0]
        destination = first.get("destination") or "-"
        project = first.get("project") or "-"
        scheduled = str(first.get("expected_date") or "-")[:10]
        driver = first.get("driver_name") or "-"
        status_val = first.get("status") or "-"

        # ---------- DISPATCH HEADER (navy bar) ----------
        header_tbl = Table(
            [[Paragraph(
                f"🚛 {dispatch_id}  &nbsp;|&nbsp;  {destination}  &nbsp;|&nbsp;  "
                f"Status: {status_val}",
                dispatch_style,
            )]],
            colWidths=[505],
        )
        header_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))

        # ---------- META ROW ----------
        meta_tbl = Table(
            [[
                Paragraph("Destination:", meta_label_style),
                Paragraph(destination, meta_value_style),
                Paragraph("Project:", meta_label_style),
                Paragraph(project, meta_value_style),
                Paragraph("Scheduled:", meta_label_style),
                Paragraph(scheduled, meta_value_style),
                Paragraph("Driver:", meta_label_style),
                Paragraph(driver, meta_value_style),
            ]],
            colWidths=[62, 90, 42, 90, 60, 62, 38, 61],
        )
        meta_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, GREY_MED),
        ]))

        # ---------- ITEM BREAKDOWN ----------
        item_data = [[
            Paragraph("Item", item_header_style),
            Paragraph("Qty", item_header_style),
            Paragraph("Unit", item_header_style),
        ]]
        total_qty = 0.0
        for it in items:
            try:
                q = float(it.get("expected_quantity") or 0)
            except (TypeError, ValueError):
                q = 0.0
            total_qty += q
            item_data.append([
                Paragraph(str(it.get("item_name", "")), item_cell_style),
                Paragraph(_fmt_qty(q), item_cell_right),
                Paragraph(str(it.get("unit", "")), item_cell_style),
            ])

        items_tbl = Table(item_data, colWidths=[345, 80, 80])
        items_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.2, GREY_MED),
        ]))

        # ---------- TOTAL BAR ----------
        n_lines = len(items)
        total_tbl = Table(
            [[
                Paragraph(f"TOTAL", total_style),
                Paragraph(f"{n_lines} line{'s' if n_lines != 1 else ''}", total_style),
                Paragraph(f"{_fmt_qty(total_qty)} units", total_style),
            ]],
            colWidths=[200, 150, 155],
        )
        total_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2A9D8F")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        # Bundle with KeepTogether — keeps the whole dispatch on one page
        story.append(KeepTogether([header_tbl, meta_tbl, items_tbl, total_tbl]))
        story.append(Spacer(1, 6 * mm))

    # ---------- SECTIONS ----------
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Deliveries Log"))
    story.append(Spacer(1, 5 * mm))

    for section_title, section_items in [
        ("Logged Today", logged_today),
        ("Completed Today", completed_today),
        ("Pending and Due (Overdue)", pending_due),
        ("Upcoming Deliveries", upcoming),
    ]:
        story.append(Paragraph(
            "<b>" + section_title + "</b> — " + str(len(section_items)) + " item(s)",
            ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=10,
                           textColor=NAVY, spaceBefore=4, spaceAfter=3),
        ))
        if not section_items:
            story.append(Paragraph("None.", _style_small()))
            story.append(Spacer(1, 4 * mm))
            continue

        # Group by dispatch_id
        groups = {}
        for d in section_items:
            did = d.get("dispatch_id") or "LEGACY"
            groups.setdefault(did, []).append(d)

        for dispatch_id, items in groups.items():
            render_dispatch_group(dispatch_id, items)


def _build_discrepancies(story, discrepancies):
    if not discrepancies:
        return
    story.append(Spacer(1, 8 * mm))
    story.append(_section_bar("Physical Count Discrepancies"))
    story.append(Spacer(1, 5 * mm))

    rows = []
    for d in discrepancies:
        rows.append([
            str(d.get("timestamp", "") or "")[:10],
            d.get("item_name", ""),
            _fmt_qty(d.get("system_stock", 0)),
            _fmt_qty(d.get("physical_count", 0)),
            _fmt_qty(d.get("variance", 0)),
            d.get("unit", ""),
            d.get("submitted_by", ""),
            str(d.get("status", "")),
        ])

    _append_chunked_table(story,
        ["Date", "Item", "System", "Physical", "Variance", "Unit", "Audited By", "Status"],
        rows, col_widths=[55, 120, 55, 55, 55, 40, 80, 55],
        font_size=6.5, header_size=7, numeric_cols={2, 3, 4})


def _build_appendix(story, title, report_type, period_label, prepared_by):
    story.append(PageBreak())
    story.append(_section_bar("Appendix"))
    story.append(Spacer(1, 5 * mm))

    app_rows = [
        ("Company", COMPANY),
        ("Tagline", TAGLINE),
        ("Location", LOCATION),
        ("Phone", PHONE),
        ("Email", EMAIL),
        ("Report Title", title),
        ("Report Type", report_type),
        ("Period", period_label),
        ("System", "ARV Inventory Management System"),
    ]
    story.append(_info_grid(app_rows))

    story.append(Spacer(1, 15 * mm))
    story.append(_section_bar("Approval", color=GREEN))
    story.append(Spacer(1, 8 * mm))

    sig = Table([
        ["", ""],
        ["Prepared By", "Approved By"],
        ["", ""],
        [prepared_by, ""],
        ["_________________________", "_________________________"],
        ["Signature / Date", "Signature / Date"],
    ], colWidths=[250, 250], rowHeights=[40, 18, 40, 18, 12, 14])
    sig.setStyle(TableStyle([
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 1), (-1, 1), NAVY),
        ("FONT", (0, 3), (-1, 3), "Helvetica", 9),
        ("TEXTCOLOR", (0, 3), (-1, 3), INK),
        ("FONT", (0, 5), (-1, 5), "Helvetica", 7.5),
        ("TEXTCOLOR", (0, 5), (-1, 5), GREY_TEXT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig)


# ============================================================================
# MAIN PDF BUILDER — ONE CLEAN PATH
# ============================================================================
def build_pdf_report(report_type, period_label, filters, summary, details, by_item,
                     prepared_by, paper_size="letter", extras=None):
    """Build the PDF. `by_item` is either:
        - a list of dicts with keys {Item, Category, Unit, On-Hand, Reserved, Available, Status}
          (inventory snapshot reports)
        - a list of dicts with keys {Item, Unit, Type, Total Qty}
          (movement / project / supplier reports)
    """
    extras = extras or {}
    deliveries = extras.get("deliveries") or []
    discrepancies = extras.get("discrepancies") or []

    buf = io.BytesIO()
    title = "Inventory Activity Report"

    if paper_size == "legal":
        page_size = portrait(legal)
    else:
        page_size = portrait(letter)
    globals()["PAGE_SIZE"] = page_size

    report_id = _generate_report_id()

    doc = ARVDocTemplate(
        buf, report_title=title,
        report_id=report_id, content_hash="--pending--",
        pagesize=page_size,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=22 * mm, bottomMargin=15 * mm,
    )

    story = []

    # 1. COVER
    _build_cover(story, report_type, period_label, prepared_by)

    # 2. EXECUTIVE SUMMARY
    story.append(PageBreak())
    story.append(_section_bar("Executive Summary"))
    story.append(Spacer(1, 5 * mm))
    if summary:
        story.append(_kpi_row(summary))
        story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Report Overview", ParagraphStyle(
        "ro", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, spaceAfter=3)))
    story.append(Paragraph(_summary_paragraph(summary, report_type, period_label), _style_body()))
    story.append(Spacer(1, 6 * mm))

    # 3. RECOMMENDATIONS
    # Determine which items list to feed into recommendations (snapshot vs tx)
    snapshot_items = by_item if _is_snapshot(by_item) else []
    _build_recommendations(story, summary, snapshot_items)

    # 4. SUMMARY BY CATEGORY (snapshot only)
    if _is_snapshot(by_item):
        _build_summary_by_category(story, by_item)

    # 5. SUMMARY BY ITEM (both paths)
    if by_item:
        if _is_snapshot(by_item):
            _build_summary_by_item_snapshot(story, by_item)
        else:
            _build_summary_by_item_tx(story, by_item)

    # 6. LOW STOCK DETAIL (snapshot only)
    if _is_snapshot(by_item):
        _build_low_stock_detail(story, by_item)

    # 7. OUT-OF-STOCK DETAIL (snapshot only)
    if _is_snapshot(by_item):
        _build_out_of_stock_detail(story, by_item)

    # 8. DELIVERIES LOG (only when extras provided)
    if deliveries and ("Full" in report_type or "Deliver" in report_type):
        _build_deliveries_log(story, deliveries)

    # 9. PHYSICAL COUNT DISCREPANCIES
    if discrepancies and ("Full" in report_type or "Physical" in report_type):
        _build_discrepancies(story, discrepancies)

    # 10. APPENDIX + APPROVAL
    _build_appendix(story, title, report_type, period_label, prepared_by)

    # Compute hash from story content
    try:
        story_repr = "".join(str(getattr(s, "text", "") or "") for s in story)
        story_repr += str(summary) + str(len(by_item or []))
        doc.content_hash = _compute_hash(story_repr.encode("utf-8"))
    except Exception:
        doc.content_hash = _compute_hash(str(datetime.now()).encode("utf-8"))

    doc.build(story)
    buf.seek(0)
    pdf_bytes = buf.getvalue()
    if _RASTERIZE_ENABLED:
        pdf_bytes = rasterize_pdf(pdf_bytes, dpi=150)
    return pdf_bytes


def _is_snapshot(by_item):
    """Detect if by_item is snapshot data (has Category) or transaction data (has Type)."""
    if not by_item:
        return False
    first = by_item[0]
    return "Category" in first or "On-Hand" in first or "Status" in first


def build_pdf_report_editable(report_type, period_label, filters, summary, details,
                              by_item, prepared_by, paper_size="letter", extras=None):
    """Returns an EDITABLE (non-rasterized) PDF. Admin use only."""
    global _RASTERIZE_ENABLED
    prev = _RASTERIZE_ENABLED
    _RASTERIZE_ENABLED = False
    try:
        return build_pdf_report(report_type, period_label, filters, summary, details,
                                by_item, prepared_by, paper_size, extras)
    finally:
        _RASTERIZE_ENABLED = prev


# ============================================================================
# EXCEL BUILDER
# ============================================================================
def build_excel_report(report_type, period_label, filters, summary, details, by_item, extras=None):
    wb = Workbook()
    navy_fill = PatternFill("solid", fgColor="0D3B66")
    grey_fill = PatternFill("solid", fgColor="F8FAFC")
    title_font = Font(bold=True, size=16, color="0D3B66")
    sub_font = Font(bold=True, size=10, color="5A6472")
    header_font = Font(bold=True, size=10, color="FFFFFF")
    label_font = Font(bold=True, size=9, color="0D3B66")
    body_font = Font(size=9, color="1F2937")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    border = Border(
        left=Side("thin", color="DCE2EC"),
        right=Side("thin", color="DCE2EC"),
        top=Side("thin", color="DCE2EC"),
        bottom=Side("thin", color="DCE2EC"),
    )

    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = COMPANY
    ws["A1"].font = title_font
    ws["A2"] = TAGLINE
    ws["A2"].font = sub_font
    ws["A3"] = report_type
    ws["A3"].font = Font(bold=True, size=12)
    ws["A4"] = period_label
    ws["A4"].font = sub_font
    ws["A5"] = "Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M")
    ws["A5"].font = Font(size=9, color="5A6472")

    row = 7
    ws.cell(row=row, column=1, value="Metric").font = header_font
    ws.cell(row=row, column=2, value="Value").font = header_font
    ws.cell(row=row, column=1).fill = navy_fill
    ws.cell(row=row, column=2).fill = navy_fill
    row += 1
    for k, v in summary.items():
        c1 = ws.cell(row=row, column=1, value=str(k))
        c1.font = label_font
        c1.border = border
        c2 = ws.cell(row=row, column=2, value=_clean(v))
        c2.font = body_font
        c2.border = border
        row += 1
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 44

    if by_item:
        ws2 = wb.create_sheet("By Item")
        headers = list(by_item[0].keys())
        for c, h in enumerate(headers, start=1):
            cell = ws2.cell(row=1, column=c, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border
        for r, d in enumerate(by_item, start=2):
            for c, h in enumerate(headers, start=1):
                val = _clean(d.get(h, ""))
                try:
                    if val != "" and float(val) == float(val):
                        val = float(val)
                except Exception:
                    pass
                cell = ws2.cell(row=r, column=c, value=val)
                cell.font = body_font
                cell.border = border
                cell.alignment = left
                if r % 2 == 1:
                    cell.fill = grey_fill
        for i, h in enumerate(headers, start=1):
            ws2.column_dimensions[get_column_letter(i)].width = max(len(h) + 2, 14)
        ws2.freeze_panes = "A2"

    if details:
        ws3 = wb.create_sheet("Details")
        headers = list(details[0].keys())
        for c, h in enumerate(headers, start=1):
            cell = ws3.cell(row=1, column=c, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border
        for r, d in enumerate(details, start=2):
            for c, h in enumerate(headers, start=1):
                v = d.get(h, "")
                if "date" in h.lower() or "time" in h.lower():
                    v = _fmt_dt(v)
                cell = ws3.cell(row=r, column=c, value=_clean(v))
                cell.font = body_font
                cell.border = border
                if r % 2 == 1:
                    cell.fill = grey_fill
        for i, h in enumerate(headers, start=1):
            ws3.column_dimensions[get_column_letter(i)].width = max(len(h) + 2, 14)
        ws3.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
