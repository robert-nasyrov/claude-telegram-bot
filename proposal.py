"""
Commercial proposal (КП) generator.
Creates professional PDF proposals from client messages.
Uses Claude to structure content, fpdf2 to render PDF.
"""

import json
import io
import logging
from datetime import date

import httpx
from fpdf import FPDF

import config

logger = logging.getLogger(__name__)


PROPOSAL_PROMPT = """Ты — коммерческий директор видеопродакшн-компании ООО ZBS PROD (Ташкент, Узбекистан).

На основе запроса клиента составь коммерческое предложение.

ЦЕНООБРАЗОВАНИЕ (рынок Ташкента 2026):
— Новостной сюжет (1-2 мин): $300-500 (съёмка + монтаж + озвучка)
— Обзор объекта / имиджевый ролик (1-3 мин): $500-1,200
— Репортаж с мероприятия (2-5 мин): $400-800
— Рекламный ролик (30сек-1мин): $800-2,000
— Подкаст съёмка (1 эпизод): $300-600
— SMM-контент (рилсы/шортсы, пакет 4 шт): $400-800
— Серия роликов (от 5 шт): скидка 10-15%
— Абонемент (ежемесячно): скидка 15-20%

В цену входит: пре-продакшн, съёмка, монтаж, цветокоррекция, 2 итерации правок.
Не входит: аренда локации, реквизит, кастинг актёров (оценивается отдельно).

ОТВЕТЬ СТРОГО В JSON формате:
{
  "client_company": "название компании клиента",
  "contact_person": "имя контактного лица если есть",
  "intro": "короткое вступление (2-3 предложения)",
  "services": [
    {
      "name": "название услуги",
      "description": "краткое описание что входит (1-2 предложения)",
      "price_from": 300,
      "price_to": 500,
      "unit": "за ролик"
    }
  ],
  "packages": [
    {
      "name": "название пакета если релевантно",
      "description": "описание",
      "price": 1500,
      "savings": "экономия 15%"
    }
  ],
  "total_note": "примечание об общей стоимости",
  "validity_days": 14
}

Если пакеты нерелевантны — оставь пустой массив.
Цены должны быть обоснованы для рынка Ташкента.
НЕ пиши ничего кроме JSON."""


class ProposalPDF(FPDF):
    """Custom PDF for commercial proposals."""

    def __init__(self):
        super().__init__()
        # Use built-in fonts with latin encoding
        # For Cyrillic we'll use DejaVu if available, otherwise fallback
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(44, 62, 80)
        self.cell(0, 12, "ZBS PROD", new_x="LMARGIN", new_y="NEXT", align="L")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(127, 140, 141)
        self.cell(0, 5, "OOO ZBS PROD | Tashkent, Uzbekistan", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, "Tel: +998933263676 | Email: pr@creo.uz", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y() + 3, 200, self.get_y() + 3)
        self.ln(8)

    def footer(self):
        self.set_y(-20)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(170, 170, 170)
        self.cell(0, 10, f"ZBS PROD | Commercial Proposal | Page {self.page_no()}", align="C")


def transliterate(text: str) -> str:
    """Transliterate Cyrillic to Latin for PDF compatibility."""
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    }
    return ''.join(mapping.get(c, c) for c in text)


def safe_text(text: str) -> str:
    """Make text safe for PDF rendering — transliterate if needed."""
    try:
        text.encode('latin-1')
        return text
    except UnicodeEncodeError:
        return transliterate(text)


def build_pdf(proposal: dict) -> bytes:
    """Build a PDF from structured proposal data."""
    pdf = ProposalPDF()
    pdf.add_page()

    today = date.today().strftime("%d.%m.%Y")

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, "COMMERCIAL PROPOSAL", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)

    # Date and client
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Date: {today}", new_x="LMARGIN", new_y="NEXT")

    client = proposal.get("client_company", "")
    if client:
        pdf.cell(0, 6, f"For: {safe_text(client)}", new_x="LMARGIN", new_y="NEXT")

    contact = proposal.get("contact_person", "")
    if contact:
        pdf.cell(0, 6, f"Attn: {safe_text(contact)}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # Intro
    intro = proposal.get("intro", "")
    if intro:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 6, safe_text(intro))
        pdf.ln(5)

    # Services table
    services = proposal.get("services", [])
    if services:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 8, "SERVICES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Table header
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(70, 8, " Service", fill=True)
        pdf.cell(75, 8, " Description", fill=True)
        pdf.cell(45, 8, " Price (USD)", fill=True, new_x="LMARGIN", new_y="NEXT")

        # Table rows
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(50, 50, 50)
        for i, svc in enumerate(services):
            fill = i % 2 == 0
            if fill:
                pdf.set_fill_color(245, 245, 245)

            name = safe_text(svc.get("name", ""))
            desc = safe_text(svc.get("description", ""))[:60]
            price_from = svc.get("price_from", 0)
            price_to = svc.get("price_to", 0)
            unit = safe_text(svc.get("unit", ""))

            price_str = f"${price_from:,}-{price_to:,} {unit}" if price_to > price_from else f"${price_from:,} {unit}"

            pdf.cell(70, 7, f" {name[:35]}", fill=fill)
            pdf.cell(75, 7, f" {desc}", fill=fill)
            pdf.cell(45, 7, f" {price_str}", fill=fill, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(5)

    # Packages
    packages = proposal.get("packages", [])
    if packages:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 8, "PACKAGES", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for pkg in packages:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(44, 62, 80)
            name = safe_text(pkg.get("name", ""))
            pdf.cell(0, 7, f"{name}", new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 80)
            desc = safe_text(pkg.get("description", ""))
            pdf.multi_cell(0, 5, desc)

            price = pkg.get("price", 0)
            savings = safe_text(pkg.get("savings", ""))
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(39, 174, 96)
            pdf.cell(0, 7, f"${price:,} ({savings})", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

    # Notes
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)

    total_note = safe_text(proposal.get("total_note", ""))
    if total_note:
        pdf.multi_cell(0, 5, total_note)
        pdf.ln(2)

    validity = proposal.get("validity_days", 14)
    pdf.cell(0, 5, f"This proposal is valid for {validity} days from the date above.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.cell(0, 5, "Price includes: pre-production, filming, editing, color correction, 2 revision rounds.", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Not included: location rental, props, casting (quoted separately).", new_x="LMARGIN", new_y="NEXT")

    # Contact
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 7, "CONTACT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 5, "OOO ZBS PROD", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Phone: +998933263676", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Email: pr@creo.uz", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Tashkent, Uzbekistan", new_x="LMARGIN", new_y="NEXT")

    return pdf.output()


async def generate_proposal(client_message: str) -> tuple[bytes, dict]:
    """
    Generate a commercial proposal PDF from a client message.
    Returns: (pdf_bytes, proposal_data)
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "system": PROPOSAL_PROMPT,
                "messages": [
                    {"role": "user", "content": client_message}
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["content"][0]["text"].strip()

        # Clean JSON
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        proposal = json.loads(raw)
        pdf_bytes = build_pdf(proposal)
        return pdf_bytes, proposal
