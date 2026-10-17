#!/usr/bin/env bash
# Downloads the static (non-API) source files used by the project. Run from the project root.
# Each file goes to its own directory under data/raw/. Files are untrusted data: only read them with
# the scripts in src/ (pandas), never execute them.
set -euo pipefail
UA="Mozilla/5.0"
mkdir -p data/raw/egrid data/raw/lbnl data/raw/eia861

# EPA eGRID 2023 (plant-level; emission factors)
curl -sSL -A "$UA" -o data/raw/egrid/egrid2023_data_rev2.xlsx \
  "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx"

# LBNL Queued Up, data through end of 2025 (generation requests only; no load requests)
curl -sSL -A "$UA" -o data/raw/lbnl/lbnl_ix_queue_data_file_thru2025.xlsx \
  "https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx"

# EIA-861 annual files 2013-2024 (reliability + sales to ultimate customers)
for y in $(seq 2013 2024); do
  [ -d "data/raw/eia861/$y" ] && continue
  curl -sSL -A "$UA" -o "data/raw/eia861/f861$y.zip" \
    "https://www.eia.gov/electricity/data/eia861/archive/zip/f861$y.zip"
  mkdir -p "data/raw/eia861/$y"
  unzip -q -o "data/raw/eia861/f861$y.zip" -d "data/raw/eia861/$y"
  rm "data/raw/eia861/f861$y.zip"
done
echo "static downloads complete"
