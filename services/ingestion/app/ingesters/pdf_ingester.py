"""PDF text extraction (pure-python free path, no API)."""
import io


def parse_pdf(raw: bytes) -> str:
    try:
        from pdfplumber import open as pdf_open  # recommended, better table/text fidelity

        with pdf_open(io.BytesIO(raw)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages)
    except Exception:
        # fallback to pypdf which is always installed
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)