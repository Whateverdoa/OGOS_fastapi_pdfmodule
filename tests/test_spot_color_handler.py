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

from app.utils.spot_color_handler import SpotColorHandler


def _build_sample_pdf(path: Path, *, color_name: str = "stans") -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)

    tint_function = DictionaryObject({
        NameObject("/FunctionType"): NumberObject(2),
        NameObject("/Domain"): ArrayObject([FloatObject(0), FloatObject(1)]),
        NameObject("/C0"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(0), FloatObject(0)]),
        NameObject("/C1"): ArrayObject([FloatObject(0), FloatObject(0.5), FloatObject(0), FloatObject(0)]),
        NameObject("/N"): NumberObject(1),
    })

    color_spaces = DictionaryObject({
        NameObject("/CS0"): ArrayObject([
            NameObject("/Separation"),
            NameObject(f"/{color_name}"),
            NameObject("/DeviceCMYK"),
            tint_function,
        ])
    })

    extgstate = DictionaryObject({
        NameObject("/GS0"): DictionaryObject({
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/OP"): BooleanObject(False),
            NameObject("/op"): BooleanObject(False),
            NameObject("/OPM"): NumberObject(0),
        })
    })

    resources = DictionaryObject({
        NameObject("/ColorSpace"): color_spaces,
        NameObject("/ExtGState"): extgstate,
    })

    page[NameObject("/Resources")] = resources

    content = DecodedStreamObject()
    content.set_data(b"q\n/GS0 gs\n/CS0 CS\n1 SCN\n0.25 w\n0 0 m\n10 0 l\nS\nQ\n")
    page[NameObject("/Contents")] = content

    with path.open("wb") as handle:
        writer.write(handle)


def test_update_spot_color_properties_enforces_magenta_overprint(tmp_path):
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output.pdf"

    _build_sample_pdf(input_path, color_name="KissCut")

    handler = SpotColorHandler()
    assert handler.update_spot_color_properties(str(input_path), str(output_path), "stans", line_thickness=0.5)

    reader = PdfReader(str(output_path))
    page = reader.pages[0]
    resources = page["/Resources"].get_object()

    color_spaces = resources["/ColorSpace"].get_object()
    cs = color_spaces[NameObject("/CS0")]
    cs_obj = cs.get_object() if hasattr(cs, "get_object") else cs
    assert str(cs_obj[1]) == "/stans"

    tint_function = cs_obj[3].get_object() if hasattr(cs_obj[3], "get_object") else cs_obj[3]
    assert tint_function[NameObject("/FunctionType")] == 2
    assert [float(x) for x in tint_function[NameObject("/C1")]] == [0.0, 1.0, 0.0, 0.0]

    extgstate = resources["/ExtGState"].get_object()
    gs = extgstate[NameObject("/GS0")].get_object()
    assert bool(gs[NameObject("/OP")]) is True
    assert bool(gs[NameObject("/op")]) is True
    assert int(gs[NameObject("/OPM")]) == 1

    stream = page["/Contents"].get_object()
    data = stream.get_data().decode("latin-1")
    assert "0.5 w" in data
    assert data.count("1 SCN") == 1

    # Running in-place should succeed without raising and keep the same guarantees
    assert handler.update_spot_color_properties(str(output_path), str(output_path), "stans", line_thickness=0.75)
    reader = PdfReader(str(output_path))
    data = reader.pages[0].get_contents().get_data().decode("latin-1")
    assert "0.75 w" in data
