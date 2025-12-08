"""
PDF Overprint Utility

Functions for managing overprint settings in PDFs, particularly for spot colors.
"""

import logging

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, DictionaryObject, NameObject, NumberObject

logger = logging.getLogger(__name__)


def _form_uses_spot(xo, xr, spot_name: str) -> bool:
    """
    Return True only if the Form XObject explicitly references the spot color
    in its content stream or ColorSpace resources.
    """
    # Check content stream for spot name (case-insensitive)
    if hasattr(xo, "get_data"):
        try:
            data = xo.get_data().decode("latin-1", errors="ignore")
        except Exception:
            data = ""
        if spot_name in data or spot_name.lower() in data.lower():
            return True

    # Check ColorSpace resources for Separation referencing spot
    if xr and "/ColorSpace" in xr:
        cs = xr["/ColorSpace"]
        if hasattr(cs, "get_object"):
            cs = cs.get_object()
        for _, cs_def in getattr(cs, "items", lambda: [])():
            cs_str = str(cs_def)
            if spot_name in cs_str or spot_name.lower() in cs_str.lower():
                return True

    return False


def ensure_overprint_for_spot(pdf_path: str, spot_name: str = "stans") -> bool:
    """
    Ensure that drawing operations using a given spot (e.g., stans)
    in Form XObjects run with overprint enabled (OP/op true).

    Implementation: scans page XObjects; for each Form whose content or
    resources **explicitly** mention the spot name, injects an ExtGState
    with /OP true, /op true, and prepends '/GSop gs' at the start of the
    form stream.

    Note: Forms named like /fzFrm* (PyMuPDF overlays) are NOT auto-patched;
    they must still contain evidence of the spot color.

    Args:
        pdf_path: Path to the PDF file (modified in place)
        spot_name: Name of the spot color to enable overprint for

    Returns:
        True if successful, False otherwise
    """
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        patched = False

        for page in reader.pages:
            resources = page.get("/Resources")
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            if not resources or "/XObject" not in resources:
                writer.add_page(page)
                continue

            xobjs = resources["/XObject"]
            if hasattr(xobjs, "get_object"):
                xobjs = xobjs.get_object()

            # iterate XObjects
            for name, xo in list(xobjs.items()):
                if hasattr(xo, "get_object"):
                    xo = xo.get_object()
                subtype = str(xo.get("/Subtype")) if hasattr(xo, "get") else ""
                if subtype != "/Form":
                    continue

                xr = xo.get("/Resources") if hasattr(xo, "get") else None
                if hasattr(xr, "get_object"):
                    xr = xr.get_object()

                # Only patch forms that explicitly use the spot color
                if not _form_uses_spot(xo, xr, spot_name):
                    continue

                # Ensure ExtGState exists on the form
                if xr is None:
                    xr = DictionaryObject()
                    xo[NameObject("/Resources")] = xr
                if "/ExtGState" not in xr:
                    xr[NameObject("/ExtGState")] = DictionaryObject()
                extg = xr["/ExtGState"]
                if hasattr(extg, "get_object"):
                    extg = extg.get_object()

                gs_dict = DictionaryObject()
                gs_dict.update(
                    {
                        NameObject("/Type"): NameObject("/ExtGState"),
                        NameObject("/OP"): BooleanObject(True),
                        NameObject("/op"): BooleanObject(True),
                        NameObject("/OPM"): NumberObject(1),
                    }
                )
                gs_ref = writer._add_object(gs_dict)
                extg[NameObject("/GSop")] = gs_ref

                # Prepend '/GSop gs' to the form stream
                if hasattr(xo, "get_data") and hasattr(xo, "set_data"):
                    try:
                        current = xo.get_data()
                    except Exception:
                        current = b""
                    xo.set_data(b"/GSop gs\n" + current)
                    patched = True

            writer.add_page(page)

        if patched:
            with open(pdf_path, "wb") as f:
                writer.write(f)
        return True
    except FileNotFoundError as e:
        logger.error("Overprint patch failed - file not found: %s", e)
        return False
    except OSError as e:
        logger.error("Overprint patch failed - I/O error: %s", e)
        return False
    except KeyError as e:
        logger.warning("Overprint patch skipped - missing PDF key: %s", e)
        return False

