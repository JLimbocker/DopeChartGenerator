
import streamlit as st
import tempfile, os
import main as layout

st.set_page_config(page_title="DOPE Card Generator", page_icon="📄", layout="centered")
st.title("DOPE Card Generator")
st.caption("Generate DOPE cards (2.5×3 small) and Wind Tables (5×3 large) from one or two CSVs.")

col1, col2 = st.columns(2)
with col1:
    csv_a = st.file_uploader("Dataset A (required)", type=["csv"])
with col2:
    csv_b = st.file_uploader("Dataset B (optional)", type=["csv"])

st.markdown(
    """
**Layout logic**
- **Single input** → 2 small (2.5″×3″) + 1 large (5″×3″)
- **Two inputs** → 4 small (two per dataset) + 1 combined large (**red over blue**)
- Large: **top row = Range**, **left column = mph (rotated 90° CCW, slim)**.
""")

with st.expander("Advanced options", expanded=False):
    layout.MPH_COL_W_IN = st.slider("MPH column width (inches)", 0.12, 0.40, layout.MPH_COL_W_IN, 0.01)
    layout.GAP_IN = st.slider("Gap between tables (inches)", 0.10, 0.60, layout.GAP_IN, 0.01)
    layout.MARGIN_LR_IN = st.slider("Left/Right page margin (inches)", 0.25, 1.00, layout.MARGIN_LR_IN, 0.05)
    layout.MARGIN_TB_IN = st.slider("Top/Bottom page margin (inches)", 0.25, 1.00, layout.MARGIN_TB_IN, 0.05)

out_name = st.text_input("Output PDF name", value="tables.pdf")

def _save_upload_to_temp(uploaded_file) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.write(uploaded_file.getbuffer()); tmp.flush(); tmp.close()
    return tmp.name

if st.button("Generate PDF", type="primary", use_container_width=True):
    if not csv_a:
        st.error("Please upload Dataset A (CSV).")
        st.stop()

    tmp_a = _save_upload_to_temp(csv_a)
    tmp_b = _save_upload_to_temp(csv_b) if csv_b else None
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name

    try:
        if tmp_b:
            layout.render_dual(tmp_a, tmp_b, tmp_pdf)
            mode = "Two inputs (4 small + combined large)"
        else:
            layout.render_single(tmp_a, tmp_pdf)
            mode = "Single input (2 small + 1 large)"

        with open(tmp_pdf, "rb") as f:
            st.download_button("Download PDF", data=f.read(), file_name=out_name or "tables.pdf",
                               mime="application/pdf", use_container_width=True)
        st.success(f"PDF generated • {mode}")
    except Exception as e:
        st.error(f"Failed to generate PDF: {e}")
    finally:
        for p in [tmp_a, tmp_b, tmp_pdf]:
            try:
                if p and os.path.exists(p): os.remove(p)
            except Exception:
                pass
