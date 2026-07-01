import os
import sys
from fastapi.testclient import TestClient

# Ensure root folder is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.main import app

client = TestClient(app)

def test_download_docx_endpoint():
    print("\nRunning automated tests for `/api/ocr/download-docx` endpoint...")
    
    mock_payload = {
        "raw_text": [
            "BEFORE THE MOTOR ACCIDENTS CLAIMS TRIBUNAL, CHENNAI",
            "M.C.O.P. No. 1205 of 2021",
            "Claimant Name: Shri Rajesh Kumar Sharma",
            "S/o Shri Om Prakash Sharma, Resident of Chennai, Tamil Nadu",
            "The Tribunal hereby awards a total compensation of Rs. 4,57,240/- as award amount."
        ],
        "filename": "test_judgment.pdf"
    }
    
    # Send request to endpoint
    response = client.post("/api/ocr/download-docx", json=mock_payload)
    
    # Assert successful response
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
    
    # Assert correct content type
    expected_content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response.headers.get("content-type") == expected_content_type, \
        f"Expected content type {expected_content_type} but got {response.headers.get('content-type')}"
        
    # Assert content-disposition header exposable and contains filename
    assert "content-disposition" in response.headers, "content-disposition header missing"
    assert 'attachment; filename="test_judgment.pdf.docx"' in response.headers["content-disposition"]
    
    # Verify file content is valid docx (PK zip archive magic bytes)
    content = response.content
    assert content.startswith(b"PK\x03\x04"), "Returned content is not a valid zip/docx file"
    
    # Let's open it using python-docx to verify content integrity!
    import io
    from docx import Document
    
    doc = Document(io.BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    
    # Assert headers/title
    assert "Extracted Document Text (OCR)" in paragraphs
    assert "Source file: test_judgment.pdf" in paragraphs[1]
    
    # Assert mock lines exist in docx
    assert "BEFORE THE MOTOR ACCIDENTS CLAIMS TRIBUNAL, CHENNAI" in paragraphs
    assert "M.C.O.P. No. 1205 of 2021" in paragraphs
    assert "Claimant Name: Shri Rajesh Kumar Sharma" in paragraphs
    
    print("All tests passed successfully for Word docx download endpoint!")

if __name__ == "__main__":
    test_download_docx_endpoint()
