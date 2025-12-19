import streamlit as st
import requests
import pandas as pd
from pathlib import Path
import zipfile
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ===================== CONFIG ===================== #

UNPAYWALL_EMAIL = "your_email@institute.edu"   # REQUIRED
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/pdf,text/html"
}

# ===================== UI ===================== #

st.set_page_config(
    page_title="DOI → Open Access PDF Downloader",
    layout="wide"
)

st.title("📚 DOI → Open Access PDF Downloader")
st.caption("Downloads **legal Open Access PDFs only** using Unpaywall, PMC & Publisher OA pages")

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
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def extract_pdf_from_html(page_url: str):
    """
    Extracts PDF link from publisher OA landing page
    """
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "lxml")

        # 1️⃣ citation_pdf_url (BEST)
        meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta and meta.get("content"):
            return meta["content"]

        # 2️⃣ Any .pdf link
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                return urljoin(page_url, href)

    except Exception:
        pass

    return None

def get_pdf_or_landing(unpaywall_data):
    locations = []

    if unpaywall_data.get("best_oa_location"):
        locations.append(unpaywall_data["best_oa_location"])

    locations.extend(unpaywall_data.get("oa_locations", []))

    for loc in locations:
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"], "pdf"

        if loc.get("url"):
            # PMC HTML → PDF
            if "ncbi.nlm.nih.gov/pmc/articles" in loc["url"]:
                return loc["url"].rstrip("/") + "/pdf", "pdf"
            return loc["url"], "html"

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
            return "Blocked or HTML"
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
            url, url_type = get_pdf_or_landing(data)

            if url:
                record["OA"] = "Yes"
                pdf_file = DOWNLOAD_DIR / f"{doi.replace('/', '_')}.pdf"

                if url_type == "pdf":
                    record["Source"] = "Direct PDF"
                    record["PDF_URL"] = url
                    record["Download_Status"] = download_pdf(url, pdf_file)

                else:
                    record["Source"] = "Publisher OA Page"
                    extracted_pdf = extract_pdf_from_html(url)

                    if extracted_pdf:
                        record["PDF_URL"] = extracted_pdf
                        record["Download_Status"] = download_pdf(extracted_pdf, pdf_file)
                    else:
                        record["Download_Status"] = "OA page but PDF not found"
            else:
                record["Download_Status"] = "OA but no usable link"
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
    **Sources:** Unpaywall • PubMed Central • Publisher OA  
    **Compliance:** 100% Legal Open Access (No Sci-Hub / Anna’s Archive)
    """
)
