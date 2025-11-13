#!/usr/bin/env bash
set -euo pipefail

DIR="examplecode"
OUTDIR="batch_outputs"
API_BASE="http://localhost:8000"
FONTS=""
REMOVE_MARKS=0
ANALYZE_ONLY=0
INCLUDE_JOBSHEETS=0

usage() {
  cat <<USAGE
Batch process/analyze PDFs in a directory tree.

Usage:
  $0 [--dir DIR] [--out OUTDIR] [--base-url URL] [--fonts embed|outline] [--remove-marks] [--include-jobsheets]
  $0 --analyze-only [--dir DIR] [--base-url URL] [--include-jobsheets]

Defaults:
  --dir examplecode
  --out batch_outputs
  --base-url http://localhost:8000

Behavior:
  - Eligible = PDF files with a JSON config in the same folder (for process mode).
  - Jobsheets are skipped by default (detected by filename/JSON containing "jobsheet"). Use --include-jobsheets to override.
  - In analyze-only mode, runs analyze for all PDFs found.
USAGE
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="${2:-$DIR}"; shift 2;;
    --out) OUTDIR="${2:-$OUTDIR}"; shift 2;;
    --base-url) API_BASE="${2:-$API_BASE}"; shift 2;;
    --fonts) FONTS="${2:-}"; shift 2;;
    --remove-marks) REMOVE_MARKS=1; shift;;
    --analyze-only) ANALYZE_ONLY=1; shift;;
    --include-jobsheets) INCLUDE_JOBSHEETS=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

mkdir -p "$OUTDIR"

found=0
ok=0
err=0

# Build list of PDFs (portable, no bash 4+ mapfile requirement)
pdfs=()
while IFS= read -r -d '' f; do
  pdfs+=("$f")
done < <(find "$DIR" -type f \( -iname '*.pdf' -o -iname '*.PDF' \) -print0)

if [[ ${#pdfs[@]} -eq 0 ]]; then
  echo "No PDFs found under $DIR"
  exit 1
fi

echo "Discovered ${#pdfs[@]} PDF(s) under $DIR"

for pdf in "${pdfs[@]}"; do
  ((found++))
  dname=$(dirname "$pdf")
  bname=$(basename "$pdf")
  stem=${bname%.*}

  # Skip jobsheets unless explicitly included
  if [[ "$INCLUDE_JOBSHEETS" -eq 0 ]]; then
    if echo "$pdf" | grep -Eiql 'job\s*sheet|jobsheet'; then
      echo "[SKIP] Jobsheet detected by filename: $pdf"
      continue
    fi
  fi

  if [[ "$ANALYZE_ONLY" -eq 1 ]]; then
    echo "[ANALYZE] $pdf"
    bash scripts/send_pdf.sh analyze "$pdf" --base-url "$API_BASE" || { ((err++)); continue; }
    ((ok++))
    continue
  fi

  # Find a JSON in the same folder
  json_file=""
  if ls "$dname"/*.json >/dev/null 2>&1; then
    # prefer matching stem
    if [[ -f "$dname/$stem.json" ]]; then
      json_file="$dname/$stem.json"
    else
      json_file=$(ls "$dname"/*.json | head -n1)
    fi
  fi

  if [[ -z "$json_file" ]]; then
    echo "[SKIP] No JSON next to $pdf"
    continue
  fi

  if [[ "$INCLUDE_JOBSHEETS" -eq 0 ]]; then
    # Skip if JSON filename contains jobsheet OR if Description/Name equals "jobsheet"
    if echo "$json_file" | grep -Eiq 'job\s*sheet|jobsheet'; then
      echo "[SKIP] Jobsheet detected by JSON filename: $json_file"; continue
    fi
    if grep -Eiq '"(Name|Description)"\s*:\s*"\s*jobsheet\s*"' "$json_file"; then
      echo "[SKIP] Jobsheet detected by JSON fields: $json_file"; continue
    fi
  fi

  out="$OUTDIR/${stem}_processed.pdf"
  [[ -n "$FONTS" ]] && out="$OUTDIR/${stem}_processed_${FONTS}.pdf"
  if [[ "$REMOVE_MARKS" -eq 1 ]]; then out="${out%.pdf}_nomarks.pdf"; fi

  echo "[PROCESS] $pdf with $(basename "$json_file") -> $out"
  args=(process-json "$pdf" --json-file "$json_file" --out "$out" --base-url "$API_BASE")
  [[ -n "$FONTS" ]] && args+=(--fonts "$FONTS")
  [[ "$REMOVE_MARKS" -eq 1 ]] && args+=(--remove-marks)

  if bash scripts/send_pdf.sh "${args[@]}"; then
    ((ok++))
  else
    echo "[ERROR] Failed: $pdf" >&2
    ((err++))
  fi
done

echo "Done. PDFs: $found, OK: $ok, Errors: $err"
exit 0
