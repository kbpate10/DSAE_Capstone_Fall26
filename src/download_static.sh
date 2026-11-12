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
# EIA-860 (generators, plants, cooling systems) and EIA-923 (generation, Schedule 8D cooling water), 2025 data year
mkdir -p data/raw/eia860 data/raw/eia923
if [ ! -f data/raw/eia860/2___Plant_Y2025.xlsx ]; then
  curl -sSL -A "$UA" -o data/raw/eia860/eia8602025.zip "https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip"
  unzip -q -o data/raw/eia860/eia8602025.zip -d data/raw/eia860
fi
if [ ! -f data/raw/eia923/EIA923_Schedule_8_Annual_Envir_Infor_2025_Final.xlsx ]; then
  curl -sSL -A "$UA" -o data/raw/eia923/f923_2025.zip "https://www.eia.gov/electricity/data/eia923/xls/f923_2025.zip"
  unzip -q -o data/raw/eia923/f923_2025.zip -d data/raw/eia923
fi
# EPA CAMPD measured hourly plant emissions (public bulk files, no key): Arizona plants, plus New Mexico because EIA-923 assigns Four Corners to AZPS
mkdir -p data/raw/campd_az
for st in az nm; do
  for y in 2021 2022 2023 2024 2025; do
    f="data/raw/campd_az/emissions-hourly-$y-$st.csv"
    [ -f "$f" ] || curl -sSf -o "$f" "https://api.epa.gov/easey/bulk-files/emissions/hourly/state/emissions-hourly-$y-$st.csv"
  done
done

echo "static downloads complete"
