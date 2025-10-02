# PDF Dieline Color Layers & XObject Reference

This document captures how dieline spot colors, optional content layers, and Form XObjects are wired together in PDFs handled by the OGOS FastAPI module. When you run into “mixed” spot-color names (e.g., some objects still showing **KissCut** after conversion to **stans**) or missing dielines, walk through the components below and verify each layer has been normalized.

---

## 1. Resource Stack Overview

Every PDF page (and any nested Form XObject) exposes a `/Resources` dictionary. Downstream renderers resolve stroke/fill colors, content streams, and optional layers through these entries.

```
Resources
├─ /ColorSpace        → spot-color definitions, DeviceN/Separation arrays
├─ /ExtGState         → stroke/fill overrides (overprint, line width, etc.)
├─ /Properties        → optional-content groups (layers/visibility)
└─ /XObject           → nested Form XObjects with their own /Resources
```

When debugging color issues, walk this tree depth‑first:

1. Start with the page’s `/Resources`.
2. For each `/XObject`, look at its `/Resources` and repeat.
3. At each level, inspect `/ColorSpace` and `/Properties` entries for stale spot-color names.

Our `SpotColorRenamer` now performs this recursion automatically, but if you see an inconsistent file, this is the hierarchy to inspect.

---

## 2. Spot Colors (`/ColorSpace`)

### 2.1 Separation & DeviceN Definitions

Dieline spot colors typically use a **Separation** or **DeviceN** entry:

```pdf
/CS2 [/Separation /Kisscut /DeviceCMYK 15 0 R]
```

* `/Separation` – single-channel spot color.
* `/DeviceN` – multi-channel spot; often used when legacy software duplicates definitions.
* The second element (`/Kisscut`) is the spot-name token we need to normalize.
* The last element is a tint transform (function or array) controlling how the spot simulates.

**What to check:**

- Confirm every dieline color space points to `/stans` (or the desired spot name).
- If a `DeviceN` or `Separation` still references `/Kisscut`, use the renamer to rewrite it. Manual fix: swap the name with `NameObject('/stans')` but reuse the same tint transform object so previews remain unchanged.

### 2.2 Common Failures

| Symptom                                | Cause                                                                    | Fix                                                                                                  |
|----------------------------------------|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Outer dieline is `stans`, inner is `KissCut` | Nested XObject kept its own `/ColorSpace` entry                          | Re-run renamer (current implementation walks XObjects); otherwise, manually update the XObject’s `/Resources` dictionary. |
| Illustrator shows duplicate spot swatches | Multiple `/ColorSpace` entries with different spot names mapping to the same tint transform | Delete the duplicates or rename them so all point to the same `/stans` token.                         |
| Press RIP ignores the dieline           | Spot color renamed but tint transform not embedded (null or missing function)          | Preserve the original tint transform object; never overwrite the function when swapping spot names.   |

---

## 3. Optional Content Groups (Layers)

### 3.1 Where Layers Live

Layer names are defined in two places:

1. **Page `/Resources` → `/Properties`** – references to `/OCG` objects used by that page.
2. **Document `/Root` → `/OCProperties`** – the global list of optional-content groups and their configuration (default visibility, order, etc.).

Example of a layer entry inside a page resource:

```pdf
/Properties <<
  /Prop1 8 0 R  % Name: Opmaak
  /Prop2 9 0 R  % Name: Kisscut
>>
```

Each referenced object (`9 0 R`) is an **Optical Content Group** dictionary:

```pdf
9 0 obj
<< /Type /OCG /Name (Kisscut) >>
```

Illustrator/Acrobat read these names when populating the layer panel. If the `/Name` stays “Kisscut”, the UI still labels it that way even if the color resources were renamed.

### 3.2 Normalization Strategy

- Rename every `/Name` field in any `/OCG` dictionary whose value matches our alias list (CutContour/KissCut/DieCut/Stans/Stanslijn).
- Walk both the page-level `/Properties` and the document’s `/OCProperties` tree; the latter can nest arrays and dictionaries (`/Order`, `/UIConfig`, etc.).
- Ensure we don’t rename unrelated layers (e.g., production overlay “Opmaak”); only apply the change when the lowercase value appears in the alias set.

### 3.3 Troubleshooting Layers

| Symptom                                       | Likely Cause                                                | Fix                                                                                       |
|-----------------------------------------------|-------------------------------------------------------------|------------------------------------------------------------------------------------------|
| Viewer still lists “Kisscut” layer            | Global `/OCProperties` or page `/Properties` contains old `/Name` | Re-run renamer or manually update the `/OCG` dictionary.                                   |
| Layer toggles hide dieline unexpectedly       | OCG association not updated after merging paths             | Ensure compound path creation keeps references to the correct `/OCG` entries.             |
| Layer missing entirely                        | `/Properties` mapping deleted or not transferred during merge | Copy the original `/Properties` into any generated Form XObject or new page resources.    |

---

## 4. Form XObjects (`/XObject`)

### 4.1 Why They Matter

When artwork is placed multiple times or generated via preflighting tools, dielines may live inside **Form XObjects**. These objects behave like mini pages with their own resource dictionaries and content streams:

```pdf
13 0 obj
<< /Type /XObject /Subtype /Form
   /Resources << /ColorSpace << /CS2 14 0 R >> ... >>
   /Contents 14 0 R
>>
```

If we renamer only at the page level, nested dieline definitions survive, which was the root cause of the “inner Kisscut” issue.

### 4.2 Recursion Checklist

When processing XObjects:

1. Resolve `xobj.get_object()` to obtain the dictionary.
2. Call the same renaming logic on the XObject’s `/Resources`.
3. Rename any OCGs referenced in the XObject resources.
4. Decode the XObject’s `/Contents` and replace residual tokens (`/KissCut`, `/Kisscut`, etc.) with the normalized name.

The updated `SpotColorRenamer` handles these steps automatically.

---

## 5. Content Streams

After resource dictionaries are clean, make sure the content stream reflects the new spot color name:

```
/CS2 CS
1 SCN
...
```

If the stream still contains `/Kisscut CS`, the renderer will attempt to look up `/Kisscut` in the resource tree, which can silently recreate the unwanted swatch.

**Quick scan:**

```bash
strings -a file.pdf | grep -i kiss
```

If any matches remain, check whether they are layer names or actual drawing commands. Our pipeline now rewrites both.

---

## 6. Workflow Summary

1. **Normalize Spot Resources**
   - Run `SpotColorRenamer` → walks pages, XObjects, `/ColorSpace`, `/Properties`, `/OCProperties`.
   - Verifies all Separation/DeviceN names match `job_config.spot_color_name`.

2. **Merge Dieline Paths**
   - Run `StansCompoundPathConverter` → combines multiple stans/kisscut segments into one compound path without altering the layer linkage.

3. **(Optional) Final Renames**
   - `SpotColorHandler.rename_spot_color` remains a placeholder; once implemented fully, it should reapply the same logic (resources + stream) so we have a single authoritative renamer.

4. **Verification**
   - Inspect outputs using `strings`, `pypdf`, or a viewer’s layer panel. Expect:
     - `/ColorSpace` definitions with `/stans` only.
     - `/Properties` (layers) labelled “stans”.
     - Content stream free of `/Kisscut` tokens.

---

## 7. Future Enhancements

- **Integrated spot-color handler**: Replace the PyMuPDF placeholder with a parser that reuses `SpotColorRenamer`/`StansCompoundPathConverter` to enforce naming and overprint settings in one pass.
- **Unit tests**: Build fixtures with nested XObjects and multiple layers to ensure regression coverage for the scenarios in this doc.
- **Layer preservation in generated dielines**: When creating new Form XObjects (e.g., for standard shapes), assign the same `/Properties` entries so the layer palette remains clean.

---

## 8. Useful Snippets

### Inspect Color Spaces Quickly (Python)
```python
from pypdf import PdfReader
reader = PdfReader(path)
page = reader.pages[0]
for cs_name, cs_def in page['/Resources']['/ColorSpace'].items():
    obj = cs_def.get_object() if hasattr(cs_def, 'get_object') else cs_def
    print(cs_name, obj)
```

### List Optional-Content Group Names (Python)
```python
props = page['/Resources'].get('/Properties', {})
for key, ref in props.items():
    ocg = ref.get_object() if hasattr(ref, 'get_object') else ref
    print(key, ocg.get('/Name'))
```

### Grep for Residual Tokens (CLI)
```bash
uv run python - <<'PY'
from pathlib import Path
path = Path('output.pdf')
print('Kiss present?', 'Kiss' in path.read_bytes().decode('latin-1', 'ignore'))
PY
```

---

Having this map of where spot colors and layers live will save you time when something slips through or a vendor PDF uses unexpected structure. Start at `/Resources`, walk through `/ColorSpace`, `/Properties`, and `/XObject`, and confirm the compound path builder didn’t strip the layer references. With the latest renamer, both the visible swatch and the layer name should always end up as the configured spot color (default `stans`).
