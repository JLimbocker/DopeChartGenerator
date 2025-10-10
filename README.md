
# CSV → Precise Tables PDF

Generate precisely sized tables from one or two CSVs.

## What it makes
- **Small table (per dataset):** 2.5" × 3.0" — columns: Range, Elev, 5mph, 10mph
- **Large table:** 5.0" × 3.0" — **top row = Range** headers, **left column = mph 2..20** (rotated 90° CCW, slim).

**Single input** → 2 small + 1 large  
**Two inputs** → 4 small (two per dataset) + 1 **combined** large (stacked **red over blue**).

## CSV input
Required columns: `Range, Elev, 5mph, 10mph`  
- `Range`: any whole number 100–999 (or parseable as whole)  
- Others: floats of any precision (rendered **with 1 decimal**)

## Install
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run (CLI)
```bash
# Single dataset
python main.py sample1.csv output_single.pdf

# Two datasets (renders 4 small + combined large)
python main.py sample1.csv sample2.csv output_dual.pdf
```

## Run (UI)
```bash
streamlit run app.py
```
Upload one or two CSVs and click **Generate PDF**.

## Notes
- Bold gridlines for legibility; tight padding; auto-fit to avoid wrapping.
- MPH column is ~0.22" wide and rotated 90° CCW.
- Combined large table uses stacked red/blue values in each cell.
