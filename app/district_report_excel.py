"""Excel export for the district township summary report.

The layout mirrors the supplied ``နောက်ဆက်တွဲ(ဃ)`` form: one row per
township in the district, with the number of surveyed wards, villages and
households.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

FONT_NAME = "Pyidaungsu"
THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MM_DIGITS = str.maketrans("0123456789", "၀၁၂၃၄၅၆၇၈၉")


def mm_digits(value) -> str:
    return str(value).translate(MM_DIGITS)


def report_year(start_date: str, end_date: str) -> str:
    for value in (start_date, end_date):
        value = (value or "").strip()
        if len(value) >= 4 and value[:4].isdigit():
            return value[:4]
    return str(date.today().year)


def report_year_label(start_date: str, end_date: str) -> str:
    return mm_digits(report_year(start_date, end_date))


def report_date_line(start_date: str, end_date: str) -> str:
    start = mm_digits(start_date) if start_date else ""
    end = mm_digits(end_date) if end_date else ""
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


def build_district_report_workbook(townships, state_name: str, district_name: str,
                                   start_date: str = "",
                                   end_date: str = "") -> BytesIO:
    """Build the official five-column district summary workbook."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "District Report"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.topLeftCell = "A1"
    ws.sheet_view.selection[0].activeCell = "A1"
    ws.sheet_view.selection[0].sqref = "A1"

    widths = {"A": 7, "B": 32, "C": 25, "D": 25, "E": 20}
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    note_font = Font(name=FONT_NAME, size=10.5)
    title_font = Font(name=FONT_NAME, size=13, bold=True)
    info_font = Font(name=FONT_NAME, size=10.5)
    right_align = Alignment(horizontal="right", vertical="center")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.merge_cells("A1:E1")
    _put(ws, 1, 1, "နောက်ဆက်တွဲ(ဃ)", font=note_font, alignment=right_align)
    ws.row_dimensions[1].height = 20

    report_title = (
        f"{report_year_label(start_date, end_date)} ခုနှစ် "
        "တိရစ္ဆာန်ကောင်ရေစာရင်း ကောက်ယူမှုအခြေအနေတင်ပြခြင်း"
    )
    ws.merge_cells("A2:E2")
    _put(ws, 2, 1, report_title, font=title_font, alignment=center_align)
    ws.row_dimensions[2].height = 32

    ws.merge_cells("A3:E3")
    _put(ws, 3, 1, " | ".join(value for value in (state_name, district_name) if value), font=info_font, alignment=left_align)
    ws.merge_cells("A5:E5")
    _put(ws, 5, 1, report_date_line(start_date, end_date), font=info_font, alignment=right_align)
    for row in range(3, 6):
        ws.row_dimensions[row].height = 20
    ws.row_dimensions[6].height = 8

    headers = [
        "စဉ်",
        "မြို့နယ်",
        "ကောက်ယူသော\nရပ်ကွက်\nစုစုပေါင်း",
        "ကောက်ယူသော\nကျေးရွာ\nစုစုပေါင်း",
        "အိမ်ထောင်စု\nစုစုပေါင်း",
    ]
    header_font = Font(name=FONT_NAME, size=10.5, bold=True)
    for column, value in enumerate(headers, 1):
        _put(ws, 7, column, value, font=header_font, alignment=center_align, border=BORDER)
    ws.row_dimensions[7].height = 64

    data_font = Font(name=FONT_NAME, size=11)
    row_number = 8
    for index, township in enumerate(townships, 1):
        values = [
            index,
            township.get("townshipName") or township.get("townshipID") or "",
            int(township.get("ward_count") or 0),
            int(township.get("village_count") or 0),
            int(township.get("household_count") or 0),
        ]
        for column, value in enumerate(values, 1):
            alignment = left_align if column == 2 else center_align
            _put(
                ws, row_number, column, value,
                font=data_font, alignment=alignment, border=BORDER,
            )
        ws.row_dimensions[row_number].height = 28
        row_number += 1

    if not townships:
        ws.merge_cells(start_row=8, start_column=1, end_row=8, end_column=5)
        _put(
            ws, 8, 1, "ဤခရိုင်အတွင်း မြို့နယ်များ မရှိပါ",
            font=data_font, alignment=center_align, border=BORDER,
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
