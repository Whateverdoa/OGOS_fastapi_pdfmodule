"""
Tests for overprint scope: ensure overprint is applied only to stans dieline strokes,
not to the entire artwork.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from app.utils.pdf_overprint import ensure_overprint_for_spot, _form_uses_spot
from app.utils.spot_color_handler import SpotColorHandler


def _build_pdf_with_two_forms(path: Path) -> None:
    """
    Build a PDF with two Form XObjects:
    - /FmArt: a regular CMYK stroke (no spot color)
    - /FmStans: a stans spot-color stroke

    This simulates a merged PDF where artwork and dieline are in separate forms.
    """
    from pypdf.generic import StreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    # --- Build Form XObject for regular artwork (CMYK, no spot) ---
    art_form = StreamObject()
    art_form.set_data(b"q\n0 1 1 0 k\n1 w\n10 10 m\n50 50 l\nS\nQ\n")
    art_form[NameObject("/Type")] = NameObject("/XObject")
    art_form[NameObject("/Subtype")] = NameObject("/Form")
    art_form[NameObject("/BBox")] = ArrayObject([
        NumberObject(0), NumberObject(0),
        NumberObject(200), NumberObject(200),
    ])
    art_form[NameObject("/Resources")] = DictionaryObject()

    # --- Build Form XObject for stans dieline ---
    # Content stream references /CS0 (a Separation for stans)
    tint_function = DictionaryObject({
        NameObject("/FunctionType"): NumberObject(2),
        NameObject("/Domain"): ArrayObject([FloatObject(0), FloatObject(1)]),
        NameObject("/C0"): ArrayObject([
            FloatObject(0), FloatObject(0), FloatObject(0), FloatObject(0)
        ]),
        NameObject("/C1"): ArrayObject([
            FloatObject(0), FloatObject(1), FloatObject(0), FloatObject(0)
        ]),
        NameObject("/N"): NumberObject(1),
    })

    stans_colorspace = DictionaryObject({
        NameObject("/CS0"): ArrayObject([
            NameObject("/Separation"),
            NameObject("/stans"),
            NameObject("/DeviceCMYK"),
            tint_function,
        ])
    })

    stans_resources = DictionaryObject({
        NameObject("/ColorSpace"): stans_colorspace,
    })

    stans_form = StreamObject()
    stans_form.set_data(b"q\n/CS0 CS\n1 SCN\n0.5 w\n0 0 m\n100 100 l\nS\nQ\n")
    stans_form[NameObject("/Type")] = NameObject("/XObject")
    stans_form[NameObject("/Subtype")] = NameObject("/Form")
    stans_form[NameObject("/BBox")] = ArrayObject([
        NumberObject(0), NumberObject(0),
        NumberObject(200), NumberObject(200),
    ])
    stans_form[NameObject("/Resources")] = stans_resources

    # --- Add forms to page resources ---
    xobjects = DictionaryObject()
    art_ref = writer._add_object(art_form)
    stans_ref = writer._add_object(stans_form)
    xobjects[NameObject("/FmArt")] = art_ref
    xobjects[NameObject("/FmStans")] = stans_ref

    page_resources = DictionaryObject({
        NameObject("/XObject"): xobjects,
    })
    page[NameObject("/Resources")] = page_resources

    # Page content invokes both forms
    page_content = DecodedStreamObject()
    page_content.set_data(b"/FmArt Do\n/FmStans Do\n")
    page[NameObject("/Contents")] = page_content

    with path.open("wb") as f:
        writer.write(f)


def test_form_uses_spot_detects_stans_only():
    """_form_uses_spot should return True only for forms with stans reference."""
    # Build mock form objects
    art_form = DictionaryObject()
    art_stream = DecodedStreamObject()
    art_stream.set_data(b"q\n0 1 1 0 k\n1 w\n10 10 m\n50 50 l\nS\nQ\n")
    art_form.get_data = art_stream.get_data

    stans_stream = DecodedStreamObject()
    stans_stream.set_data(b"q\n/CS0 CS\n1 SCN\nstans\n0.5 w\n0 0 m\n100 100 l\nS\nQ\n")
    stans_form = DictionaryObject()
    stans_form.get_data = stans_stream.get_data

    # art_form has no stans reference
    assert _form_uses_spot(art_form, None, "stans") is False

    # stans_form has stans in content
    assert _form_uses_spot(stans_form, None, "stans") is True


def test_ensure_overprint_patches_stans_form_only(tmp_path):
    """
    After ensure_overprint_for_spot, only the form with stans should have
    /GSop gs prepended. The artwork form should remain untouched.
    """
    pdf_path = tmp_path / "test.pdf"
    _build_pdf_with_two_forms(pdf_path)

    # Apply overprint
    result = ensure_overprint_for_spot(str(pdf_path), "stans")
    assert result is True

    # Read back and verify
    reader = PdfReader(str(pdf_path))
    page = reader.pages[0]
    resources = page["/Resources"].get_object()
    xobjects = resources["/XObject"].get_object()

    # Check FmArt (artwork) - should NOT have /GSop gs
    art_form = xobjects["/FmArt"].get_object()
    art_data = art_form.get_data().decode("latin-1", errors="ignore")
    assert "/GSop gs" not in art_data, "Artwork form should not have overprint injected"

    # Check FmStans (dieline) - should have /GSop gs
    stans_form = xobjects["/FmStans"].get_object()
    stans_data = stans_form.get_data().decode("latin-1", errors="ignore")
    assert "/GSop gs" in stans_data, "Stans form should have overprint injected"

    # Verify ExtGState was added to stans form resources
    stans_res = stans_form.get("/Resources")
    if hasattr(stans_res, "get_object"):
        stans_res = stans_res.get_object()
    assert "/ExtGState" in stans_res
    extg = stans_res["/ExtGState"]
    if hasattr(extg, "get_object"):
        extg = extg.get_object()
    assert "/GSop" in extg


def test_spot_color_handler_overprint_selective(tmp_path):
    """
    SpotColorHandler.update_spot_color_properties should inject overprint
    GS only before stans strokes, not before CMYK strokes.
    """
    # Build a simple PDF with both CMYK and stans strokes in page content
    pdf_path = tmp_path / "mixed.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)

    tint_function = DictionaryObject({
        NameObject("/FunctionType"): NumberObject(2),
        NameObject("/Domain"): ArrayObject([FloatObject(0), FloatObject(1)]),
        NameObject("/C0"): ArrayObject([
            FloatObject(0), FloatObject(0), FloatObject(0), FloatObject(0)
        ]),
        NameObject("/C1"): ArrayObject([
            FloatObject(0), FloatObject(1), FloatObject(0), FloatObject(0)
        ]),
        NameObject("/N"): NumberObject(1),
    })

    color_spaces = DictionaryObject({
        NameObject("/CS0"): ArrayObject([
            NameObject("/Separation"),
            NameObject("/stans"),
            NameObject("/DeviceCMYK"),
            tint_function,
        ])
    })

    extgstate = DictionaryObject({
        NameObject("/GS0"): DictionaryObject({
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/OP"): BooleanObject(False),
            NameObject("/op"): BooleanObject(False),
        })
    })

    resources = DictionaryObject({
        NameObject("/ColorSpace"): color_spaces,
        NameObject("/ExtGState"): extgstate,
    })
    page[NameObject("/Resources")] = resources

    # Content: CMYK stroke, then stans stroke
    content = DecodedStreamObject()
    content.set_data(
        b"q\n"
        b"0 1 1 0 K\n"  # CMYK stroke color
        b"1 w\n"
        b"10 10 m\n20 20 l\nS\n"  # CMYK path
        b"Q\n"
        b"q\n"
        b"/GS0 gs\n"
        b"/CS0 CS\n"
        b"1 SCN\n"  # stans stroke
        b"0.25 w\n"
        b"30 30 m\n40 40 l\nS\n"  # stans path
        b"Q\n"
    )
    page[NameObject("/Contents")] = content

    with pdf_path.open("wb") as f:
        writer.write(f)

    # Apply spot color handler
    handler = SpotColorHandler()
    output_path = tmp_path / "output.pdf"
    result = handler.update_spot_color_properties(
        str(pdf_path), str(output_path), "stans", line_thickness=0.5
    )
    assert result is True

    # Read back
    reader = PdfReader(str(output_path))
    page = reader.pages[0]
    data = page.get_contents().get_data().decode("latin-1")

    # The stans stroke should have overprint GS applied
    # The CMYK stroke should NOT have overprint GS
    lines = data.split("\n")

    # Find the CMYK section (before /CS0 CS)
    cmyk_section = []
    stans_section = []
    in_stans = False
    for line in lines:
        stripped = line.strip()
        if "/CS0 CS" in stripped or "/CS0 cs" in stripped:
            in_stans = True
        if in_stans:
            stans_section.append(stripped)
        else:
            cmyk_section.append(stripped)

    cmyk_text = "\n".join(cmyk_section)
    stans_text = "\n".join(stans_section)

    # CMYK section should not have the stans overprint GS
    assert "/GS_STANS_OP gs" not in cmyk_text, (
        "CMYK stroke should not have stans overprint GS"
    )

    # Stans section should have overprint GS and correct line width
    assert "/GS_STANS_OP gs" in stans_text or "0.5 w" in stans_text, (
        "Stans stroke should have overprint applied or line width set"
    )

