"""
DocuRAG Ingestion Router Module
Dynamically classifies pages and routes them to optimal extraction pipelines.
"""

from enum import Enum
from typing import Dict, Any


class PageStrategy(str, Enum):
    DIGITAL_NATIVE = "digital_native"
    SCANNED_OCR = "scanned_ocr"
    TABLE_INTENSIVE = "table_intensive"
    FIGURE_HEAVY = "figure_heavy"


class IngestRouter:
    """
    Analyzes document pages and determines optimal parsing paths.
    """
    @staticmethod
    def classify_page(text_char_count: int, table_count: int, image_count: int) -> PageStrategy:
        if table_count > 0 and text_char_count > 100:
            return PageStrategy.TABLE_INTENSIVE
        elif text_char_count < 50 and image_count > 0:
            return PageStrategy.SCANNED_OCR
        elif image_count > 1 and text_char_count < 300:
            return PageStrategy.FIGURE_HEAVY
        else:
            return PageStrategy.DIGITAL_NATIVE
