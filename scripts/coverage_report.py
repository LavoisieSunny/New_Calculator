import os
import json
import sys

# Configure stdout for utf-8 to prevent encoding errors on windows
sys.stdout.reconfigure(encoding='utf-8')

from backend.parser_heuristics import parse_hindi_extracted_text

def main():
    fixtures_dir = "tests/fixtures/lower_court"
    if not os.path.exists(fixtures_dir):
        print(f"Fixtures directory not found: {fixtures_dir}")
        return

    files = [f for f in os.listdir(fixtures_dir) if f.endswith(".txt")]
    if not files:
        print("No text fixtures found.")
        return

    total_files = len(files)
    structural_blocks_found = 0
    total_fields_checked = 0
    correct_fields_matched = 0

    print(f"Running Hindi Parser Coverage Report over {total_files} fixtures...")
    print("=" * 70)

    for f in sorted(files):
        name = os.path.splitext(f)[0]
        txt_path = os.path.join(fixtures_dir, f)
        json_path = os.path.join(fixtures_dir, f"{name}.json")

        if not os.path.exists(json_path):
            continue

        with open(txt_path, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines() if line.strip()]

        with open(json_path, "r", encoding="utf-8") as file:
            expected = json.load(file)

        res = parse_hindi_extracted_text(lines)
        
        has_struct = True
        for msg in res.get("needs_manual_review", []):
            if "no structural table block detected" in msg.lower():
                has_struct = False
                break
        if has_struct:
            structural_blocks_found += 1

        print(f"Fixture: {name:<40} StructBlock: {'YES' if has_struct else 'NO'}")
        
        for field, expected_val in expected.items():
            actual_val = res.get(field)
            if actual_val is None:
                actual_val = 0.0 if field != "disability" else ""
            
            is_correct = (actual_val == expected_val)
            total_fields_checked += 1
            if is_correct:
                correct_fields_matched += 1
            else:
                print(f"  [MISMATCH] Field '{field}': Expected {expected_val}, got {actual_val}")

    print("=" * 70)
    struct_pct = (structural_blocks_found / total_files) * 100.0 if total_files > 0 else 0.0
    field_pct = (correct_fields_matched / total_fields_checked) * 100.0 if total_fields_checked > 0 else 0.0
    
    print(f"Summary statistics:")
    print(f"  - Structural block extraction rate: {struct_pct:.1f}% ({structural_blocks_found}/{total_files})")
    print(f"  - Field accuracy rate:              {field_pct:.1f}% ({correct_fields_matched}/{total_fields_checked})")

if __name__ == "__main__":
    main()
