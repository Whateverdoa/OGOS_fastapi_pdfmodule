"""
Utility to fix operator imbalances in PDF content streams.

Handles three operator pairs:
- q/Q (graphics state save/restore)
- BT/ET (text object begin/end)
- BMC/BDC/EMC (marked content begin/end)

Ghostscript's pdfwrite device can introduce imbalances during font embedding.
This utility removes excess closing operators and adds missing closers.
"""
import pikepdf
import re
import logging

logger = logging.getLogger(__name__)


def fix_q_Q_imbalance(pdf_path: str, output_path: str = None) -> bool:
    """
    Fix operator imbalances (q/Q, BT/ET, BMC/EMC) in PDF content streams.

    Removes excess closing operators and adds missing closers at end of streams.

    Args:
        pdf_path: Path to input PDF
        output_path: Path to output PDF (overwrites input if None)

    Returns:
        True if fixes were applied, False otherwise
    """
    if output_path is None:
        output_path = pdf_path
    
    try:
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            fixes_applied = False
            
            for page_num, page in enumerate(pdf.pages, 1):
                if '/Contents' in page:
                    contents = page['/Contents']
                    
                    # Handle array of content streams
                    if isinstance(contents, pikepdf.Array):
                        for stream in contents:
                            if isinstance(stream, pikepdf.Stream):
                                if _fix_operator_balance(stream):
                                    fixes_applied = True
                                    logger.info(f"Fixed operator imbalance in page {page_num}")
                    
                    # Handle single content stream
                    elif isinstance(contents, pikepdf.Stream):
                        if _fix_operator_balance(contents):
                            fixes_applied = True
                            logger.info(f"Fixed operator imbalance in page {page_num}")
            
            if fixes_applied:
                pdf.save(output_path)
                logger.info(f"Saved repaired PDF to {output_path}")
            
            return fixes_applied
            
    except Exception as e:
        logger.error(f"Failed to fix q/Q imbalance: {e}")
        return False


def _fix_operator_balance(stream_obj) -> bool:
    """
    Fix operator balance in a content stream.

    Handles three operator pairs:
    - q/Q (graphics state)
    - BT/ET (text objects)
    - BMC|BDC/EMC (marked content)

    Removes excess closing operators and adds missing closers at end.

    Args:
        stream_obj: pikepdf Stream object

    Returns:
        True if any fixes were applied
    """
    try:
        content_bytes = bytes(stream_obj.read_bytes())
        content_str = content_bytes.decode('latin-1', errors='ignore')

        lines = content_str.split('\n')
        q_stack = bt_stack = bmc_stack = 0
        balanced_lines = []

        for line in lines:
            stripped = line.strip()

            # q/Q handling
            if stripped == 'q':
                q_stack += 1
                balanced_lines.append(line)
            elif stripped == 'Q':
                if q_stack > 0:
                    q_stack -= 1
                    balanced_lines.append(line)
                else:
                    logger.debug("Removing extra Q operator")
                    continue

            # BT/ET handling
            elif stripped == 'BT':
                bt_stack += 1
                balanced_lines.append(line)
            elif stripped == 'ET':
                if bt_stack > 0:
                    bt_stack -= 1
                    balanced_lines.append(line)
                else:
                    logger.debug("Removing extra ET operator")
                    continue

            # BMC/BDC/EMC handling (handles /Name BMC, /OC/R5 BDC, etc.)
            elif re.match(r'^/[\w/]+\s+(BMC|BDC)$', stripped) or stripped in ('BMC', 'BDC'):
                bmc_stack += 1
                balanced_lines.append(line)
            elif stripped == 'EMC':
                if bmc_stack > 0:
                    bmc_stack -= 1
                    balanced_lines.append(line)
                else:
                    logger.debug("Removing extra EMC operator")
                    continue

            else:
                balanced_lines.append(line)

        # Add missing closing operators (innermost to outermost)
        for _ in range(bt_stack):
            balanced_lines.append('ET')
            logger.debug("Adding missing ET operator")

        for _ in range(bmc_stack):
            balanced_lines.append('EMC')
            logger.debug("Adding missing EMC operator")

        for _ in range(q_stack):
            balanced_lines.append('Q')
            logger.debug("Adding missing Q operator")

        fixed_content = '\n'.join(balanced_lines)
        if fixed_content != content_str:
            stream_obj.write(fixed_content.encode('latin-1'))
            return True

        return False

    except Exception as e:
        logger.error(f"Failed to process content stream: {e}")
        return False
