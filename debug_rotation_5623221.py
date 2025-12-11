
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.core.pdf_analyzer import PDFAnalyzer

def analyze_file(path):
    print(f"Analyzing {path}...")
    analyzer = PDFAnalyzer()
    try:
        analysis = analyzer.analyze_pdf(path)
        print("\n--- Analysis Result ---")
        
        mediabox = analysis.get('mediabox', {})
        trimbox = analysis.get('trimbox', {})
        
        print(f"MediaBox: {mediabox}")
        print(f"TrimBox: {trimbox}")
        
        if trimbox:
            width = abs(trimbox['x1'] - trimbox['x0'])
            height = abs(trimbox['y1'] - trimbox['y0'])
            print(f"Calculated Width (mm): {width:.2f}")
            print(f"Calculated Height (mm): {height:.2f}")
        elif mediabox:
            width = abs(mediabox['x1'] - mediabox['x0'])
            height = abs(mediabox['y1'] - mediabox['y0'])
            print(f"Calculated Width (mm): {width:.2f}")
            print(f"Calculated Height (mm): {height:.2f}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    target_pdf = "pdf_storage/original/5623221_8841620_original.pdf"
    if os.path.exists(target_pdf):
        analyze_file(target_pdf)
    else:
        print(f"File not found: {target_pdf}")
