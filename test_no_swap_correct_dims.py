
import unittest
from unittest.mock import MagicMock, patch
from app.core.pdf_processor import PDFProcessor
from app.models.schemas import PDFJobConfig

class TestNoSwap(unittest.TestCase):
    @patch('app.core.pdf_processor.PDFAnalyzer')
    @patch('app.core.pdf_processor.PDFProcessor._process_standard_shape')
    def test_no_swap_when_correct(self, mock_process_shape, MockAnalyzer):
        processor = PDFProcessor()
        
        # Scenario: Correct dimensions
        # PDF is 70x48 mm
        mock_instance = MockAnalyzer.return_value
        mock_instance.analyze_pdf.return_value = {
            'mediabox': {'x0': 0, 'y0': 0, 'x1': 70.0, 'y1': 48.0},
            'trimbox': {'x0': 0, 'y0': 0, 'x1': 70.0, 'y1': 48.0},
            'spot_colors': []
        }
        
        # Config is ALSO 70x48 (Horizontal)
        job_config = PDFJobConfig(
            reference="test_correct",
            shape="rectangle",
            width=70.0,  # MATCHES PDF WIDTH
            height=48.0, # MATCHES PDF HEIGHT
            spot_color_name="stans",
            line_thickness=0.5
        )
        
        mock_process_shape.return_value = "dummy.pdf"
        processor.process_pdf("dummy.pdf", job_config)
        
        args, _ = mock_process_shape.call_args
        passed_config = args[1]
        
        print(f"\nOriginal Config: {job_config.width} x {job_config.height}")
        print(f"Passed Config:   {passed_config.width} x {passed_config.height}")
        
        if passed_config.width == 70.0 and passed_config.height == 48.0:
             print("SUCCESS: Dimensions were NOT swapped (as expected).")
        else:
             print("FAILURE: Dimensions were swapped incorrectly.")

if __name__ == '__main__':
    unittest.main()
