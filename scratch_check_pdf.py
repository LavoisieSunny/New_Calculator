import os
import sys
from pypdf import PdfReader, PdfWriter

# Add backend folder to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.ocr import perform_ocr_on_scanned_pdf
from backend.parser_heuristics import parse_extracted_text

pdf_path = r"C:\Users\lavoi\Desktop\Miracle\pdfs\compensation\MA_9824_2025.pdf"
temp_pdf_path = "temp_MA_9824_2025.pdf"

print("Creating temporary 2-page PDF (Page 1 and Page 42)...")
reader = PdfReader(pdf_path)
writer = PdfWriter()
writer.add_page(reader.pages[0])
writer.add_page(reader.pages[len(reader.pages) - 1])
with open(temp_pdf_path, "wb") as f:
    writer.write(f)

print("Running scanned OCR on 2-page PDF...")
text_lines, ocr_debug = perform_ocr_on_scanned_pdf(temp_pdf_path)
print(f"OCR completed: {len(text_lines)} lines extracted.")

# Clean up temp pdf
if os.path.exists(temp_pdf_path):
    os.remove(temp_pdf_path)

# Write raw text to a scratch file
with open("extracted_raw_text.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(text_lines))
print("\nSaved extracted text to extracted_raw_text.txt")
    
# 1. Parse Suggestions JSON
print("\n--- RUNNING HEURISTIC SUGGESTION PARSING ---")
sug = parse_extracted_text(text_lines)
import pprint
pprint.pprint(sug)
