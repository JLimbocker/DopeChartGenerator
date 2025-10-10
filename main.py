
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV -> Precisely sized PDF tables

Small table: 2.5" x 3.0" (Range, Elev, 5mph, 10mph)
Large table: 5.0" x 3.0"
  - Top row: Range headers
  - Column 0: mph integers (2..20) rotated 90° CCW; ~0.22" wide
  - Single input: one value per cell
  - Two inputs: stacked red (data1) over blue (data2) per cell
"""

import csv
import sys
from typing import List

from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----- Constants (tweakable) -----
MPH_COLUMNS = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

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

def format_one_decimal(v: str) -> str:
    try:
        return f"{float(v):.1f}"
    except (ValueError, TypeError):
        return v

def read_csv_rows(csv_path: str) -> List[List[str]]:
    required = ["Range", "Elev", "5mph", "10mph"]
    rows: List[List[str]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        for key in required:
            if key not in reader.fieldnames:
                raise ValueError(f"Missing required column: {key!r}")
        for rec in reader:
            rows.append([
                format_range(rec["Range"]),
                format_one_decimal(rec["Elev"]),
                format_one_decimal(rec["5mph"]),
                format_one_decimal(rec["10mph"]),
            ])
    return rows

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
def small_table_data(rows: List[List[str]]):
    return [["Range", "Elev", "5mph", "10mph"]] + rows

def mph_values_from_10(m10: str, mph: int) -> str:
    try:
        base = float(m10)
    except (ValueError, TypeError):
        base = 0.0
    return f"{base * (mph/10.0):.1f}"

def large_single_data(rows: List[List[str]]):
    header = [""] + [r[0] for r in rows]
    body = []
    for m in MPH_COLUMNS:
        body.append([str(m)] + [mph_values_from_10(r[3], m) for r in rows])
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

def large_combined_data(rows1: List[List[str]], rows2: List[List[str]]):
    header = [""] + [r[0] for r in rows1]
    body = []
    for m in MPH_COLUMNS:
        row = [str(m)]
        for r1, r2 in zip(rows1, rows2):
            a = mph_values_from_10(r1[3], m)
            b = mph_values_from_10(r2[3], m)
            html = f'<font color="#CC0000">{a}</font><br/><font color="#0033CC">{b}</font>'
            row.append(Paragraph(html, STACK_STYLE))
        body.append(row)
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
    rows1 = read_csv_rows(csv1)
    t_s1 = make_fixed_size_table(small_table_data(rows1), SMALL_W_IN, SMALL_H_IN)
    t_s2 = make_fixed_size_table(small_table_data(rows1), SMALL_W_IN, SMALL_H_IN)
    t_L  = make_fixed_size_table(large_single_data(rows1), LARGE_W_IN, LARGE_H_IN,
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
    rows1 = read_csv_rows(csv1)
    rows2 = read_csv_rows(csv2)

    t_s1a = make_fixed_size_table(small_table_data(rows1), SMALL_W_IN, SMALL_H_IN)
    t_s1b = make_fixed_size_table(small_table_data(rows1), SMALL_W_IN, SMALL_H_IN)
    t_s2a = make_fixed_size_table(small_table_data(rows2), SMALL_W_IN, SMALL_H_IN)
    t_s2b = make_fixed_size_table(small_table_data(rows2), SMALL_W_IN, SMALL_H_IN)

    t_Lc  = make_fixed_size_table(large_combined_data(rows1, rows2), LARGE_W_IN, LARGE_H_IN,
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
