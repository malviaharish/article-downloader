import streamlit as st
import requests
import pandas as pd
from pathlib import Path
import zipfile
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ===================== CONFIG ===================== #

UNPAYWALL_EMAIL = "your_real_email@institute.edu"   # REQUIRED
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/pdf,text/html"
}

# ===================== UI ===================== #

st.set_page_config(
    page_title="DOI / PMID / PMCID → Open Access PDF Downloader",
    layout="wide"
)

st.title("📚 DOI / PMID / PMCID → Open Access PDF Downloader")
st.caption("Downloads **legal Open Access PDFs only** using Unpaywall & PubMed Central")

id_text = st.text_area(
    "Paste DOI / PMID / PMCID (one per line)",
    height=220,
    placeholder="10.1000/j.jmb.2020.01.001\nPMID:12345678\nPMC1234567"
)

# ===================== HELPERS ===================== #

def clean_id(val: str) -> str:
    val = val.strip()
    val = re.sub(r"^https?://(dx\.)?doi\.org/", "", val, flags=re.I)
    return val.upper()

def id_type(val: str) -> str:
    if val.startswith("PMC"):
        return "PMCID"
    if val.startswith("PMID:") or val.isdigit():
        return "PMID"
    return "DOI"

def id_crosswalk(val: str):
    try:
        r = requests.get(
            "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
            params={"ids": val, "format": "json"},
            timeout=10
        )
        recs = r.json().get("records", [])
        if recs:
            return recs[0]
    except Exception:
        pass
    return {}

def query_unpaywall(doi: str):
    try:
        r = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": UNPAYWALL_EMAIL},
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def extract_pdf_from_html(page_url: str):
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "lxml")

        meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta and meta.get("content"):
            return meta["content"]

        for a in soup.find_all("a", href=True):
            if ".pdf" in a["href"].lower():
                return urljoin(page_url, a["href"])
    except Exception:
        pass
    return None

def download_pdf(pdf_url: str, filepath: Path) -> str:
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            filepath.write_bytes(r.content)
            return "Downloaded"
        return f"HTTP {r.status_code}"
    except Exception:
        return "Timeout / Blocked"

def zip_downloads(zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for pdf in DOWNLOAD_DIR.glob("*.pdf"):
            z.write(pdf, pdf.name)

def make_clickable(url):
    if not url:
        return ""
    return f"""
    <a href="{url}" target="_blank"
       style="
           background:#2563eb;
           color:white;
           padding:6px 12px;
           border-radius:6px;
           text-decoration:none;
           font-weight:600;
       ">
       Open PDF
    </a>
    """

# ===================== MAIN ===================== #

if st.button("🔍 Check & Download PDFs"):

    inputs = [clean_id(x) for x in id_text.splitlines() if x.strip()]
    progress = st.progress(0)

    results = []

    for i, val in enumerate(inputs):

        record = {
            "Input": val,
            "DOI": "",
            "PMID": "",
            "PMCID": "",
            "OA": "No",
            "Source": "",
            "PDF_URL": "",
            "Download_Status": ""
        }

        # ---------- Resolve IDs ---------- #
        idinfo = id_crosswalk(val)
        record["DOI"] = idinfo.get("doi", "")
        record["PMID"] = idinfo.get("pmid", "")
        record["PMCID"] = idinfo.get("pmcid", "")

        # ---------- PMC direct ---------- #
        if record["PMCID"]:
            pmc_pdf = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{record['PMCID']}/pdf"
            record["OA"] = "Yes"
            record["Source"] = "PubMed Central"
            record["PDF_URL"] = pmc_pdf
            pdf_file = DOWNLOAD_DIR / f"{record['PMCID']}.pdf"
            record["Download_Status"] = download_pdf(pmc_pdf, pdf_file)

        # ---------- Unpaywall via DOI ---------- #
        elif record["DOI"]:
            up = query_unpaywall(record["DOI"])
            if up and up.get("is_oa"):
                loc = up.get("best_oa_location") or {}
                pdf = loc.get("url_for_pdf") or extract_pdf_from_html(loc.get("url", ""))

                if pdf:
                    record["OA"] = "Yes"
                    record["Source"] = "Unpaywall / Publisher"
                    record["PDF_URL"] = pdf
                    pdf_file = DOWNLOAD_DIR / f"{record['DOI'].replace('/', '_')}.pdf"
                    record["Download_Status"] = download_pdf(pdf, pdf_file)
                else:
                    record["Download_Status"] = "OA but PDF not found"
            else:
                record["Download_Status"] = "Not Open Access"

        else:
            record["Download_Status"] = "Identifier not resolved"

        results.append(record)
        progress.progress((i + 1) / len(inputs))

    df = pd.DataFrame(results)
    df["PDF_Link"] = df["PDF_URL"].apply(make_clickable)

    st.success("✅ Processing complete")

    st.markdown(
        df[["Input", "DOI", "PMID", "PMCID", "OA", "Source", "PDF_Link", "Download_Status"]]
        .to_html(escape=False, index=False),
        unsafe_allow_html=True
    )

    # ===================== EXPORTS ===================== #

    st.download_button(
        "⬇️ Download CSV Report",
        df.drop(columns=["PDF_Link"]).to_csv(index=False),
        "oa_report.csv",
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
    **Sources:** Unpaywall • PubMed Central  
    **Compliance:** 100% Legal Open Access  
    """
)
