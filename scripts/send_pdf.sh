#!/usr/bin/env bash
set -euo pipefail

API_BASE="http://localhost:8000"

usage() {
  cat <<USAGE
Usage:
  $0 analyze <pdf_path> [--base-url URL]
  $0 process <pdf_path> (--job-json JSON | --job-file PATH) [--out FILE] [--base-url URL] [--fonts embed|outline] [--remove-marks]
  $0 process-json <pdf_path> --json-file PATH [--out FILE] [--base-url URL] [--fonts embed|outline] [--remove-marks]

Examples:
  $0 analyze examplecode/5355531_8352950/5355531_8352950.PDF
  $0 process example.pdf --job-json '{"reference":"demo","shape":"circle","width":50,"height":50}' --out out.pdf
  $0 process-json example.pdf --json-file examplecode/5355531_8352950/5355531_8352950.json
USAGE
}

require_file() {
  local f="$1"
  [[ -f "$f" ]] || { echo "File not found: $f" >&2; exit 1; }
}

parse_base_url() {
  local a=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base-url)
        shift
        API_BASE="${1:-$API_BASE}"; shift ;;
      *)
        a+=("$1"); shift ;;
    esac
  done
  echo "${a[@]}"
}

http_post_file() {
  # $1 endpoint, $2 body file path, outputs headers to stdout
  local endpoint="$1" body_file="$2"; shift 2
  local hdr
  hdr="$(mktemp)"
  # timeouts (env override: CURL_TIMEOUT seconds)
  local max_time="${CURL_TIMEOUT:-60}"
  curl -sS \
    --connect-timeout 5 \
    --max-time "$max_time" \
    --http1.1 \
    -H "Expect:" \
    -D "$hdr" -o "$body_file" "$@" "$endpoint" || true
  cat "$hdr"
  rm -f "$hdr"
}

extract_http_code() {
  awk '/^HTTP\//{code=$2} END{print code}'
}

extract_header() {
  # case-insensitive header extract
  awk -F': ' -v key="$(echo "$1" | tr '[:upper:]' '[:lower:]')" '{
    name=$1; sub(/\r$/, "", name); sub(/\r$/, "", $2);
    if (tolower(name) == key) print $2
  }'
}

content_disposition_filename() {
  # parse filename from Content-Disposition header
  sed -n 's/.*filename="\(.*\)".*/\1/p'
}

cmd=${1:-}
[[ -z "${cmd}" ]] && { usage; exit 1; }
shift || true

case "$cmd" in
  analyze)
    args=("$@")
    # parse optional --base-url
    eval "set -- $(printf ' %q' ${args[@]})"
    remaining=( $(parse_base_url "$@") )
    eval "set -- ${remaining[@]:-}"
    pdf=${1:-}
    [[ -n "$pdf" ]] || { usage; exit 1; }
    require_file "$pdf"

    body=$(mktemp)
    headers=$(http_post_file \
      "$API_BASE/api/pdf/analyze" "$body" \
      -X POST -H "accept: application/json" -F "pdf_file=@$pdf")

    code=$(echo "$headers" | extract_http_code)
    ctype=$(echo "$headers" | extract_header "Content-Type" | tail -n1)
    echo "HTTP $code"
    echo "Content-Type: ${ctype:-unknown}"
    echo
    cat "$body"
    echo
    rm -f "$body"
    exit 0
    ;;

  process)
    out=""
    job_json=""
    job_file=""
    pdf=""
    fonts=""
    # Parse args in any order
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --base-url)
          API_BASE="${2:-$API_BASE}"; shift 2 ;;
        --out)
          out="${2:-}"; shift 2 ;;
        --job-json)
          job_json="${2:-}"; shift 2 ;;
        --job-file)
          job_file="${2:-}"; shift 2 ;;
        --fonts)
          fonts="${2:-}"; shift 2 ;;
        --remove-marks)
          remove_marks=1; shift ;;
        --)
          shift; break ;;
        -*)
          echo "Unknown option: $1" >&2; usage; exit 1 ;;
        *)
          if [[ -z "$pdf" ]]; then pdf="$1"; else :; fi; shift ;;
      esac
    done
    [[ -n "$pdf" ]] || { usage; exit 1; }
    require_file "$pdf"
    if [[ -n "$job_file" ]]; then require_file "$job_file"; job_json="$(tr -d '\n' < "$job_file")"; fi
    [[ -n "$job_json" ]] || { echo "--job-json or --job-file is required" >&2; exit 1; }

    body=$(mktemp)
    q=""; sep="?"; if [[ -n "$fonts" ]]; then q="${q}${sep}fonts=$fonts"; sep="&"; fi; if [[ "${remove_marks:-}" == 1 ]]; then q="${q}${sep}remove_marks=true"; fi
    headers=$(http_post_file \
      "$API_BASE/api/pdf/process$q" "$body" \
      -X POST -H "accept: application/pdf" -F "pdf_file=@$pdf" -F "job_config=$job_json")

    code=$(echo "$headers" | extract_http_code)
    ctype=$(echo "$headers" | extract_header "Content-Type" | tail -n1)
    if echo "$ctype" | grep -qi '^application/pdf'; then
      # choose filename
      if [[ -z "$out" ]]; then
        disp=$(echo "$headers" | extract_header "Content-Disposition" | tail -n1)
        out=$(echo "$disp" | content_disposition_filename)
        [[ -n "$out" ]] || out="processed_$(date +%s).pdf"
      fi
      mv "$body" "$out"
      echo "HTTP $code"
      echo "Saved PDF to: $out"
      # Print useful custom headers if available
      for h in X-Processing-Reference X-Processing-Shape X-Winding-Value X-Rotation-Angle X-Needs-Rotation X-Winding-Error; do
        val=$(echo "$headers" | extract_header "$h" | tail -n1 || true)
        [[ -n "$val" ]] && echo "$h: $val"
      done
    else
      echo "HTTP $code"
      echo "Response (non-PDF):"
      echo
      cat "$body"; echo
      rm -f "$body"
      exit 1
    fi
    exit 0
    ;;

  process-json)
    out=""
    json_file=""
    pdf=""
    fonts=""
    # Parse args in any order
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --base-url)
          API_BASE="${2:-$API_BASE}"; shift 2 ;;
        --out)
          out="${2:-}"; shift 2 ;;
        --json-file)
          json_file="${2:-}"; shift 2 ;;
        --fonts)
          fonts="${2:-}"; shift 2 ;;
        --remove-marks)
          remove_marks=1; shift ;;
        --)
          shift; break ;;
        -*)
          echo "Unknown option: $1" >&2; usage; exit 1 ;;
        *)
          if [[ -z "$pdf" ]]; then pdf="$1"; else :; fi; shift ;;
      esac
    done
    [[ -n "$pdf" && -n "$json_file" ]] || { usage; exit 1; }
    require_file "$pdf"; require_file "$json_file"

    body=$(mktemp)
    q=""; sep="?"; if [[ -n "$fonts" ]]; then q="${q}${sep}fonts=$fonts"; sep="&"; fi; if [[ "${remove_marks:-}" == 1 ]]; then q="${q}${sep}remove_marks=true"; fi
    headers=$(http_post_file \
      "$API_BASE/api/pdf/process-with-json-file$q" "$body" \
      -X POST -H "accept: application/pdf" -F "pdf_file=@$pdf" -F "json_file=@$json_file;type=application/json")

    code=$(echo "$headers" | extract_http_code)
    ctype=$(echo "$headers" | extract_header "Content-Type" | tail -n1)
    if echo "$ctype" | grep -qi '^application/pdf'; then
      if [[ -z "$out" ]]; then
        disp=$(echo "$headers" | extract_header "Content-Disposition" | tail -n1)
        out=$(echo "$disp" | content_disposition_filename)
        [[ -n "$out" ]] || out="processed_$(date +%s).pdf"
      fi
      mv "$body" "$out"
      echo "HTTP $code"
      echo "Saved PDF to: $out"
      for h in X-Processing-Reference X-Processing-Shape X-Winding-Value X-Rotation-Angle X-Needs-Rotation X-Winding-Error; do
        val=$(echo "$headers" | extract_header "$h" | tail -n1 || true)
        [[ -n "$val" ]] && echo "$h: $val"
      done
    else
      echo "HTTP $code"
      echo "Response (non-PDF):"
      echo
      cat "$body"; echo
      rm -f "$body"
      exit 1
    fi
    exit 0
    ;;

  *)
    usage; exit 1 ;;
esac
