
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV -> Precisely sized PDF tables

Small table: 2.5" x 3.0" (Range, Elev, 5mph, 10mph)
Large table: 5.0" x 3.0"
  - Top row: Range headers
  - Column 0: mph integers generated from available wind data; rotated 90° CCW; ~0.22" wide
  - Single input: one value per cell
  - Two inputs: stacked red (data1) over blue (data2) per cell
"""

import csv
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----- Constants (tweakable) -----
PAGE_W_IN, PAGE_H_IN = 8.5, 11.0
MARGIN_LR_IN = 0.5
MARGIN_TB_IN = 0.5
GAP_IN = 0.25

SMALL_W_IN, SMALL_H_IN = 2.5, 3.0
LARGE_W_IN, LARGE_H_IN = 5.0, 3.0
MPH_COL_W_IN = 0.22  # slim rotated column

# ----- Formatting helpers -----
def format_range(v: str) -> str:
    try:
        return f"{int(float(v))}"
    except (ValueError, TypeError):
        return v

def format_optional_one_decimal(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:.1f}"

@dataclass
class WindRow:
    range_label: str
    elevation: Optional[float]
    winds: Dict[int, float]


@dataclass
class WindDataset:
    rows: List[WindRow]
    mph_values: List[int]


def _parse_wind_columns(fieldnames: Sequence[str]) -> List[Tuple[int, str]]:
    wind_columns: List[Tuple[int, str]] = []
    for name in fieldnames:
        lower = name.lower()
        if lower.endswith("mph") and lower not in {"range", "elev"}:
            prefix = lower[:-3].strip()
            try:
                mph = int(prefix)
            except ValueError:
                continue
            wind_columns.append((mph, name))
    wind_columns.sort(key=lambda x: x[0])
    return wind_columns


def _parse_float(value: str) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_csv_rows(csv_path: str) -> WindDataset:
    required = ["Range", "Elev"]
    rows: List[WindRow] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        for key in required:
            if key not in reader.fieldnames:
                raise ValueError(f"Missing required column: {key!r}")
        wind_columns = _parse_wind_columns(reader.fieldnames)
        if not wind_columns:
            raise ValueError("CSV must contain at least one wind speed column ending with 'mph'")
        for rec in reader:
            winds: Dict[int, float] = {}
            for mph, col in wind_columns:
                value = _parse_float(rec.get(col))
                if value is not None:
                    winds[mph] = value
            rows.append(WindRow(
                range_label=format_range(rec["Range"]),
                elevation=_parse_float(rec["Elev"]),
                winds=winds,
            ))
    mph_values = sorted({mph for mph, _ in wind_columns})
    return WindDataset(rows=rows, mph_values=mph_values)


def interpolate_wind_value(row: WindRow, target_mph: int) -> Optional[float]:
    if target_mph in row.winds:
        return row.winds[target_mph]
    if not row.winds:
        return None
    sorted_mphs = sorted(row.winds.keys())
    if target_mph < sorted_mphs[0] or target_mph > sorted_mphs[-1]:
        return None
    if target_mph == sorted_mphs[0]:
        return row.winds[sorted_mphs[0]]
    if target_mph == sorted_mphs[-1]:
        return row.winds[sorted_mphs[-1]]
    lower_mph = None
    upper_mph = None
    for mph in sorted_mphs:
        if mph < target_mph:
            lower_mph = mph
        elif mph > target_mph:
            upper_mph = mph
            break
        else:
            return row.winds[mph]
    if lower_mph is None or upper_mph is None:
        return None
    lower_val = row.winds[lower_mph]
    upper_val = row.winds[upper_mph]
    if lower_val is None or upper_val is None or upper_mph == lower_mph:
        return None
    ratio = (target_mph - lower_mph) / (upper_mph - lower_mph)
    return lower_val + (upper_val - lower_val) * ratio


def generate_large_mph_columns(*mph_lists: Sequence[int]) -> List[int]:
    available = sorted({mph for lst in mph_lists for mph in lst})
    if not available:
        raise ValueError("No wind speed columns available to generate large chart headers")
    start = available[0]
    end = max(max(available), 16)

    def build(step: int) -> List[int]:
        mphs = list(range(start, end + 1, step))
        if mphs[-1] != end:
            mphs.append(end)
        if mphs[0] != start:
            mphs.insert(0, start)
        return sorted(set(mphs))

    mphs = build(2)
    if len(mphs) < 8:
        mphs = build(1)
    step = 2
    while len(mphs) > 10 and step < (end - start + 1):
        step += 1
        mphs = build(step)

    if len(mphs) > 10:
        # Down-sample while preserving endpoints
        desired = 10
        full = mphs
        result = [full[0]]
        for i in range(1, desired - 1):
            pos = i * (len(full) - 1) / (desired - 1)
            idx = round(pos)
            idx = max(0, min(idx, len(full) - 1))
            candidate = full[idx]
            if candidate <= result[-1] and idx < len(full) - 1:
                idx += 1
                candidate = full[idx]
            result.append(candidate)
        result.append(full[-1])
        # Remove potential duplicates while keeping order
        deduped: List[int] = []
        for val in result:
            if not deduped or deduped[-1] != val:
                deduped.append(val)
        mphs = deduped

    if len(mphs) < 8:
        full_range = list(range(start, end + 1))
        for mph in full_range:
            if mph not in mphs:
                mphs.append(mph)
                mphs.sort()
                if len(mphs) >= 8:
                    break
    if len(mphs) < 8:
        raise ValueError("Unable to generate at least 8 wind columns from available data range")
    return mphs[:10]

# ----- Fit helpers -----
def _max_line_width(text: str, font_name="Helvetica") -> float:
    lines = text.splitlines() if isinstance(text, str) else [str(text)]
    return max(pdfmetrics.stringWidth(line, font_name, 1.0) for line in lines) if lines else 0.0

def _cell_plain(cell) -> str:
    if isinstance(cell, Paragraph):
        return cell.getPlainText()
    return str(cell)

def shrink_to_fit_font_size_excluding_first_col(table_data, col_widths, row_heights,
                                                font_name="Helvetica", max_font=12.0, min_font=3.2,
                                                hpad=1.0, vpad=1.5, leading_factor=1.15, lines_per_cell=1):
    nrows = len(table_data)
    ncols = len(table_data[0]) if nrows else 0
    horiz_sizes = []
    for c in range(ncols):
        if c == 0:
            continue
        max_w = 0.0
        for r in range(nrows):
            txt = _cell_plain(table_data[r][c])
            max_w = max(max_w, _max_line_width(txt, font_name))
        usable = max(col_widths[c] - 2*hpad, 0.5)
        horiz_sizes.append(usable / max_w if max_w > 0 else max_font)
    if not horiz_sizes:
        horiz_sizes = [max_font]
    vert_sizes = []
    for r in range(nrows):
        row_h = max(row_heights[r] - 2*vpad, 0.5)
        vert_sizes.append(row_h / (leading_factor * lines_per_cell))
    size = min(min(horiz_sizes), min(vert_sizes), max_font)
    return max(min_font, size)

# ----- Builders -----
SMALL_WIND_COLUMNS = [5, 10]


def wind_value_string(row: WindRow, mph: int) -> str:
    value = interpolate_wind_value(row, mph)
    return format_optional_one_decimal(value)


def small_table_data(dataset: WindDataset):
    header = ["Range", "Elev"] + [f"{mph}mph" for mph in SMALL_WIND_COLUMNS]
    table_rows = []
    for row in dataset.rows:
        table_rows.append([
            row.range_label,
            format_optional_one_decimal(row.elevation),
            *[wind_value_string(row, mph) for mph in SMALL_WIND_COLUMNS],
        ])
    return [header] + table_rows


def large_single_data(dataset: WindDataset, mph_columns: Sequence[int]):
    header = [""] + [r.range_label for r in dataset.rows]
    body = []
    for mph in mph_columns:
        body.append([str(mph)] + [wind_value_string(r, mph) for r in dataset.rows])
    return [header] + body

styles = getSampleStyleSheet()
STACK_STYLE = ParagraphStyle(
    'StackedRB',
    parent=styles['BodyText'],
    alignment=1,
    fontName='Helvetica',
    fontSize=8,
    leading=9.5,
    spaceBefore=0,
    spaceAfter=0,
)

def large_combined_data(dataset1: WindDataset, dataset2: WindDataset, mph_columns: Sequence[int]):
    header = [""] + [r.range_label for r in dataset1.rows]
    body = []
    for mph in mph_columns:
        row_cells = [str(mph)]
        for r1, r2 in zip(dataset1.rows, dataset2.rows):
            a = wind_value_string(r1, mph)
            b = wind_value_string(r2, mph)
            html = f'<font color="#CC0000">{a}</font><br/><font color="#0033CC">{b}</font>'
            row_cells.append(Paragraph(html, STACK_STYLE))
        body.append(row_cells)
    return [header] + body

# ----- Table factories -----
def make_fixed_size_table(table_data, width_in, height_in,
                          grid_width=0.5, font_name="Helvetica", lines_per_cell=1,
                          rotate_first_col=False, mph_col_width_in=MPH_COL_W_IN):
    width = width_in * inch
    height = height_in * inch
    nrows = len(table_data)
    ncols = len(table_data[0])

    if rotate_first_col:
        mph_w = mph_col_width_in * inch
        remaining_w = max(width - mph_w, 0.5)
        other_w = remaining_w / (ncols - 1)
        col_widths = [mph_w] + [other_w]*(ncols-1)
        row_heights = [height / nrows]*nrows
        font_size = shrink_to_fit_font_size_excluding_first_col(
            table_data, col_widths, row_heights, lines_per_cell=lines_per_cell
        )
    else:
        col_widths = [width / ncols]*ncols
        row_heights = [height / nrows]*nrows
        font_size = 8  # small tables

    t = Table(table_data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
    style_cmds = [
        ("FONT", (0,0), (-1,-1), font_name, font_size),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 1.0),
        ("RIGHTPADDING", (0,0), (-1,-1), 1.0),
        ("TOPPADDING", (0,0), (-1,-1), 1.5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1.5),
        ("GRID", (0,0), (-1,-1), grid_width, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
    ]
    if rotate_first_col:
        style_cmds += [
            ("ROTATE", (0,1), (0,-1), 90),
            ("ALIGN", (0,1), (0,-1), "CENTER"),
            ("VALIGN", (0,1), (0,-1), "MIDDLE"),
        ]
    t.setStyle(TableStyle(style_cmds))
    return t

# ----- Layout helpers -----
def draw_table(c: rl_canvas.Canvas, t: Table, x_in: float, y_in: float):
    c.saveState()
    c.translate(x_in*inch, y_in*inch)
    t.wrapOn(c, 0, 0)
    t.drawOn(c, 0, 0)
    c.restoreState()

def render_single(csv1: str, out_pdf: str):
    dataset1 = read_csv_rows(csv1)
    small_data = small_table_data(dataset1)
    mph_columns = generate_large_mph_columns(dataset1.mph_values)
    large_data = large_single_data(dataset1, mph_columns)

    t_s1 = make_fixed_size_table(small_data, SMALL_W_IN, SMALL_H_IN)
    t_s2 = make_fixed_size_table(small_data, SMALL_W_IN, SMALL_H_IN)
    t_L  = make_fixed_size_table(large_data, LARGE_W_IN, LARGE_H_IN,
                                 grid_width=0.75, rotate_first_col=True, lines_per_cell=1)

    c = rl_canvas.Canvas(out_pdf, pagesize=letter)

    total_small_w = 2*SMALL_W_IN + GAP_IN
    x_start = (PAGE_W_IN - total_small_w)/2.0
    y_top = PAGE_H_IN - MARGIN_TB_IN - SMALL_H_IN
    draw_table(c, t_s1, x_start, y_top)
    draw_table(c, t_s2, x_start + SMALL_W_IN + GAP_IN, y_top)

    x_large = (PAGE_W_IN - LARGE_W_IN)/2.0
    y_large = y_top - GAP_IN - LARGE_H_IN
    draw_table(c, t_L, x_large, y_large)

    c.showPage()
    c.save()

def render_dual(csv1: str, csv2: str, out_pdf: str):
    dataset1 = read_csv_rows(csv1)
    dataset2 = read_csv_rows(csv2)

    small1 = small_table_data(dataset1)
    small2 = small_table_data(dataset2)
    mph_columns = generate_large_mph_columns(dataset1.mph_values, dataset2.mph_values)
    large_combined = large_combined_data(dataset1, dataset2, mph_columns)

    t_s1a = make_fixed_size_table(small1, SMALL_W_IN, SMALL_H_IN)
    t_s1b = make_fixed_size_table(small1, SMALL_W_IN, SMALL_H_IN)
    t_s2a = make_fixed_size_table(small2, SMALL_W_IN, SMALL_H_IN)
    t_s2b = make_fixed_size_table(small2, SMALL_W_IN, SMALL_H_IN)

    t_Lc  = make_fixed_size_table(large_combined, LARGE_W_IN, LARGE_H_IN,
                                  grid_width=0.75, rotate_first_col=True, lines_per_cell=2)

    c = rl_canvas.Canvas(out_pdf, pagesize=letter)

    total_row_w = 2*SMALL_W_IN + GAP_IN
    x_left = (PAGE_W_IN - total_row_w)/2.0
    x_right = x_left + SMALL_W_IN + GAP_IN
    y_row1 = PAGE_H_IN - MARGIN_TB_IN - SMALL_H_IN
    y_row2 = y_row1 - (SMALL_H_IN + GAP_IN)

    draw_table(c, t_s1a, x_left,  y_row1)
    draw_table(c, t_s1b, x_right, y_row1)
    draw_table(c, t_s2a, x_left,  y_row2)
    draw_table(c, t_s2b, x_right, y_row2)

    x_large = (PAGE_W_IN - LARGE_W_IN)/2.0
    y_large = y_row2 - GAP_IN - LARGE_H_IN
    draw_table(c, t_Lc, x_large, y_large)

    c.showPage()
    c.save()

if __name__ == "__main__":
    if len(sys.argv) == 3:
        render_single(sys.argv[1], sys.argv[2])
        print(f"Wrote {sys.argv[2]}")
    elif len(sys.argv) == 4:
        render_dual(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"Wrote {sys.argv[3]}")
    else:
        print("Usage:\n  python main.py input.csv output.pdf\n  python main.py input1.csv input2.csv output.pdf")
        sys.exit(1)
