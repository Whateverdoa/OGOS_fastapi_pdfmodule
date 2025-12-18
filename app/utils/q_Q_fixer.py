"""
Utility to fix q/Q imbalance in PDF content streams
"""
import pikepdf
from typing import List


def fix_q_Q_imbalance(pdf_path: str, output_path: str = None) -> bool:
    """
    Fix q/Q operator imbalance in PDF content streams.
    
    Removes extra Q operators from the end of content streams
    to balance with q operators.
    
    Args:
        pdf_path: Path to PDF file
        output_path: Optional output path (defaults to in-place)
    
    Returns:
        True if fixed, False if no fix needed or failed
    """
    if output_path is None:
        output_path = pdf_path
    
    try:
        pdf = pikepdf.open(pdf_path)
        fixed = False
        
        for page in pdf.pages:
            if '/Contents' in page:
                content_stream = page['/Contents']
                
                # Only handle single content stream (not array)
                if not isinstance(content_stream, pikepdf.Array):
                    content_bytes = content_stream.read_bytes()
                    content_text = content_bytes.decode('latin-1', errors='replace')
                    
                    # Count q and Q
                    lines = content_text.split('\n')
                    q_count = sum(1 for line in lines if line.strip() == 'q')
                    Q_count = sum(1 for line in lines if line.strip() == 'Q')
                    
                    if Q_count > q_count:
                        # Remove extra Q operators from the end
                        extra_Q = Q_count - q_count
                        fixed_lines = []
                        Q_to_remove = extra_Q
                        
                        # Process lines in reverse to remove trailing Qs
                        for line in reversed(lines):
                            if Q_to_remove > 0 and line.strip() == 'Q':
                                Q_to_remove -= 1
                                # Skip this Q
                                continue
                            fixed_lines.insert(0, line)
                        
                        # Update content stream
                        fixed_text = '\n'.join(fixed_lines)
                        content_stream.write(fixed_text.encode('latin-1'))
                        fixed = True
        
        if fixed:
            pdf.save(output_path)
        
        pdf.close()
        return fixed
        
    except Exception as e:
        print(f"Error fixing q/Q imbalance: {e}")
        return False
