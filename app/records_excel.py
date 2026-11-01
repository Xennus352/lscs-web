"""Fill the supplied survey workbook without collapsing breeds or age groups."""
from collections import defaultdict
from copy import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import column_index_from_string, get_column_letter


TEMPLATE = Path(__file__).parent / "excel_templates" / "records.xlsx"
# The sample's animal order differs from the database ID order.
LARGE = dict(zip(
    ["laID01", "laID02", "laID03", "laID04", "laID06", "laID07", "laID08"],
    ["T", "AE", "AP", "BA", "BL", "BW", "CH"],
))
SMALL = dict(zip(["yaID01", "yaID02", "yaID03", "yaID04"], ["DD", "DO", "DZ", "EK"]))
POULTRY = dict(zip(
    [f"lsID{i:02}" for i in range(1, 11)],
    ["FG", "FO", "FQ", "FV", "GD", "GF", "GN", "GV", "HD", "HL"],
))
BREEDING = dict(zip(
    ["bsID01", "bsID07", "bsID02", "bsID03", "bsID04", "bsID05", "bsID06", "bsID08", "bsID09"],
    ["IB", "ID", "IF", "IH", "IJ", "IL", "IN", "IP", "IR"],
))
POULTRY_AGES = {
    "ageID07": 0, "ageID08": 1, "ageID09": 2,
    "ageID10": 0, "ageID11": 2,
    "ageID12": 0, "ageID13": 1, "ageID14": 2,
    "ageID15": 0, "ageID16": 1, "ageID17": 2,
}


def _put(sheet, row, column, value):
    cell = sheet.cell(row, column, value)
    # Survey text, including leading '=' and phone/household numbers, is literal.
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def _date(value):
    if isinstance(value, (date, datetime)):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return value or ""


def _animal_block(detail):
    kind, animal = detail["animalTypeID"], detail["animalID"]
    if kind == "atID01":
        return LARGE.get(animal, "CS")
    if kind == "atID02":
        return SMALL.get(animal, "EV")
    if kind == "atID03":
        return POULTRY.get(animal, "HT")
    return None


def _count_column(detail, start):
    kind, animal = detail["animalTypeID"], detail["animalID"]
    age, gender = detail["ageID"], detail["genderID"]
    if kind in ("atID01", "atID02"):
        ages = ["ageID03", "ageID02", "ageID01"] if kind == "atID01" else ["ageID06", "ageID05", "ageID04"]
        if age in ages and gender in ("g01", "g02", "g03"):
            return start + 1 + ages.index(age) * 3 + ["g01", "g02", "g03"].index(gender)
    if kind == "atID03":
        if animal in ("lsID02", "lsID05"):
            return start + 1  # broilers have a single count column
        group = POULTRY_AGES.get(age)
        if animal == "lsID03" and group is not None:
            # The sample combines young males/females into one column.
            if group < 2:
                return start + 1
            if gender in ("g01", "g03"):
                return start + 2 + (gender == "g03")
        elif group is not None and gender in ("g01", "g03"):
            return start + 1 + group * 2 + (gender == "g03")
    return None


def build_records_workbook(households, details):
    workbook = load_workbook(TEMPLATE)
    sheet = workbook.active
    sheet.freeze_panes = "T6"
    sheet.print_title_rows = "1:5"
    # Full source detail also preserves categories absent from the supplied layout
    # (for example bsID10), and legacy records with unrecognised age/sex IDs.
    raw = workbook.create_sheet("Animal details")
    raw.append([
        "Form_ID", "Animal type ID", "Animal ID", "Animal", "Breed ID", "Breed",
        "Age ID", "Age", "Gender ID", "Gender", "Count",
    ])
    raw.freeze_panes = "A2"
    by_form = defaultdict(list)
    for raw_row, detail in enumerate(details, 2):
        by_form[detail["formID"]].append(detail)
        values = [detail.get(key, "") for key in (
            "formID", "animalTypeID", "animalID", "animal_name", "speciesID",
            "species_name", "ageID", "age_name", "genderID", "gender_name", "data_count",
        )]
        for col, value in enumerate(values, 1):
            _put(raw, raw_row, col, value)

    border = Border(**{edge: Side(style="thin", color="000000") for edge in ("left", "right", "top", "bottom")})
    row_number = 6
    for household in households:
        animals = defaultdict(dict)
        breeding = defaultdict(int)
        form_details = by_form[household["formID"]]
        for detail in form_details:
            count = int(detail.get("data_count") or 0)
            if detail["animalTypeID"] == "atID04":
                start = BREEDING.get(detail["animalID"])
                if start and detail["genderID"] in ("g01", "g03"):
                    breeding[column_index_from_string(start) + (detail["genderID"] == "g03")] += count
                continue
            block = _animal_block(detail)
            if block is None:
                continue
            key = (detail["animalID"], detail["speciesID"])
            if key not in animals[block]:
                breed = detail.get("species_name") or ""
                if block in ("CS", "EV", "HT"):
                    breed = f"{detail.get('animal_name') or detail['animalID']} / {breed}"
                animals[block][key] = {"breed": breed, "counts": defaultdict(int), "total": 0}
            entry = animals[block][key]
            start = column_index_from_string(block)
            column = _count_column(detail, start)
            if column is not None:
                entry["counts"][column] += count
            entry["total"] += count

        height = max([1] + [len(breeds) for breeds in animals.values()])
        base = [
            household["formID"], household.get("state_name") or "",
            household.get("district_name") or "", household.get("township_name") or "",
            household.get("qv_name") or "", household.get("WardName") or "",
            household.get("householdNo") or "", _date(household.get("interviewDate")),
            household.get("respondent_name") or "", household.get("respondent_gender") or "",
            household.get("respondent_edu") or "", household.get("respondent_phone") or "",
            household.get("headName") or "", household.get("headGender") or "",
            household.get("headAge") or "", household.get("headEduStatus") or "",
            household.get("headPhoneNo") or "",
            "မွေး" if any(d["animalTypeID"] in ("atID01", "atID02") and int(d.get("data_count") or 0) > 0 for d in form_details) else "မမွေး",
        ]
        for offset in range(height):
            row = row_number + offset
            sheet.row_dimensions[row].height = 42
            for col in range(1, 256):
                cell = sheet.cell(row, col)
                cell.font = Font(name="Pyidaungsu", size=11)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = copy(border)
            _put(sheet, row, 1, row - 5)
            for col, value in enumerate(base, 2):
                _put(sheet, row, col, value)
            sheet.cell(row, 9).number_format = "yyyy-mm-dd"
            _put(sheet, row, 254, household.get("Interviewer") or "")
            _put(sheet, row, 255, household.get("interviewerPhoneNo") or "")
        for block, breeds in animals.items():
            start = column_index_from_string(block)
            for offset, entry in enumerate(breeds.values()):
                row = row_number + offset
                _put(sheet, row, start, entry["breed"])
                for column, count in entry["counts"].items():
                    _put(sheet, row, column, count)
                if block not in ("FO", "GD"):
                    width = 10 if block in LARGE.values() or block == "CS" or block in SMALL.values() or block == "EV" else 4 if block == "FQ" else 7
                    _put(sheet, row, start + width, entry["total"])
        # Counts occur once per household even when breeds require extra rows.
        for column, count in breeding.items():
            _put(sheet, row_number, column, count)
        row_number += height

    sheet.print_area = f"A1:IU{max(5, row_number - 1)}"
    for col in range(1, 12):
        raw.column_dimensions[get_column_letter(col)].width = 24
        raw.cell(1, col).font = Font(name="Pyidaungsu", bold=True)
    raw.auto_filter.ref = raw.dimensions
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
