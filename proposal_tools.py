"""
Commercial proposal (КП) PDF generator.
Claude calls this tool to generate professional PDF proposals
that Robert can forward to clients directly from Telegram.
"""

import json
import logging
import os
from datetime import date

from fpdf import FPDF

logger = logging.getLogger(__name__)

# ──────────────────── Tool Definition ─────────────────

PROPOSAL_TOOLS = [
    {
        "name": "generate_proposal_pdf",
        "description": (
            "Generate a professional commercial proposal (коммерческое предложение) as PDF. "
            "Use when the user asks to create a КП, commercial proposal, or price quote for a client. "
            "Extract: client company name, contact person, services requested, prices. "
            "ALWAYS confirm the content with the user before generating the PDF. "
            "Show the proposal text first, ask for confirmation, then generate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_company": {
                    "type": "string",
                    "description": "Client company name",
                },
                "client_contact": {
                    "type": "string",
                    "description": "Client contact person name (if known)",
                    "default": "",
                },
                "services": {
                    "type": "array",
                    "description": "List of services with pricing",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Service name"},
                            "description": {"type": "string", "description": "Brief description"},
                            "price_uzs": {"type": "integer", "description": "Price in UZS (сум)"},
                            "price_usd": {"type": "integer", "description": "Price in USD (approximate)"},
                            "unit": {"type": "string", "description": "Per what: за ролик, за день, за проект", "default": "за единицу"},
                        },
                        "required": ["name", "price_uzs"],
                    },
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes, terms, or conditions",
                    "default": "",
                },
                "valid_days": {
                    "type": "integer",
                    "description": "Proposal validity in days",
                    "default": 14,
                },
            },
            "required": ["client_company", "services"],
        },
    },
]


# ──────────────────── PDF Generator ───────────────────

class ProposalPDF(FPDF):
    """Professional proposal PDF with ZBS PROD branding."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=25)
        # Register a Unicode font — DejaVu is available on most systems
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if os.path.exists(font_path):
            self.add_font("DejaVu", "", font_path, uni=True)
            self.add_font("DejaVu", "B", bold_path, uni=True)
            self.default_font = "DejaVu"
        else:
            # Fallback — try to find any Unicode font
            for p in [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ]:
                if os.path.exists(p):
                    self.add_font("UniFont", "", p, uni=True)
                    bold_p = p.replace("Regular", "Bold").replace("Sans.", "Sans-Bold.")
                    if os.path.exists(bold_p):
                        self.add_font("UniFont", "B", bold_p, uni=True)
                    self.default_font = "UniFont"
                    break
            else:
                self.default_font = "Helvetica"

    def header(self):
        self.set_font(self.default_font, "B", 16)
        self.set_text_color(40, 40, 40)
        self.cell(0, 10, "ООО ZBS PROD", align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.default_font, "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, "Видеопродакшн  •  Медиа  •  Контент", align="L", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, "Тел: +998 93 326 36 76  •  pr@creo.uz", align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        # Line
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-20)
        self.set_font(self.default_font, "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"ООО ZBS PROD  •  Ташкент  •  {date.today().year}", align="C")


def generate_pdf(
    client_company: str,
    client_contact: str,
    services: list[dict],
    notes: str = "",
    valid_days: int = 14,
) -> str:
    """Generate proposal PDF, return file path."""
    pdf = ProposalPDF()
    pdf.add_page()
    f = pdf.default_font

    # Title
    pdf.set_font(f, "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, "Коммерческое предложение", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Client info
    pdf.set_font(f, "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 7, f"Для: {client_company}", new_x="LMARGIN", new_y="NEXT")
    if client_contact:
        pdf.cell(0, 7, f"Контактное лицо: {client_contact}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Дата: {date.today().strftime('%d.%m.%Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Действительно: {valid_days} дней", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Services table header
    pdf.set_fill_color(45, 45, 45)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(f, "B", 10)

    col_w = [10, 55, 65, 30, 30]  # №, Услуга, Описание, Цена UZS, Цена USD
    headers = ["№", "Услуга", "Описание", "Цена (сум)", "Цена ($)"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 9, h, border=1, fill=True, align="C")
    pdf.ln()

    # Services rows
    pdf.set_text_color(40, 40, 40)
    pdf.set_font(f, "", 9)
    total_uzs = 0
    total_usd = 0

    for idx, svc in enumerate(services, 1):
        name = svc.get("name", "")
        desc = svc.get("description", "")
        price_uzs = svc.get("price_uzs", 0)
        price_usd = svc.get("price_usd", 0)
        unit = svc.get("unit", "")

        total_uzs += price_uzs
        total_usd += price_usd

        price_uzs_str = f"{price_uzs:,}".replace(",", " ")
        price_usd_str = f"${price_usd:,}" if price_usd else "—"
        if unit:
            price_uzs_str += f"\n{unit}"
            price_usd_str += f"\n{unit}" if price_usd else ""

        row_h = 10
        # Check if we need multi-line
        if len(desc) > 40 or len(name) > 30:
            row_h = 16

        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(245, 245, 245)

        pdf.cell(col_w[0], row_h, str(idx), border=1, fill=fill, align="C")
        pdf.cell(col_w[1], row_h, name[:30], border=1, fill=fill)
        pdf.cell(col_w[2], row_h, desc[:40], border=1, fill=fill)
        pdf.cell(col_w[3], row_h, price_uzs_str.split("\n")[0], border=1, fill=fill, align="R")
        pdf.cell(col_w[4], row_h, price_usd_str.split("\n")[0], border=1, fill=fill, align="R")
        pdf.ln()

    # Total row
    pdf.set_font(f, "B", 10)
    pdf.set_fill_color(230, 230, 230)
    total_w = col_w[0] + col_w[1] + col_w[2]
    pdf.cell(total_w, 10, "ИТОГО:", border=1, fill=True, align="R")
    pdf.cell(col_w[3], 10, f"{total_uzs:,}".replace(",", " "), border=1, fill=True, align="R")
    pdf.cell(col_w[4], 10, f"${total_usd:,}" if total_usd else "—", border=1, fill=True, align="R")
    pdf.ln(12)

    # Notes
    if notes:
        pdf.set_font(f, "B", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 8, "Примечания:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(f, "", 10)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 6, notes)
        pdf.ln(5)

    # Standard terms
    pdf.set_font(f, "", 9)
    pdf.set_text_color(120, 120, 120)
    terms = [
        "• Предоплата 50% перед началом работ, 50% по завершении",
        "• Сроки производства обсуждаются отдельно по каждому проекту",
        "• В стоимость включены: съёмка, монтаж, цветокоррекция, звук",
        "• Транспортные расходы за пределами Ташкента оплачиваются отдельно",
        f"• Предложение действительно {valid_days} дней с даты выставления",
    ]
    for term in terms:
        pdf.cell(0, 6, term, new_x="LMARGIN", new_y="NEXT")

    # Save
    filepath = f"/tmp/КП_{client_company.replace(' ', '_')}_{date.today().strftime('%d%m%Y')}.pdf"
    pdf.output(filepath)
    logger.info(f"Proposal PDF saved: {filepath}")
    return filepath


# ──────────────────── Tool Executor ───────────────────

async def execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "generate_proposal_pdf":
            filepath = generate_pdf(
                client_company=tool_input["client_company"],
                client_contact=tool_input.get("client_contact", ""),
                services=tool_input["services"],
                notes=tool_input.get("notes", ""),
                valid_days=tool_input.get("valid_days", 14),
            )
            return json.dumps({
                "success": True,
                "filepath": filepath,
                "message": "PDF created. Send it to the user as a document.",
            }, ensure_ascii=False)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        logger.error(f"Proposal tool error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})
