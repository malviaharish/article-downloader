import streamlit as st
import requests
import pandas as pd
import os
from pathlib import Path

UNPAYWALL_EMAIL = "your_email@institute.edu"  # REQUIRED

st.set_page_config("DOI → Legal PDF Downloader", layout="wide")
st.title("📚 DOI → Legal PDF Downloader (Open Access only)")

doi_text = st.text_area(
    "Paste DOIs (one per line)",
    height=200,
    placeholder="10.1000/j.jmb.2020.01.001"
)

download_dir = Path("downloads")
download_dir.mkdir(exist_ok=True)

def query_unpaywall(doi):
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": UNPAYWALL_EMAIL}
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return None
    return r.json()

def download_pdf(pdf_url, filename):
    r = requests.get(pdf_url, timeout=30)
    if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", ""):
        with open(filename, "wb") as f:
            f.write(r.content)
        return True
    return False

if st.button("🔍 Check & Download"):
    dois = [d.strip() for d in doi_text.splitlines() if d.strip()]
    results = []

    progress = st.progress(0)

    for i, doi in enumerate(dois):
        record = {
            "DOI": doi,
            "OA": "No",
            "Source": "",
            "PDF_Downloaded": "No",
            "PDF_URL": ""
        }

        data = query_unpaywall(doi)
        if data and data.get("is_oa"):
            record["OA"] = "Yes"

            oa_loc = data.get("best_oa_location")
            if oa_loc and oa_loc.get("url_for_pdf"):
                pdf_url = oa_loc["url_for_pdf"]
                record["Source"] = oa_loc.get("host_type", "")
                record["PDF_URL"] = pdf_url

                pdf_path = download_dir / f"{doi.replace('/', '_')}.pdf"
                if download_pdf(pdf_url, pdf_path):
                    record["PDF_Downloaded"] = "Yes"

        results.append(record)
        progress.progress((i + 1) / len(dois))

    df = pd.DataFrame(results)
    st.success("Done!")

    st.dataframe(df, use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download report (CSV)",
        csv,
        "doi_oa_report.csv",
        "text/csv"
    )
