import os
import sys
from PIL import Image, ImageDraw

# Ensure root folder is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.parser_heuristics import parse_extracted_text

def create_mock_scan(output_path="test_scan.png"):
    """
    Creates a mock image of a legal claims document.
    Draws text lines in black on a white background.
    """
    print(f"Creating mock claim document scan at: {output_path}...")
    
    # 800x800 image, white background to fit more lines cleanly
    img = Image.new('RGB', (800, 800), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Write sample lines in high-contrast black
    lines = [
        "BEFORE THE MOTOR ACCIDENTS CLAIMS TRIBUNAL, CHENNAI",
        "M.C.O.P. No. 1205 of 2021",
        "Claimant Name: Shri Rajesh Kumar Sharma",
        "S/o Shri Om Prakash Sharma, Resident of Chennai, Tamil Nadu",
        "Date of Birth of Injured: 12-04-1992 (Age: 32)",
        "Date of Accident: 12-05-2022",
        "Monthly Income: Earns Rs. 25000 per month from private service",
        "Permanent Disability: 40% permanent disability in left leg",
        "Number of dependents: 3 family members",
        "Marital Status: Married",
        "The Tribunal hereby awards a total compensation of Rs. 4,57,240/- as award amount.",
        "Award Section:",
        "1. Disability Compensation : Rs. 2,00,000/-",
        "2. Pain and suffering : Rs. 40,000/-",
        "3. Loss of amenities : Rs. 30,000/-",
        "4. Transportation charges : Rs. 15,000/-",
        "5. Extra nourishment : Rs. 15,000/-",
        "6. Attender charges : Rs. 15,000/-"
    ]
    
    y = 20
    for line in lines:
        d.text((40, y), line, fill=(0, 0, 0))
        y += 38
        
    img.save(output_path)
    print("Mock document scan created successfully!")
    return output_path

def test_ocr_and_parsing():
    print("\n========================================================")
    print("            RUNNING PADDLEOCR SANITY CHECK")
    print("========================================================")
    
    # Create the test image
    img_path = create_mock_scan()
    
    # Try initializing and running PaddleOCR
    try:
        print("\nLoading PaddleOCR (will download model if running for the first time)...")
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(
            enable_mkldnn=False,
            use_textline_orientation=True,
            text_detection_model_name='PP-OCRv5_mobile_det',
            text_recognition_model_name='en_PP-OCRv5_mobile_rec'
        )
        print("PaddleOCR loaded successfully!")
        
        print(f"\nRunning OCR scanning on {img_path}...")
        result = ocr.ocr(img_path)
        
        print("Raw OCR result type:", type(result))
        print("Raw OCR result:")
        import pprint
        pprint.pprint(result)
        
        # We will parse it based on the structure we see
        extracted_lines = []
        if result and len(result) > 0:
            for item in result:
                # 1. Handle PaddleX v3 custom object / dict with 'rec_texts'
                if hasattr(item, 'rec_texts') and item.rec_texts:
                    extracted_lines.extend(item.rec_texts)
                elif isinstance(item, dict) and 'rec_texts' in item:
                    extracted_lines.extend(item['rec_texts'])
                elif hasattr(item, 'get') and item.get('rec_texts'):
                    extracted_lines.extend(item.get('rec_texts'))
                # 2. Handle standard PaddleOCR v2 list structure
                elif isinstance(item, list):
                    for line in item:
                        if isinstance(line, list) and len(line) > 1 and isinstance(line[1], tuple):
                            extracted_lines.append(line[1][0])
                            
        print("\n--- OCR EXTRACTED TEXT LINES ---")
        for i, line in enumerate(extracted_lines):
            print(f"[{i+1:02d}] {line}")
        
        print("\n--- HEURISTIC PARSING RESULTS ---")
        suggestions = parse_extracted_text(extracted_lines)
        for key, val in suggestions.items():
            val_str = str(val).replace('\u20b9', 'Rs.')
            print(f"{key:<20}: {val_str}")
            
    except ImportError:
        print("\n[ERROR] PaddleOCR is not installed in the current environment!")
        print("Please ensure you are running this script inside the virtual environment:")
        print("  .venv\\Scripts\\python test_ocr.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] OCR Execution failed: {str(e)}")
        sys.exit(1)

def test_vision_cross_check_trigger():
    from unittest.mock import patch, MagicMock
    from backend.ocr import ocr_page_with_vision
    
    mock_paddle_lines = ["Claimant Name: Rajesh", "Age: 32", "Award: 200000"]
    mock_vision_text = "Claimant Name: Rajesh\nAge: 32\nAward: 200000"
    
    with patch("backend.ocr.classify_scanned_page", return_value="text-heavy"), \
         patch("backend.ocr.call_paddle_ocr", return_value=(mock_paddle_lines, 0.95, True)) as mock_paddle, \
         patch("backend.ocr.score_ocr_page_quality", return_value=0.95), \
         patch("backend.ocr.call_vision_model", return_value=mock_vision_text) as mock_vision, \
         patch("backend.ocr.Image.open") as mock_image_open:
        
        # Mock PIL Image
        mock_img = MagicMock()
        mock_img.convert.return_value = mock_img
        mock_img.size = (800, 800)
        mock_image_open.return_value = mock_img
        
        # Mock preprocessing helpers
        with patch("backend.ocr.preprocess_for_vision", return_value=mock_img), \
             patch("backend.ocr.image_to_base64", return_value="mock_b64"), \
             patch("backend.ocr._vision_is_paused", return_value=False), \
             patch("backend.ocr.OCR_ENABLE_VISION_ESCALATION", True):
             
            # 1. Test high_court track: should trigger vision cross-check even though paddle_good is True
            # We pass fitz_text to bypass the dynamic language detection probe (which calls call_paddle_ocr)
            lines_hc, meta_hc = ocr_page_with_vision(
                page_idx=0,
                total_pages=1,
                rendered_img_path="dummy_path.png",
                fitz_text="mock digital layer text to bypass dynamic language probe",
                pdf_path=None,
                vision_available=True,
                paddle_available=True,
                track="high_court"
            )
            
            mock_paddle.assert_called_once()
            mock_vision.assert_called_once()
            assert meta_hc.get("vision_cross_checked") is True
            assert "[VISION CROSS-CHECK]" in lines_hc
            assert "Age: 32" in lines_hc
            
            # Reset mock counts for lower_court test
            mock_paddle.reset_mock()
            mock_vision.reset_mock()
            
            # 2. Test lower_court track: should NOT trigger vision cross-check when paddle_good is True
            # We use page_idx=2 to bypass the page 0/1 direct vision override
            lines_lc, meta_lc = ocr_page_with_vision(
                page_idx=2,
                total_pages=3,
                rendered_img_path="dummy_path.png",
                pdf_path=None,
                vision_available=True,
                paddle_available=True,
                track="lower_court"
            )
            
            mock_paddle.assert_called_once()
            mock_vision.assert_not_called()
            assert meta_lc.get("vision_cross_checked") is False
            assert "[VISION CROSS-CHECK]" not in lines_lc

if __name__ == "__main__":
    test_ocr_and_parsing()
