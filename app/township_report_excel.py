"""Excel export for the township village/ward household report."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

FONT_NAME = "Pyidaungsu"
THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MM_DIGITS = str.maketrans("0123456789", "၀၁၂၃၄၅၆၇၈၉")


def _mm_digits(value) -> str:
    return str(value).translate(MM_DIGITS)


def _report_year(start_date: str, end_date: str) -> str:
    for value in (start_date, end_date):
        value = (value or "").strip()
        if len(value) >= 4 and value[:4].isdigit():
            return value[:4]
    return str(date.today().year)


def _date_line(start_date: str, end_date: str) -> str:
    start = _mm_digits(start_date) if start_date else ""
    end = _mm_digits(end_date) if end_date else ""
    if start and end:
        return f"ရက်စွဲ - {start} မှ {end} ထိ"
    if start:
        return f"ရက်စွဲ - {start} မှ ထိ"
    if end:
        return f"ရက်စွဲ - မှ {end} ထိ"
    return "ရက်စွဲ - အားလုံး"


def _put(ws, row: int, column: int, value, **style):
    cell = ws.cell(row, column, value)
    if isinstance(value, str):
        cell.data_type = "s"
    for key, val in style.items():
        setattr(cell, key, val)
    return cell


def build_township_report_workbook(villages, state_name: str, district_name: str,
                                   township_name: str, start_date: str = "",
                                   end_date: str = "") -> BytesIO:
    """Build the report in the same five-column layout as the supplied form."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Township Report"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.topLeftCell = "A1"
    ws.sheet_view.selection[0].activeCell = "A1"
    ws.sheet_view.selection[0].sqref = "A1"
    ws.print_title_rows = "7:7"

    widths = {"A": 6, "B": 38, "C": 25, "D": 22, "E": 16}
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    report_year = _mm_digits(_report_year(start_date, end_date))
    report_title = (
        f"{report_year} ခုနှစ် တိရစ္ဆာန်ကောင်ရေစာရင်း "
        "ကောက်ယူပြီးစီးမှုအခြေအနေ"
    )
    ws.merge_cells("A1:E1")
    _put(
        ws, 1, 1, report_title,
        font=Font(name=FONT_NAME, size=13, bold=True),
        alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
    )
    ws.row_dimensions[1].height = 32

    info_font = Font(name=FONT_NAME, size=10.5)
    info_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.merge_cells("A2:B2")
    _put(ws, 2, 1, f"တိုင်းဒေသကြီး/ပြည်နယ် - {state_name}", font=info_font, alignment=info_align)
    ws.merge_cells("A3:B3")
    _put(ws, 3, 1, f"ခရိုင် - {district_name}", font=info_font, alignment=info_align)
    ws.merge_cells("A4:B4")
    _put(ws, 4, 1, f"မြို့နယ် - {township_name}", font=info_font, alignment=info_align)

    ws.merge_cells("A5:E5")
    _put(
        ws, 5, 1, _date_line(start_date, end_date),
        font=info_font,
        alignment=Alignment(horizontal="right", vertical="center"),
    )
    for row in range(2, 6):
        ws.row_dimensions[row].height = 19
    ws.row_dimensions[6].height = 8

    headers = [
        "စဉ်",
        "စာရင်းကောက်ယူသောကျေးရွာရပ် ကွက်အမည်",
        "Village/Ward P-code",
        "အိမ်ထောင်စုအရေအတွက်",
        "မှတ်ချက်",
    ]
    header_font = Font(name=FONT_NAME, size=10.5, bold=True)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for column, value in enumerate(headers, 1):
        _put(ws, 7, column, value, font=header_font, alignment=header_align, border=BORDER)
    ws.row_dimensions[7].height = 50

    data_font = Font(name=FONT_NAME, size=11)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_number = 8
    for index, village in enumerate(villages, 1):
        values = [
            index,
            village.get("villageName") or "",
            "-",
            int(village.get("household_count") or 0),
            "",
        ]
        for column, value in enumerate(values, 1):
            alignment = left_align if column in (2, 5) else center_align
            _put(
                ws, row_number, column, value,
                font=data_font, alignment=alignment, border=BORDER,
            )
        ws.row_dimensions[row_number].height = 27
        row_number += 1

    if not villages:
        ws.merge_cells(start_row=8, start_column=1, end_row=8, end_column=5)
        _put(
            ws, 8, 1, "ဤကာလအတွင်း မှတ်တမ်းရှိသော ကျေးရွာအုပ်စု/ကျေးရွာ မရှိပါ",
            font=data_font,
            alignment=Alignment(horizontal="center", vertical="center"),
            border=BORDER,
        )
        ws.row_dimensions[8].height = 30
        row_number = 9

    last_row = max(7, row_number - 1)
    ws.print_area = f"A1:E{last_row}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = ws.page_margins.bottom = 0.5

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
