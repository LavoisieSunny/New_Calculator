import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.request
import asyncio
import threading
import time

from backend.ocr import (
    call_vision_model,
    is_vision_model_available,
    perform_targeted_ocr_lower_court,
    _VISION_SEMAPHORE,
    OCR_PAGE_TIMEOUT,
    OCR_HYBRID_LABEL
)

class TestOCRTimeouts(unittest.TestCase):
    def setUp(self):
        # Reset consecutive failures and paused status
        from backend.ocr import _VISION_STATE_LOCK
        with _VISION_STATE_LOCK:
            import backend.ocr
            backend.ocr._VISION_CONSECUTIVE_FAILURES = 0
            backend.ocr._VISION_PAUSED_UNTIL = 0.0
        
        # Reset semaphore
        while _VISION_SEMAPHORE.acquire(blocking=False):
            pass
        _VISION_SEMAPHORE.release()

    @patch('urllib.request.urlopen')
    def test_call_vision_model_http_timeout(self, mock_urlopen):
        # Simulate a socket timeout inside urllib.request.urlopen
        import socket
        mock_urlopen.side_effect = urllib.error.URLError(reason=socket.timeout("timed out"))
        
        # Should return "" immediately and log timeout, rather than crashing
        res = call_vision_model("mock_base64_image", page_num=1)
        self.assertEqual(res, "")

    def test_call_vision_model_semaphore_timeout(self):
        # Acquire the semaphore in another thread to block
        _VISION_SEMAPHORE.acquire()
        
        try:
            # call_vision_model should timeout on acquiring the semaphore (90s limit, we'll patch it to be fast)
            with patch('backend.ocr._VISION_SEMAPHORE.acquire', return_value=False):
                res = call_vision_model("mock_base64_image", page_num=1)
                self.assertEqual(res, "")
        finally:
            _VISION_SEMAPHORE.release()

    @patch('urllib.request.urlopen')
    def test_is_vision_model_available_offline(self, mock_urlopen):
        # Simulate Ollama is offline
        mock_urlopen.side_effect = Exception("Connection refused")
        available = is_vision_model_available()
        self.assertFalse(available)

    @patch('backend.ocr.is_vision_model_available')
    @patch('backend.ocr.is_paddle_available')
    @patch('pypdfium2.PdfDocument')
    def test_targeted_ocr_healthcheck_fallback(self, mock_doc, mock_paddle, mock_vision):
        mock_vision.return_value = False
        mock_paddle.return_value = True
        
        mock_doc_ctx = mock_doc.return_value.__enter__.return_value
        mock_doc_ctx.__len__.return_value = 5
        
        mock_page = MagicMock()
        mock_bitmap = MagicMock()
        mock_pil_img = MagicMock()
        mock_pil_img.size = (100, 100)
        mock_pil_img.convert.return_value = mock_pil_img
        
        mock_doc_ctx.__getitem__.return_value = mock_page
        mock_page.render.return_value = mock_bitmap
        mock_bitmap.to_pil.return_value = mock_pil_img
        
        # Test perform_targeted_ocr_lower_court behaves gracefully with offline Ollama
        # (It shouldn't crash, and will use paddle)
        with patch('backend.ocr.find_relevant_pages_by_heading', return_value={}):
            with patch('backend.ocr.classify_scanned_page', return_value="blank"):
                lines, debug = perform_targeted_ocr_lower_court("mock_file.pdf")
                self.assertEqual(lines, [])
                self.assertEqual(debug["ocr_engine_used"], OCR_HYBRID_LABEL)

    def test_result_container_incremental_update(self):
        container = {}
        # Test perform_targeted_ocr_lower_court updates result_container
        # Mock rendering and dependencies to isolate result_container updating
        with patch('backend.ocr.is_vision_model_available', return_value=True), \
             patch('backend.ocr.is_paddle_available', return_value=True), \
             patch('backend.ocr.find_relevant_pages_by_heading', return_value={"heading1": [0]}), \
             patch('pypdfium2.PdfDocument') as mock_doc:
            
            mock_doc_ctx = mock_doc.return_value.__enter__.return_value
            mock_doc_ctx.__len__.return_value = 5
            
            mock_page = MagicMock()
            mock_bitmap = MagicMock()
            mock_pil_img = MagicMock()
            mock_pil_img.size = (100, 100)
            mock_pil_img.convert.return_value = mock_pil_img
            
            mock_doc_ctx.__getitem__.return_value = mock_page
            mock_page.render.return_value = mock_bitmap
            mock_bitmap.to_pil.return_value = mock_pil_img
            
            with patch('backend.ocr.classify_scanned_page', return_value="blank"):
                perform_targeted_ocr_lower_court("mock_file.pdf", result_container=container)
                
                # Should have populated target_pages and page_idxs
                self.assertIn("target_pages", container)
                self.assertEqual(container["target_pages"], {"heading1": [0]})
                self.assertIn("page_idxs", container)
                # target_pages has [0], unconditional is [0, 1, 4] for 5 pages total_pages
                self.assertEqual(container["page_idxs"], [0, 1, 4])

if __name__ == '__main__':
    unittest.main()
