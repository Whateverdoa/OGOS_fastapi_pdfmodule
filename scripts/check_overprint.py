#!/usr/bin/env python3
import sys
from pypdf import PdfReader

def check_overprint(pdf_path: str) -> int:
    reader = PdfReader(pdf_path)
    found = False
    for i, page in enumerate(reader.pages, start=1):
        res = page.get("/Resources")
        if hasattr(res, "get_object"):
            res = res.get_object()
        if res and "/ExtGState" in res:
            gs = res["/ExtGState"]
            if hasattr(gs, "get_object"):
                gs = gs.get_object()
            for name, g in getattr(gs, "items", lambda: [])():
                if hasattr(g, "get_object"):
                    g = g.get_object()
                s = str(g)
                if "/OP true" in s or "/op true" in s:
                    print(f"Page {i}: overprint enabled in ExtGState {name}")
                    found = True
        # Inspect XObjects
        if res and "/XObject" in res:
            xobjs = res["/XObject"]
            if hasattr(xobjs, "get_object"):
                xobjs = xobjs.get_object()
            for xname, xo in getattr(xobjs, "items", lambda: [])():
                if hasattr(xo, "get_object"):
                    xo = xo.get_object()
                subtype = str(xo.get("/Subtype")) if hasattr(xo, "get") else ""
                if subtype != "/Form":
                    continue
                xr = xo.get("/Resources") if hasattr(xo, "get") else None
                if hasattr(xr, "get_object"):
                    xr = xr.get_object()
                if xr and "/ExtGState" in xr:
                    gs = xr["/ExtGState"]
                    if hasattr(gs, "get_object"):
                        gs = gs.get_object()
                    for name, g in getattr(gs, "items", lambda: [])():
                        if hasattr(g, "get_object"):
                            g = g.get_object()
                        s = str(g)
                        if "/OP true" in s or "/op true" in s:
                            print(f"Page {i} XObject {xname}: overprint enabled in ExtGState {name}")
                            found = True
    if not found:
        print("No overprint-enabled ExtGState found.")
        return 1
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: scripts/check_overprint.py <pdf_path>")
        sys.exit(2)
    sys.exit(check_overprint(sys.argv[1]))

