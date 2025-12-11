"""
PDF Endpoint Helper Functions

Shared utilities for PDF API endpoints: parsing, validation, detection.
"""

from typing import Dict, Optional

from ...models.schemas import ShapeType


def normalize_shape(value: str | None) -> str | None:
    """Normalize incoming shape strings (synonyms -> enum values)."""
    if value is None:
        return None
    s = str(value).strip().lower()
    mapping = {
        # expected
        "circle": "circle",
        "rectangle": "rectangle",
        "custom": "custom",
        # synonyms
        "irregular": "custom",
        "square": "rectangle",
        "rect": "rectangle",
        "oval": "circle",
        "ellipse": "circle",
    }
    return mapping.get(s, s)


def to_float(value: object, default: float = 0.0) -> float:
    """Parse floats from strings like '40,0' or '40.0'; returns default on failure."""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            v = value.strip().replace(",", ".")
            return float(v)
    except Exception:
        pass
    return default


def to_int_or_str(value: object) -> Optional[object]:
    """Coerce winding to int when possible; otherwise keep original string; None if empty."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if v == "":
            return None
        try:
            return int(v)
        except Exception:
            return v
    return value


def detect_reseller(context_text: str, config: Dict[str, object]) -> bool:
    """Heuristic: detect reseller customers by name in path/zip name or JSON fields."""
    keywords = ("print.com", "helloprint", "drukwerkdeal", "cimpress")
    txt = (context_text or "").lower()
    if any(k in txt for k in keywords):
        return True
    reseller_keys = (
        "Customer",
        "customer",
        "Reseller",
        "reseller",
        "Client",
        "client",
        "Brand",
        "brand",
        "Company",
        "company",
        "Supplier",
        "supplier",
        "SupplierId",
        "supplierid",
    )
    for key in reseller_keys:
        val = config.get(key)
        if isinstance(val, str) and any(k in val.lower() for k in keywords):
            return True

    
    # If Winding is present, assume reseller (as verified by user: "only files coming through are resellers")
    if "Winding" in config or "winding" in config:
        return True
        
    return False


def parse_job_config_from_json(
    config_dict: Dict, base_reference: str = ""
) -> Dict[str, object]:
    """
    Parse a JSON config dict into PDFJobConfig-compatible dict.

    Args:
        config_dict: Raw JSON config dictionary
        base_reference: Fallback reference if not in config

    Returns:
        Dictionary ready for PDFJobConfig construction
    """
    shape_value = config_dict.get("Shape", config_dict.get("shape", "")).lower()
    if shape_value in ("irregular", "custom_shape", "freeform"):
        shape_value = ShapeType.custom.value

    return {
        "reference": config_dict.get(
            "ReferenceAtCustomer", config_dict.get("reference", base_reference)
        ),
        "description": config_dict.get("Description", ""),
        "shape": shape_value,
        "width": to_float(config_dict.get("Width", config_dict.get("width", 0))),
        "height": to_float(config_dict.get("Height", config_dict.get("height", 0))),
        "radius": to_float(config_dict.get("Radius", config_dict.get("radius", 0))),
        "winding": to_int_or_str(
            config_dict.get("Winding", config_dict.get("winding"))
        ),
        "substrate": config_dict.get("Substrate", config_dict.get("substrate")),
        "adhesive": config_dict.get("Adhesive", config_dict.get("adhesive")),
        "colors": config_dict.get("Colors", config_dict.get("colors")),
        "fonts": config_dict.get("Fonts", config_dict.get("fonts", "embed")),
        "remove_marks": config_dict.get(
            "RemoveMarks",
            config_dict.get("remove_marks", config_dict.get("removeMarks", False)),
        ),
    }


def get_explicit_rotation(config_dict: Dict) -> Optional[int]:
    """Extract explicit rotation from config if present."""
    rotate_val_raw = config_dict.get(
        "Rotate", config_dict.get("rotate", config_dict.get("Orientation"))
    )
    if rotate_val_raw is None:
        return None
    try:
        return int(round(to_float(rotate_val_raw, 0.0)))
    except Exception:
        return None

