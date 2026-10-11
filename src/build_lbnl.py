"""Convert the LBNL Queued Up workbook ('03. Complete Queue Data' sheet) to parquet.

Note: this dataset contains generation/storage requests only (project_type: Generation, Surplus,
Upgrade, Replacement). It has NO load or data-center interconnection requests.
Output: data/processed/lbnl_queue_all.parquet
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    q = pd.read_excel(ROOT / "data/raw/lbnl/lbnl_ix_queue_data_file_thru2025.xlsx",
                      sheet_name="03. Complete Queue Data", header=1)
    for c in q.columns:  # mixed-type object columns cannot be written to parquet as-is
        if q[c].dtype == object:
            q[c] = q[c].astype(str).where(q[c].notna())
    q.to_parquet(ROOT / "data/processed/lbnl_queue_all.parquet", index=False)
    print(q.shape, "| AZ rows:", int((q.state == "AZ").sum()), "| project types:", q.project_type.value_counts().to_dict())


if __name__ == "__main__":
    main()
