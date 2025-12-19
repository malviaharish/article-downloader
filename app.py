import streamlit as st
import requests
import pandas as pd
from pathlib import Path
import zipfile
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ===================== CONFIG ===================== #

UNPAYWALL_EMAIL = "your_email@institute.edu"
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/pdf,text/html"
}

# ===================== UI ===================== #

st.set_page_config(page_title="DOI → OA PDF Downloader", layout="wide")
st.title("📚 DOI → Open Access PDF Downloader")
st.caption("Handles publisher blocks by resolving PDFs from journal pages (OA only)")

doi_text = st.text_area(
    "Paste DOIs (one per line)",
    height=220,
    placeholder="10.1016/j.csbj.2022.05.012"
)

# ===================== FUNCTIONS ===================== #

def clean_doi(doi):
    doi = doi.strip()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)

def query_unpaywall(doi):
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": UNPAYWALL_EMAIL}
    r = requests.get(url, params=params, timeout=15)
    return r.json() if r.status_code == 200 else None

def extract_pdf_from_html(page_url):
    """
    Scrape journal landing page for PDF link
    """
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Common PDF link patterns
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if ".pdf" in href:
                return urljoin(page_url, a["href"])

    except Exception:
        pass

    return None

def get_pdf_url(unpaywall_data):
    locations = []

    if unpaywall_data.get("best_oa_location"):
        locations.append(unpaywall_data["best_oa_location"])

    locations.extend(unpaywall_data.get("oa_locations", []))

    for loc in locations:
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"], loc.get("url"), loc.get("host_type", "")

        url = loc.get("url", "")
        if "ncbi.nlm.nih.gov/pmc/articles" in url:
            return url.rstrip("/") + "/pdf", url, "pmc"

    return None, None, None

def download_pdf_with_fallback(pdf_url, landing_url, filepath):
    # 1️⃣ Try direct PDF
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            filepath.write_bytes(r.content)
            return "Downloaded (direct)"
    except Exception:
        pass

    # 2️⃣ Fallback: scrape journal page
    if landing_url:
        scraped_pdf = extract_pdf_from_html(landing_url)
        if scraped_pdf:
            try:
                r = requests.get(scraped_pdf, headers=HEADERS, timeout=30)
                if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
                    filepath.write_bytes(r.content)
                    return "Downloaded (journal page)"
            except Exception:
                pass

    return "OA but blocked"

def zip_pdfs(zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for pdf in DOWNLOAD_DIR.glob("*.pdf"):
            z.write(pdf, pdf.name)

# ===================== MAIN ===================== #

if st.button("🔍 Check & Download PDFs"):

    dois = [clean_doi(d) for d in doi_text.splitlines() if d.strip()]
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
            pdf_url, landing_url, source = get_pdf_url(data)

            if pdf_url:
                record["OA"] = "Yes"
                record["Source"] = source
                record["PDF_URL"] = pdf_url

                pdf_file = DOWNLOAD_DIR / f"{doi.replace('/', '_')}.pdf"
                record["Download_Status"] = download_pdf_with_fallback(
                    pdf_url, landing_url, pdf_file
                )
            else:
                record["Download_Status"] = "OA but no PDF found"

        else:
            record["Download_Status"] = "Not Open Access"

        results.append(record)
        progress.progress((i + 1) / len(dois))

    df = pd.DataFrame(results)
    st.success("✅ Completed")
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "⬇️ Download CSV Report",
        df.to_csv(index=False).encode(),
        "doi_oa_report.csv",
        "text/csv"
    )

    zip_path = Path("oa_pdfs.zip")
    zip_pdfs(zip_path)

    if zip_path.exists():
        st.download_button(
            "📦 Download PDFs (ZIP)",
            zip_path.read_bytes(),
            "oa_pdfs.zip",
            "application/zip"
        )

# ===================== FOOTER ===================== #

st.markdown(
    """
    ---
    **Sources:** Unpaywall • Publisher OA • PubMed Central  
    **Policy:** Open Access only (fully compliant)
    """
)
