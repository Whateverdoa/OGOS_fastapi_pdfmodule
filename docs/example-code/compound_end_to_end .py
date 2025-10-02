import pymupdf as fitz

def process_pdf(in_path, out_path, shape_kind="custom"):
    doc = fitz.open(in_path)

    for page in doc:
        # 1) vector paths ophalen
        stroke_paths = extract_stroke_paths(page)

        if shape_kind in ("rect", "square", "circle", "oval"):
            # Regular: verwijderen + vervangen
            # hier zou je bbox bepalen (bijv. grootste stroke path)
            if stroke_paths:
                bbox = stroke_paths[0]["rect"]
                if shape_kind in ("rect", "square"):
                    replace_regular_with_box(page, bbox)
                else:
                    # simpele heuristic: cirkel binnen bbox
                    center = bbox.tl + (bbox.width/2, bbox.height/2)
                    radius = min(bbox.width, bbox.height)/2
                    # evt. eerst weghalen:
                    page.add_redact_annot(bbox)
                    page.apply_redactions(images=0, drawings=2, text=0)
                    replace_regular_with_circle(page, center, radius)
        else:
            # Custom/irregular: compound path met magenta 0.5pt
            if stroke_paths:
                # herteken als één compound path
                redraw_as_compound(page, stroke_paths, overlay=True)
                # optioneel: oude vectoren verwijderen
                for p in stroke_paths:
                    page.add_redact_annot(p["rect"])
                page.apply_redactions(images=0, drawings=2, text=0)

        # 2) (optioneel) alle bekende naam-tokens naar /stans
        rename_tokens_in_streams(doc, page)

    doc.save(out_path, deflate=True)  # standaard save; deflate comprimeert
