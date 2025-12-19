import streamlit as st
import requests
import pandas as pd
from pathlib import Path
import zipfile
import re

# ===================== CONFIG ===================== #

UNPAYWALL_EMAIL = "your_email@institute.edu"   # REQUIRED
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/pdf"
}

# ===================== UI ===================== #

st.set_page_config(
    page_title="DOI → Open Access PDF Downloader",
    layout="wide"
)

st.title("📚 DOI → Open Access PDF Downloader")
st.caption("Downloads **legal Open Access PDFs only** using Unpaywall & PubMed Central")

doi_text = st.text_area(
    "Paste DOIs (one per line)",
    height=220,
    placeholder="10.1000/j.jmb.2020.01.001"
)

# ===================== FUNCTIONS ===================== #

def clean_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi

def query_unpaywall(doi: str):
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": UNPAYWALL_EMAIL}
    r = requests.get(url, params=params, timeout=15)
    if r.status_code == 200:
        return r.json()
    return None

def get_pdf_url(unpaywall_data):
    """
    Robust OA PDF resolver:
    - Checks best_oa_location
    - Checks all oa_locations
    - Converts PMC HTML → PDF
    """
    locations = []

    if unpaywall_data.get("best_oa_location"):
        locations.append(unpaywall_data["best_oa_location"])

    locations.extend(unpaywall_data.get("oa_locations", []))

    for loc in locations:
        # 1️⃣ Direct PDF
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"], loc.get("host_type", "")

        # 2️⃣ PubMed Central HTML → PDF
        url = loc.get("url", "")
        if "ncbi.nlm.nih.gov/pmc/articles" in url:
            return url.rstrip("/") + "/pdf", "pmc"

    return None, None

def download_pdf(pdf_url: str, filepath: Path) -> str:
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=30)
        content_type = r.headers.get("Content-Type", "").lower()

        if r.status_code == 200 and "pdf" in content_type:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return "Downloaded"
        else:
            return "Blocked or HTML page"
    except Exception as e:
        return f"Error: {str(e)}"

def zip_downloads(zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for pdf in DOWNLOAD_DIR.glob("*.pdf"):
            z.write(pdf, pdf.name)

# ===================== MAIN LOGIC ===================== #

if st.button("🔍 Check & Download PDFs"):

    raw_dois = [d for d in doi_text.splitlines() if d.strip()]
    dois = [clean_doi(d) for d in raw_dois]

    if not dois:
        st.warning("Please paste at least one DOI.")
        st.stop()

    results = []
    progress = st.progress(0)

    for i, doi in enumerate(dois):

        record = {
            "DOI": doi,
            "OA": "No",
            "Source": "",
            "PDF_URL": "",
            "Download_Status": ""
        }

        data = query_unpaywall(doi)

        if data and data.get("is_oa"):
            pdf_url, source = get_pdf_url(data)

            if pdf_url:
                record["OA"] = "Yes"
                record["Source"] = source
                record["PDF_URL"] = pdf_url

                pdf_file = DOWNLOAD_DIR / f"{doi.replace('/', '_')}.pdf"
                record["Download_Status"] = download_pdf(pdf_url, pdf_file)
            else:
                record["Download_Status"] = "OA but no PDF link"

        else:
            record["Download_Status"] = "Not Open Access"

        results.append(record)
        progress.progress((i + 1) / len(dois))

    df = pd.DataFrame(results)

    st.success("✅ Processing complete")
    st.dataframe(df, use_container_width=True)

    # ===================== EXPORTS ===================== #

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV Report",
        csv_data,
        "doi_oa_report.csv",
        "text/csv"
    )

    zip_path = Path("oa_pdfs.zip")
    zip_downloads(zip_path)

    if zip_path.exists():
        with open(zip_path, "rb") as f:
            st.download_button(
                "📦 Download All PDFs (ZIP)",
                f,
                file_name="oa_pdfs.zip",
                mime="application/zip"
            )

# ===================== FOOTER ===================== #

st.markdown(
    """
    ---
    **Data sources:** Unpaywall • PubMed Central  
    **Compliance:** Open Access only (no Sci-Hub / Anna’s Archive)  
    """
)
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
