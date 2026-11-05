"""Excel export for the state-wide township summary report.

The layout mirrors the supplied ``နောက်ဆက်တွဲ(င)`` form: one row per
township in the state, with its district and the number of surveyed wards,
villages and households.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from app.district_report_excel import (
    BORDER,
    FONT_NAME,
    _put,
    report_date_line,
    report_year_label,
)


def build_state_report_workbook(townships, state_name: str,
                                start_date: str = "",
                                end_date: str = "") -> BytesIO:
    """Build the official six-column state summary workbook."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "State Report"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.topLeftCell = "A1"
    ws.sheet_view.selection[0].activeCell = "A1"
    ws.sheet_view.selection[0].sqref = "A1"

    widths = {"A": 7, "B": 24, "C": 24, "D": 22, "E": 22, "F": 18}
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    note_font = Font(name=FONT_NAME, size=10.5)
    title_font = Font(name=FONT_NAME, size=13, bold=True)
    info_font = Font(name=FONT_NAME, size=10.5)
    header_font = Font(name=FONT_NAME, size=10.5, bold=True)
    data_font = Font(name=FONT_NAME, size=11)
    right_align = Alignment(horizontal="right", vertical="center")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.merge_cells("A1:F1")
    _put(ws, 1, 1, "နောက်ဆက်တွဲ(င)", font=note_font, alignment=right_align)
    ws.row_dimensions[1].height = 20

    report_title = (
        f"{report_year_label(start_date, end_date)} ခုနှစ် "
        "တိရစ္ဆာန်ကောင်ရေစာရင်း ကောက်ယူမှုအခြေအနေတင်ပြခြင်း"
    )
    ws.merge_cells("A2:F2")
    _put(ws, 2, 1, report_title, font=title_font, alignment=center_align)
    ws.row_dimensions[2].height = 32

    ws.merge_cells("A3:C3")
    _put(
        ws, 3, 1, f"တိုင်းဒေသကြီး/ပြည်နယ် - {state_name}",
        font=info_font, alignment=left_align,
    )
    ws.merge_cells("A4:F4")
    _put(
        ws, 4, 1, report_date_line(start_date, end_date),
        font=info_font, alignment=right_align,
    )
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 8

    for row in (6, 7):
        for column in range(1, 7):
            _put(
                ws, row, column, "",
                font=header_font, alignment=center_align, border=BORDER,
            )

    ws.merge_cells("A6:A7")
    _put(ws, 6, 1, "စဉ်", font=header_font, alignment=center_align)
    ws.merge_cells("B6:B7")
    _put(ws, 6, 2, "ခရိုင်", font=header_font, alignment=center_align)
    ws.merge_cells("C6:C7")
    _put(ws, 6, 3, "မြို့နယ်", font=header_font, alignment=center_align)
    ws.merge_cells("D6:E6")
    _put(ws, 6, 4, "ကောက်ယူသော", font=header_font, alignment=center_align)
    _put(ws, 7, 4, "ရပ်ကွက်\nစုစုပေါင်း", font=header_font, alignment=center_align)
    _put(ws, 7, 5, "ကျေးရွာ\nစုစုပေါင်း", font=header_font, alignment=center_align)
    _put(ws, 6, 6, "အိမ်ထောင်စု", font=header_font, alignment=center_align)
    _put(ws, 7, 6, "စုစုပေါင်း", font=header_font, alignment=center_align)
    ws.row_dimensions[6].height = 30
    ws.row_dimensions[7].height = 54

    row_number = 8
    for index, township in enumerate(townships, 1):
        values = [
            index,
            township.get("districtName") or township.get("districtID") or "",
            township.get("townshipName") or township.get("townshipID") or "",
            int(township.get("ward_count") or 0),
            int(township.get("village_count") or 0),
            int(township.get("household_count") or 0),
        ]
        for column, value in enumerate(values, 1):
            alignment = left_align if column in (2, 3) else center_align
            _put(
                ws, row_number, column, value,
                font=data_font, alignment=alignment, border=BORDER,
            )
        ws.row_dimensions[row_number].height = 28
        row_number += 1

    if not townships:
        ws.merge_cells(start_row=8, start_column=1, end_row=8, end_column=6)
        _put(
            ws, 8, 1, "ဤပြည်နယ်အတွင်း မြို့နယ်များ မရှိပါ",
            font=data_font, alignment=center_align, border=BORDER,
        )
        ws.row_dimensions[8].height = 30
        row_number = 9

    last_row = max(7, row_number - 1)
    ws.print_area = f"A1:F{last_row}"
    ws.page_setup.orientation = "landscape"
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
