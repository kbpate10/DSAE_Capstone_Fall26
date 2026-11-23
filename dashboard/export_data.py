from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parent.parent
P, O = root / "data/processed", root / "dashboard/data"
O.mkdir(exist_ok=True)
pd.read_parquet(P/"carbon_intensity.parquet")[["respondent","ts","ci_kg_per_mwh","data_flag"]].to_parquet(O/"carbon_intensity.parquet", index=False)
pd.read_parquet(P/"consumption_ci.parquet")[["respondent","ts","ci_cons","valid","imports_mwh","supply_mwh"]].to_parquet(O/"consumption_ci.parquet", index=False)
pd.read_parquet(P/"eia861_panel.parquet")[["state","year","util_num","util_name","com_mwh","ind_mwh"]].to_parquet(O/"eia861_panel.parquet", index=False)
print("done")