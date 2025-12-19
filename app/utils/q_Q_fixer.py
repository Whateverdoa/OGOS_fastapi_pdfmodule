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
    For arrays of content streams, treats them as a single logical unit.

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

                    # Handle array of content streams - treat as single unit
                    if isinstance(contents, pikepdf.Array):
                        streams = [s for s in contents if isinstance(s, pikepdf.Stream)]
                        if streams:
                            if _fix_operator_balance_multi(streams):
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


def _fix_operator_balance_multi(streams: list) -> bool:
    """
    Fix operator balance across multiple content streams treated as one unit.

    This handles cases where q is in stream 0 and Q is in stream 1.
    We track state across streams and only add missing closers at the very end.
    """
    try:
        q_stack = bt_stack = bmc_stack = 0
        all_fixed_contents = []
        any_modified = False

        for stream_idx, stream_obj in enumerate(streams):
            content_bytes = bytes(stream_obj.read_bytes())
            content_str = content_bytes.decode('latin-1', errors='ignore')

            lines = content_str.split('\n')
            balanced_lines = []

            for line in lines:
                stripped = line.strip()
                current_line = line

                # Count operators using token-based approach
                tokens = stripped.split()

                q_opens = 0
                q_closes = 0
                has_bt = False
                has_et = False
                has_bmc = False
                has_emc = False

                for token in tokens:
                    if token == 'q':
                        q_opens += 1
                    elif token == 'Q':
                        q_closes += 1
                    elif token == 'BT':
                        has_bt = True
                    elif token == 'ET':
                        has_et = True
                    elif token in ('BMC', 'BDC'):
                        has_bmc = True
                    elif token == 'EMC':
                        has_emc = True

                # Process q/Q balance
                q_stack += q_opens
                valid_closes = min(q_closes, q_stack)
                excess_closes = q_closes - valid_closes
                q_stack -= valid_closes

                if excess_closes > 0:
                    for _ in range(excess_closes):
                        current_line = re.sub(r'\s+Q(\s*)$', r'\1', current_line)
                        if current_line.strip() == 'Q':
                            current_line = ''
                        logger.debug(f"Removing extra Q in stream {stream_idx}")
                    any_modified = True

                # Process BT/ET
                if has_bt:
                    bt_stack += 1
                if has_et:
                    if bt_stack > 0:
                        bt_stack -= 1
                    else:
                        current_line = re.sub(r'\bET\b', '', current_line)
                        logger.debug(f"Removing extra ET in stream {stream_idx}")
                        any_modified = True

                # Process BMC/BDC/EMC
                if has_bmc:
                    bmc_stack += 1
                if has_emc:
                    if bmc_stack > 0:
                        bmc_stack -= 1
                    else:
                        current_line = re.sub(r'\bEMC\b', '', current_line)
                        logger.debug(f"Removing extra EMC in stream {stream_idx}")
                        any_modified = True

                if current_line.strip():
                    balanced_lines.append(current_line)
                elif line.strip():
                    pass  # Skip lines that became empty
                else:
                    balanced_lines.append(line)

            all_fixed_contents.append('\n'.join(balanced_lines))

        # Add missing closers to the LAST stream only
        last_stream_content = all_fixed_contents[-1]
        closers = []

        for _ in range(bt_stack):
            closers.append('ET')
            logger.debug("Adding missing ET operator")
            any_modified = True

        for _ in range(bmc_stack):
            closers.append('EMC')
            logger.debug("Adding missing EMC operator")
            any_modified = True

        for _ in range(q_stack):
            closers.append('Q')
            logger.debug("Adding missing Q operator")
            any_modified = True

        if closers:
            all_fixed_contents[-1] = last_stream_content + '\n' + '\n'.join(closers)

        # Write back modified streams
        if any_modified:
            for i, stream_obj in enumerate(streams):
                original = bytes(stream_obj.read_bytes()).decode('latin-1', errors='ignore')
                if all_fixed_contents[i] != original:
                    stream_obj.write(all_fixed_contents[i].encode('latin-1'))
            return True

        return False

    except Exception as e:
        logger.error(f"Failed to process multi-stream content: {e}")
        return False


def _fix_operator_balance(stream_obj) -> bool:
    """
    Fix operator balance in a content stream.

    Handles three operator pairs:
    - q/Q (graphics state) - including inline like "q 0.1 0 0 0.1 0 0 cm"
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
            current_line = line

            # Count q/Q operators on the line using token-based approach
            # This handles cases like "q ... Q" on same line
            tokens = stripped.split()

            # Count openers first
            q_opens = 0
            q_closes = 0
            has_bt = False
            has_et = False
            has_bmc = False
            has_emc = False

            for i, token in enumerate(tokens):
                if token == 'q':
                    q_opens += 1
                elif token == 'Q':
                    q_closes += 1
                elif token == 'BT':
                    has_bt = True
                elif token == 'ET':
                    has_et = True
                elif token in ('BMC', 'BDC'):
                    has_bmc = True
                elif token == 'EMC':
                    has_emc = True

            # Process q/Q balance for this line
            # Add all opens to stack
            q_stack += q_opens

            # Process closes - remove excess
            valid_closes = min(q_closes, q_stack)
            excess_closes = q_closes - valid_closes
            q_stack -= valid_closes

            if excess_closes > 0:
                # Remove excess Q operators from line
                for _ in range(excess_closes):
                    # Remove last Q from line
                    current_line = re.sub(r'\s+Q(\s*)$', r'\1', current_line)
                    if current_line.strip() == 'Q':
                        current_line = ''
                    logger.debug(f"Removing extra Q operator (excess: {excess_closes})")

            # Process BT/ET
            if has_bt:
                bt_stack += 1
            if has_et:
                if bt_stack > 0:
                    bt_stack -= 1
                else:
                    current_line = re.sub(r'\bET\b', '', current_line)
                    logger.debug("Removing extra ET operator")

            # Process BMC/BDC/EMC
            if has_bmc:
                bmc_stack += 1
            if has_emc:
                if bmc_stack > 0:
                    bmc_stack -= 1
                else:
                    current_line = re.sub(r'\bEMC\b', '', current_line)
                    logger.debug("Removing extra EMC operator")

            # Only add non-empty lines
            if current_line.strip():
                balanced_lines.append(current_line)
            elif line.strip():
                # Line became empty after removing operators - skip it
                pass
            else:
                # Preserve empty lines
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
