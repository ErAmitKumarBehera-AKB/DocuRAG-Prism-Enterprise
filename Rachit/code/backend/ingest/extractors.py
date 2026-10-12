"""
DocuRAG Extractors Module
Modular extraction helpers for PDF digital text, tables, and image/figure rasterization.
"""

import os
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
import pdfplumber


class PDFTextExtractor:
    """Extracts text blocks with coordinates from PyMuPDF page."""
    @staticmethod
    def extract_blocks(page: fitz.Page) -> List[Dict[str, Any]]:
        blocks = page.get_text("blocks")
        results = []
        for i, b in enumerate(blocks):
            if b[6] == 0:  # text block
                text = b[4].strip()
                if text:
                    results.append({
                        "index": i,
                        "text": text,
                        "bbox": list(b[:4])
                    })
        return results


class PDFTableExtractor:
    """Extracts structured tables with headers and converts to clean Markdown."""
    @staticmethod
    def extract_tables(plumb_page: pdfplumber.page.Page) -> List[Dict[str, Any]]:
        extracted_tables = plumb_page.extract_tables()
        results = []
        for t_idx, table in enumerate(extracted_tables):
            if not table or len(table) < 2:
                continue
            
            clean_rows = []
            for row in table:
                clean_row = [str(cell or "").strip() for cell in row]
                if any(clean_row):
                    clean_rows.append(clean_row)
                    
            if len(clean_rows) < 2:
                continue

            headers = clean_rows[0]
            header_line = "| " + " | ".join(headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
            data_lines = ["| " + " | ".join(row) + " |" for row in clean_rows[1:]]
            markdown = "\n".join([header_line, sep_line] + data_lines)
            
            results.append({
                "index": t_idx,
                "markdown": markdown,
                "rows_count": len(clean_rows),
                "cols_count": len(headers)
            })
        return results


class PDFImageExtractor:
    """Renders page thumbnails and extracts embedded figures."""
    @staticmethod
    def render_thumbnail(page: fitz.Page, output_path: str, zoom: float = 1.0) -> str:
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pix.save(output_path)
        return output_path
