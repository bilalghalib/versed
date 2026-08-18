#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for versed-pdf.
#
# System packages provide the non-Python runtime pieces the library needs:
#   - tesseract-ocr(+ara): the `ocr` extra (pytesseract) shells out to this binary
#   - cairo/pango/gobject-introspection + Amiri/Noto fonts: the OpenITI PDF
#     typesetter (src/versed/openiti_renderer.py) renders through PangoCairo
# Python and Node deps are then refreshed from the checked-out source.
set -euo pipefail

cd "$(dirname "$0")/.."

APT_PACKAGES=(
  tesseract-ocr
  tesseract-ocr-ara
  python3-gi
  python3-gi-cairo
  python3-cairo
  gir1.2-pango-1.0
  gir1.2-glib-2.0
  fonts-hosny-amiri
  fonts-noto-core
)

missing=()
for pkg in "${APT_PACKAGES[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    missing+=("$pkg")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
fi

# Editable install with the PDF, OCR, and dev (pytest) extras. The semantic
# extra (torch/transformers) is intentionally omitted: the deterministic core
# is dependency-free and models are optional and downloaded on demand.
python3 -m pip install --break-system-packages -e '.[pdf,ocr,dev]'

# OpenITI mARkdown parsing bridges to @openiti/markdown-parser via `node -e`.
npm install

echo "versed-pdf environment ready."
