"""
Commercial proposal generator with full Cyrillic support.
"""
import json, io, os, logging
from datetime import date
import httpx
from fpdf import FPDF
import config

logger = logging.getLogger(__name__)
FONT_DIR = os.path.dirname(os.path.abspath(__file__))

PROPOSAL_PROMPT = """Ты — коммерческий директор видеопродакшн-компании ООО ZBS PROD (Ташкент, Узбекистан).

На основе запроса клиента составь коммерческое предложение.

ЦЕНООБРАЗОВАНИЕ (рынок Ташкента 2026):
— Новостной сюжет (1-2 мин): $300-500
— Обзор объекта / имиджевый ролик (1-3 мин): $500-1,200
— Репортаж с мероприятия (2-5 мин): $400-800
— Рекламный ролик (30сек-1мин): $800-2,000
— Подкаст съёмка (1 эпизод): $300-600
— SMM-контент (рилсы/шортсы, пакет 4 шт): $400-800
— Серия роликов (от 5 шт): скидка 10-15%
— Абонемент (ежемесячно): скидка 15-20%

ОТВЕТЬ СТРОГО В JSON:
{
  "client_company": "название",
  "contact_person": "имя если есть",
  "intro": "вступление НА РУССКОМ (2-3 предложения)",
  "services": [
    {"name": "Услуга", "description": "Описание на русском", "price_from": 300, "price_to": 500, "unit": "за сюжет"}
  ],
  "packages": [
    {"name": "Пакет", "description": "описание", "price_from": 2000, "price_to": 3500, "savings": "Экономия 15%"}
  ],
  "total_note": "примечание НА РУССКОМ",
  "validity_days": 14
}

ВСЕ тексты НА РУССКОМ. Цены в USD. НЕ пиши ничего кроме JSON."""


class ProposalPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=25)
        fp = os.path.join(FONT_DIR, "DejaVuSans.ttf")
        fb = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
        if os.path.exists(fp):
            self.add_font("DV", "", fp, uni=True)
        if os.path.exists(fb):
            self.add_font("DV", "B", fb, uni=True)
        self.F = "DV" if os.path.exists(fp) else "Helvetica"

    def header(self):
        self.set_font(self.F, "B", 22)
        self.set_text_color(41, 128, 185)
        self.cell(0, 12, "ZBS PROD", new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.F, "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, "ООО ZBS PROD  |  Ташкент, Узбекистан", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, "Тел: +998 93 326 36 76  |  Email: pr@creo.uz", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.5)
        self.line(10, self.get_y()+3, 200, self.get_y()+3)
        self.ln(8)

    def footer(self):
        self.set_y(-20)
        self.set_font(self.F, "", 7)
        self.set_text_color(170, 170, 170)
        self.cell(0, 10, f"ZBS PROD  •  Коммерческое предложение  •  Стр. {self.page_no()}", align="C")


def build_pdf(p: dict) -> bytes:
    pdf = ProposalPDF()
    pdf.add_page()
    F = pdf.F
    today = date.today().strftime("%d.%m.%Y")

    # Title
    pdf.set_font(F, "B", 18)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 12, "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # Meta
    pdf.set_font(F, "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(95, 6, f"Дата: {today}")
    pdf.cell(95, 6, f"Действительно: {p.get('validity_days',14)} дней", new_x="LMARGIN", new_y="NEXT", align="R")
    if p.get("client_company"):
        pdf.set_font(F, "B", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 6, f"Для: {p['client_company']}", new_x="LMARGIN", new_y="NEXT")
    if p.get("contact_person"):
        pdf.set_font(F, "", 10)
        pdf.cell(0, 6, f"Контактное лицо: {p['contact_person']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Intro
    if p.get("intro"):
        pdf.set_font(F, "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 6, p["intro"])
        pdf.ln(5)

    # Services
    svcs = p.get("services", [])
    if svcs:
        pdf.set_font(F, "B", 13)
        pdf.set_text_color(41, 128, 185)
        pdf.cell(0, 10, "УСЛУГИ", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        # Header
        pdf.set_font(F, "B", 9)
        pdf.set_fill_color(41, 128, 185)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(120, 8, "  Услуга", fill=True)
        pdf.cell(70, 8, "  Стоимость (USD)", fill=True, new_x="LMARGIN", new_y="NEXT")
        # Rows — name + price on line 1, description on line 2
        for i, s in enumerate(svcs):
            bg = i % 2 == 0
            if bg: pdf.set_fill_color(240, 245, 250)
            pf, pt = s.get("price_from", 0), s.get("price_to", 0)
            ps = f"${pf:,} – {pt:,}" if pt > pf else f"${pf:,}"
            u = s.get("unit", "")
            if u: ps += f" {u}"
            # Line 1: name + price
            pdf.set_font(F, "B", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(120, 7, f"  {s.get('name','')}", fill=bg)
            pdf.cell(70, 7, f"  {ps}", fill=bg, new_x="LMARGIN", new_y="NEXT")
            # Line 2: description
            desc = s.get("description", "")
            if desc:
                pdf.set_font(F, "", 8)
                pdf.set_text_color(120, 120, 120)
                pdf.cell(120, 5, f"  {desc[:65]}", fill=bg)
                pdf.cell(70, 5, "", fill=bg, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    # Packages
    pkgs = p.get("packages", [])
    if pkgs:
        pdf.set_font(F, "B", 13)
        pdf.set_text_color(41, 128, 185)
        pdf.cell(0, 10, "ПАКЕТНЫЕ ПРЕДЛОЖЕНИЯ", new_x="LMARGIN", new_y="NEXT")
        for pk in pkgs:
            pdf.set_font(F, "B", 11)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 7, pk.get("name", ""), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(F, "", 9)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, 5, pk.get("description", ""))
            pdf.ln(1)
            pf = pk.get("price_from", pk.get("price", 0))
            pt = pk.get("price_to", 0)
            sv = pk.get("savings", "")
            parts = []
            if pt > pf:
                parts.append(f"${pf:,} – ${pt:,}")
            elif pf:
                parts.append(f"от ${pf:,}")
            if sv:
                parts.append(sv)
            if parts:
                pdf.set_font(F, "B", 10)
                pdf.set_text_color(39, 174, 96)
                pdf.set_x(10)
                pdf.cell(190, 8, "  ".join(parts), new_x="LMARGIN", new_y="NEXT", align="L")
            pdf.ln(3)

    # Conditions
    pdf.ln(3)
    pdf.set_font(F, "B", 13)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 10, "УСЛОВИЯ", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(F, "B", 9)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 6, "В стоимость входит:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(F, "", 9)
    for t in ["Пре-продакшн и подготовка", "Профессиональная съёмка", "Монтаж и цветокоррекция", "2 итерации правок"]:
        pdf.cell(0, 5, f"  ✓  {t}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font(F, "B", 9)
    pdf.cell(0, 6, "Оценивается отдельно:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(F, "", 9)
    for t in ["Аренда локации", "Реквизит и декорации", "Кастинг актёров"]:
        pdf.cell(0, 5, f"  •  {t}", new_x="LMARGIN", new_y="NEXT")

    if p.get("total_note"):
        pdf.ln(5)
        pdf.set_font(F, "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.multi_cell(0, 5, p["total_note"])

    # Contact
    pdf.ln(8)
    pdf.set_font(F, "B", 13)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 10, "КОНТАКТЫ", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(F, "", 10)
    pdf.set_text_color(60, 60, 60)
    for line in ["ООО ZBS PROD", "Тел: +998 93 326 36 76", "Email: pr@creo.uz", "Ташкент, Узбекистан"]:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

    return pdf.output()


async def generate_proposal(client_message: str) -> tuple[bytes, dict]:
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
                "messages": [{"role": "user", "content": client_message}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["content"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        proposal = json.loads(raw)
        pdf_bytes = build_pdf(proposal)
        return pdf_bytes, proposal
