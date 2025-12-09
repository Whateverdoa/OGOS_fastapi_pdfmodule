
import unittest
from unittest.mock import MagicMock, patch
from app.core.pdf_processor import PDFProcessor
from app.models.schemas import PDFJobConfig, ShapeType

class TestDimensionSwap(unittest.TestCase):
    @patch('app.core.pdf_processor.PDFAnalyzer')
    @patch('app.core.pdf_processor.PDFProcessor._process_standard_shape')
    def test_smart_dimension_swap(self, mock_process_shape, MockAnalyzer):
        # Setup
        processor = PDFProcessor()
        
        # Mock analyzer to return horizontal dimensions (70x48 mm)
        # 70mm * 2.83465 = ~198.4 points
        # 48mm * 2.83465 = ~136.1 points
        mock_instance = MockAnalyzer.return_value
        mock_instance.analyze_pdf.return_value = {
            'mediabox': {'x0': 0, 'y0': 0, 'x1': 70.0, 'y1': 48.0}, # 70x48mm
            'trimbox': {'x0': 0, 'y0': 0, 'x1': 70.0, 'y1': 48.0},  # 70x48mm
            'spot_colors': []
        }
        
        # Job Config: Vertical (48x70 mm)
        job_config = PDFJobConfig(
            reference="test_swap",
            shape="rectangle",
            width=48.0,
            height=70.0,
            spot_color_name="stans",
            line_thickness=0.5
        )
        
        # Execution
        # We need to mock _process_standard_shape because it does real file ops we want to avoid
        # But we DO want to test the logic inside process_pdf BEFORE it calls _process_standard_shape
        mock_process_shape.return_value = "dummy_output.pdf"
        
        processor.process_pdf("dummy_input.pdf", job_config)
        
        # Verification
        # Check what arguments _process_standard_shape was called with
        # Specifically, check if job_config.width/height were swapped
        args, _ = mock_process_shape.call_args
        passed_config = args[1]
        
        print(f"\nOriginal Config: 48.0 x 70.0")
        print(f"Passed Config:   {passed_config.width} x {passed_config.height}")
        
        # Expectation: They SHOULD be swapped to 70.0 x 48.0 if logic exists
        # Currently logic does NOT exist, so this test should show 48.0 x 70.0
        
        if passed_config.width == 70.0 and passed_config.height == 48.0:
             print("SUCCESS: Dimensions were swapped!")
        else:
             print("FAILURE: Dimensions were NOT swapped.")

if __name__ == '__main__':
    unittest.main()
