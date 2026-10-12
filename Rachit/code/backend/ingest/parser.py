import os
from typing import List

import fitz  # PyMuPDF
import pdfplumber

from backend.app.config import settings
from backend.core.schemas import ContentType, EvidenceChunk
from backend.generation.vision import describe_image


def parse_document(path: str, file_id: str, storage_id: str, asset_output_dir: str = None, processing_preference: str = "mixed", pii_mode: str = "STRICT") -> List[EvidenceChunk]:
    if asset_output_dir is None:
        asset_output_dir = settings.asset_dir
    chunks = []

    try:
        doc = fitz.open(path)

        with pdfplumber.open(path) as pdf_plumb:

            for page_num, page in enumerate(doc):

                p_num = page_num + 1

                # =====================================================
                # 1. Extract Text
                # =====================================================

                blocks = page.get_text("blocks")

                for i, b in enumerate(blocks):

                    if b[6] == 0:  # text block

                        text = b[4].strip()

                        if len(text) > 5:

                            chunks.append(
                                EvidenceChunk(
                                    chunk_id=f"{storage_id}_p{p_num}_t{i}",
                                    file_id=file_id,
                                    storage_id=storage_id,
                                    page=p_num,
                                    content_type=ContentType.text,
                                    region_id=f"t{i}",
                                    bbox=list(b[:4]),
                                    text=text
                                )
                            )

                # =====================================================
                # 2. Extract Tables
                # =====================================================

                if page_num < len(pdf_plumb.pages):

                    plumb_page = pdf_plumb.pages[page_num]

                    tables = plumb_page.find_tables()

                    for i, table in enumerate(tables):

                        extracted = table.extract()

                        if extracted and len(extracted) > 0:
                            headers = extracted[0]
                            header_str = " | ".join([str(c) if c else "" for c in headers])

                            for r_idx, row in enumerate(extracted):
                                row_str = " | ".join([str(c) if c else "" for c in row])
                                
                                try:
                                    row_cells = table.rows[r_idx].cells if hasattr(table.rows[r_idx], 'cells') else table.rows[r_idx]
                                except Exception:
                                    row_cells = []

                                for c_idx, cell_data in enumerate(row):
                                    cell_val = str(cell_data).strip() if cell_data else ""
                                    
                                    # Skip indexing completely empty cells
                                    if not cell_val:
                                        continue
                                        
                                    col_header = str(headers[c_idx]).strip() if c_idx < len(headers) and headers[c_idx] else f"Column {c_idx+1}"
                                    
                                    chunk_text = (
                                        f"Table Context: {header_str}\n"
                                        f"Row Context: {row_str}\n"
                                        f"Target Data ({col_header}): {cell_val}"
                                    )
                                    
                                    try:
                                        if c_idx < len(row_cells) and row_cells[c_idx]:
                                            bbox = list(row_cells[c_idx])
                                        else:
                                            # Fallback to row bbox or table bbox
                                            valid_cells = [c for c in row_cells if c is not None]
                                            if valid_cells:
                                                bbox = [
                                                    min(c[0] for c in valid_cells),
                                                    min(c[1] for c in valid_cells),
                                                    max(c[2] for c in valid_cells),
                                                    max(c[3] for c in valid_cells)
                                                ]
                                            else:
                                                bbox = list(table.bbox)
                                    except Exception:
                                        bbox = list(table.bbox)

                                    chunks.append(
                                        EvidenceChunk(
                                            chunk_id=f"{storage_id}_p{p_num}_tbl{i}_r{r_idx}_c{c_idx}",
                                            file_id=file_id,
                                            storage_id=storage_id,
                                            page=p_num,
                                            content_type=ContentType.table,
                                            region_id=f"tbl{i}_r{r_idx}_c{c_idx}",
                                            bbox=bbox,
                                            text=chunk_text
                                        )
                                    )
                                    
                        # Add a whole-table chunk to capture multi-row context (e.g. dashboard metrics)
                        if extracted and len(extracted) > 0:
                            table_text = "\n".join([" | ".join([str(c) if c else "" for c in row]) for row in extracted])
                            chunks.append(
                                EvidenceChunk(
                                    chunk_id=f"{storage_id}_p{p_num}_tbl{i}_full",
                                    file_id=file_id,
                                    storage_id=storage_id,
                                    page=p_num,
                                    content_type=ContentType.table,
                                    region_id=f"tbl{i}_full",
                                    bbox=list(table.bbox),
                                    text=f"Full Table:\n{table_text}"
                                )
                            )

                # =====================================================
                # 3. Extract Images + Gemini Vision (Only for mixed/charts)
                # =====================================================

                if processing_preference in ["mixed", "charts"]:
                    image_list = page.get_images(full=True)

                    for i, img in enumerate(image_list):

                        xref = img[0]

                        # Extract image from PDF
                        base_image = doc.extract_image(xref)

                        image_bytes = base_image["image"]
                        ext = base_image["ext"]

                        # Save extracted image
                        final_img_path = None
                        temp_img_path = None
                        
                        if pii_mode != "STRICT":
                            final_img_path = os.path.join(
                                settings.asset_dir,
                                f"{file_id}_p{p_num}_img{i}.{ext}"
                            )
                            
                            temp_img_path = os.path.join(
                                asset_output_dir,
                                f"{file_id}_p{p_num}_img{i}.{ext}"
                            )

                            with open(temp_img_path, "wb") as f:
                                f.write(image_bytes)

                        print(
                            f"[VISION] Analyzing image: "
                            f"{file_id} page {p_num} image {i}"
                        )

                        if pii_mode == "STRICT":
                            print(f"[VISION] Blocked image analysis for {file_id} due to STRICT PII mode")
                            visual_description = "Visual description blocked due to STRICT PII masking. Images are not analyzed to prevent data leakage."
                        else:
                            # Analyze image using Gemini Vision
                            visual_description = describe_image(temp_img_path)

                        print(
                            f"[VISION] Description generated for "
                            f"{file_id} page {p_num} image {i}"
                        )

                        if visual_description != "Visual description unavailable.":
                            # Get actual image bounding box on the PDF page
                            try:
                                img_rects = page.get_image_rects(xref)
                                if img_rects:
                                    bbox = [img_rects[0].x0, img_rects[0].y0, img_rects[0].x1, img_rects[0].y1]
                                else:
                                    bbox = [0, 0, 0, 0]
                            except Exception:
                                bbox = [0, 0, 0, 0]

                            # Store visual information as an EvidenceChunk
                            chunks.append(
                                EvidenceChunk(
                                    chunk_id=f"{storage_id}_p{p_num}_img{i}",
                                    file_id=file_id,
                                    storage_id=storage_id,
                                    page=p_num,
                                    content_type=ContentType.image,
                                    region_id=f"img{i}",
                                    bbox=bbox,
                                    thumbnail_path=final_img_path,
                                    text=visual_description
                                )
                            )

    except Exception as e:

        print(
            f"Error parsing document: {e}"
        )

    return chunks