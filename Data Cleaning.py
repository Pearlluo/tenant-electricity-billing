import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).parent

# === 1. Load data ===
df = pd.read_excel(BASE_DIR / "Results.xlsx")
df["DateTime"] = pd.to_datetime(df["DateTime"])

# === 2. Cleaning function ===
def clean_meter_data(sub_df, meter):
    start_time = pd.Timestamp("2025-07-17 00:00:00")
    end_time   = pd.Timestamp("2025-08-17 00:00:00")

    # Keep only records within the target period
    sub_df = sub_df[(sub_df["DateTime"] >= start_time) & (sub_df["DateTime"] <= end_time)].copy()

    # Insert start point if missing
    if start_time not in sub_df["DateTime"].values:
        first_row = pd.DataFrame({
            "DateTime": [start_time],
            "kWh_IMP": [0],
            "kWh_EXP": [0],
            "Meter": [meter]
        })
        sub_df = pd.concat([first_row, sub_df]).sort_values("DateTime").reset_index(drop=True)

    # Insert end point to ensure full time coverage
    if end_time not in sub_df["DateTime"].values:
        last_row = pd.DataFrame({
            "DateTime": [end_time],
            "kWh_IMP": [np.nan],
            "kWh_EXP": [np.nan],
            "Meter": [meter]
        })
        sub_df = pd.concat([sub_df, last_row]).sort_values("DateTime").reset_index(drop=True)

    # Deduplicate: keep last value for the same timestamp
    sub_df = sub_df.groupby("DateTime", as_index=False).agg({
        "kWh_IMP": "last",
        "kWh_EXP": "last",
        "Meter": "first"
    })

    # Generate complete 5-minute time series for the fixed period
    full_range = pd.date_range(start_time, end_time, freq="5min")
    sub_df = sub_df.set_index("DateTime").reindex(full_range).rename_axis("DateTime").reset_index()
    sub_df["Meter"] = meter

    # Outlier handling
    for col in ["kWh_IMP", "kWh_EXP"]:
        sub_df.loc[sub_df[col] < 0, col] = np.nan
        sub_df[col] = sub_df[col].mask(sub_df[col].diff().abs() > sub_df[col].median() * 5)

    # Linear interpolation
    sub_df[["kWh_IMP", "kWh_EXP"]] = sub_df[["kWh_IMP", "kWh_EXP"]].interpolate(method="linear")

    # Resample to 30-minute intervals
    sub_df = sub_df.set_index("DateTime").resample("30min").first().reset_index()

    # Round to 1 decimal place
    sub_df["kWh_IMP"] = sub_df["kWh_IMP"].round(1)
    sub_df["kWh_EXP"] = sub_df["kWh_EXP"].round(1)

    return sub_df


# === 3. Process each meter ===
result_list = []
for meter, group in df.groupby("Meter"):
    cleaned = clean_meter_data(group, meter)
    result_list.append(cleaned)

# Merge all meters
df_30min = pd.concat(result_list).reset_index(drop=True)

# === 4. Export result ===
df_30min.to_excel("cleaned_30min.xlsx", index=False)

print("Done. Output: cleaned_30min.xlsx (period 7/17 00:00 ~ 8/17 00:00, 30-min intervals, 1 decimal place)")
