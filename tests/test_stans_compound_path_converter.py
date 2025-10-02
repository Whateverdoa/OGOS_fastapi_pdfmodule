from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
)

from app.utils.stans_compound_path_converter import StansCompoundPathConverter


def _make_stream(data: str, resources: DictionaryObject) -> DecodedStreamObject:
    stream = DecodedStreamObject()
    stream.set_data(data.encode("latin-1"))
    stream[NameObject("/Resources")] = resources
    return stream


def _make_resources() -> DictionaryObject:
    return DictionaryObject({
        NameObject("/ColorSpace"): DictionaryObject({
            NameObject("/CS0"): ArrayObject([
                NameObject("/Separation"),
                NameObject("/stans"),
                NameObject("/DeviceCMYK"),
                NameObject("/Identity"),
            ])
        })
    })


def test_recurses_into_child_xobjects_and_combines_sequences():
    converter = StansCompoundPathConverter()

    inner_resources = _make_resources()
    inner_stream = _make_stream(
        "\n".join([
            "q",
            "/CS0 CS",
            "1 SCN",
            "0 0 m",
            "10 0 l",
            "S",
            "Q",
            "q",
            "/CS0 CS",
            "1 SCN",
            "10 10 m",
            "20 10 l",
            "S",
            "Q",
        ]),
        inner_resources,
    )

    middle_resources = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({
            NameObject("/X1"): inner_stream
        })
    })
    middle_stream = _make_stream("/X1 Do\n", middle_resources)

    page_resources = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({
            NameObject("/X2"): middle_stream
        }),
        NameObject("/ColorSpace"): DictionaryObject({
            NameObject("/CS0"): ArrayObject([
                NameObject("/Separation"),
                NameObject("/stans"),
                NameObject("/DeviceCMYK"),
                NameObject("/Identity"),
            ])
        })
    })

    page_stream = _make_stream("/X2 Do\n", page_resources)

    stats = converter._process_stream(page_stream, {"/CS0"}, page_resources)

    assert stats["stans_sequences_found"] == 2
    assert stats["compound_paths_created"] == 1

    combined_text = inner_stream.get_data().decode("latin-1")
    assert combined_text.count("\nS\n") == 1
