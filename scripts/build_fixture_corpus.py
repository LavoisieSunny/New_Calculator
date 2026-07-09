import os
import re
import json
import argparse

def scrub_pii(text: str) -> str:
    # 1. Scrub names like "राजेश कुमार पुत्र श्री रमेश कुमार", "रमेश कुमार"
    text = re.sub(
        r'(?:नाम|पिता का नाम|पुत्र|पुत्री|पत्नी|श्री|late|Late|shri|Shri|Late\.)\s*[:\-]*\s*([a-zA-Z\s]{2,30}|[\u0900-\u097F\s]{2,30})',
        lambda m: m.group(0).replace(m.group(1), " [SCRUBBED] "),
        text
    )
    # 2. Scrub case numbers (e.g. MACC 123/2025, MACC No. 12/2024)
    text = re.sub(
        r'(?:एम\.?ए\.?सी\.?सी\.?|MACC)[.\s]*(?:क्\.?|No\.?|नं\.?)? *[-–:]? *\d{1,6} */ *\d{4}',
        "[CASE_NUMBER_SCRUBBED]",
        text,
        flags=re.IGNORECASE
    )
    # 3. Scrub vehicle numbers (e.g. MP07CA1234, MP-20-BA-0911)
    text = re.sub(
        r'\b[A-Z]{2}[ \-]?\d{1,2}[ \-]?[A-Z]{1,3}[ \-]?\d{3,4}\b',
        "[VEHICLE_NUMBER_SCRUBBED]",
        text,
        flags=re.IGNORECASE
    )
    # 4. Scrub policy numbers
    text = re.sub(
        r'\b[A-Za-z0-9\-/]{8,20}\b',
        "[POLICY_NUMBER_SCRUBBED]",
        text
    )
    # 5. Scrub dates of birth / dates of accident (dd.mm.yyyy, dd/mm/yyyy)
    text = re.sub(
        r'\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b',
        "[DATE_SCRUBBED]",
        text
    )
    return text

def detect_table_shape(text: str) -> str:
    if any(x in text for x in ["अ.", "ब.", "स.", "द."]):
        return "lettered_hi"
    if any(x in text for x in ["1.", "2.", "3.", "4.", "5."]):
        if any(x in text for x in ["शून्य", "निरंक", "nil"]):
            return "numbered_nil"
        return "numbered_clean"
    if "क्रमांक" in text or "मद" in text:
        return "column_krmank"
    return "unordered_or_paragraphs"

def main():
    parser = argparse.ArgumentParser(description="PII scrub and cluster real historical Hindi case text to fixtures")
    parser.add_argument("--src-dir", required=True, help="Directory containing raw OCR text files")
    parser.add_argument("--dest-dir", default="tests/fixtures/lower_court", help="Destination folder for fixtures")
    parser.add_argument("--sample-size", type=int, default=2, help="Number of files to sample per cluster")
    args = parser.parse_args()

    os.makedirs(args.dest_dir, exist_ok=True)
    
    if not os.path.exists(args.src_dir):
        print(f"Source directory does not exist: {args.src_dir}")
        return

    clusters = {}
    for filename in os.listdir(args.src_dir):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(args.src_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        shape = detect_table_shape(content)
        clusters.setdefault(shape, []).append((filename, content))
        
    print(f"Clustering results:")
    for shape, items in clusters.items():
        print(f"  - {shape}: {len(items)} files")
        
        # Sample N files per cluster
        sampled = items[:args.sample_size]
        for idx, (filename, content) in enumerate(sampled, 1):
            scrubbed = scrub_pii(content)
            
            base_name = f"cluster_{shape}_{idx}"
            dest_txt = os.path.join(args.dest_dir, f"{base_name}.txt")
            dest_json = os.path.join(args.dest_dir, f"{base_name}.json")
            
            with open(dest_txt, "w", encoding="utf-8") as out_f:
                out_f.write(scrubbed)
                
            skeleton = {
                "medical_expenses": 0.0,
                "pain_and_suffering": 0.0,
                "transportation": 0.0,
                "special_diet": 0.0,
                "attender_charges": 0.0,
                "future_medical_expenses": 0.0,
                "loss_of_income": 0.0,
                "disability": ""
            }
            with open(dest_json, "w", encoding="utf-8") as out_j:
                json.dump(skeleton, out_j, indent=4)
                
            print(f"Saved fixture: {dest_txt} and verification placeholder {dest_json}")

if __name__ == "__main__":
    main()
