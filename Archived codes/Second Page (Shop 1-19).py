import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ================== Settings ==================
file_path = BASE_DIR / "Results.xlsx"
output_dir = BASE_DIR / "MeterReports"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Electricity parameters
daily_charge = 1.8796       # Daily supply charge
consumption_rate = 0.381783 # Consumption rate (per kWh)
gst_rate = 0.10             # 10% GST

# ================== Load data ==================
df = pd.read_excel(file_path)
df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime")

# ================== Process each meter ==================
for meter in df["Meter"].unique():
    df_meter = df[df["Meter"] == meter].copy()

    # Calculate interval consumption
    df_meter["kWh_IMP_interval"] = df_meter["kWh_IMP"].diff().clip(lower=0)
    df_meter["kWh_EXP_interval"] = df_meter["kWh_EXP"].diff().clip(lower=0)

    # Daily aggregation by period
    df_daily = df_meter.resample("D", on="DateTime").sum()

    # Cost calculation
    df_daily["Charge_exGST"] = daily_charge + (df_daily["kWh_IMP_interval"] * consumption_rate)
    df_daily["Charge_incGST"] = df_daily["Charge_exGST"] * (1 + gst_rate)

    # Averages
    avg_import = df_daily["kWh_IMP_interval"].mean()
    avg_charge = df_daily["Charge_incGST"].mean()

    # ================== Plot ==================
    # 297mm x 297mm -> 11.7in x 11.7in
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.7, 11.7))

    # Chart 1: Daily Consumption
    ax1.plot(df_daily.index, df_daily["kWh_IMP_interval"], marker="o", color="green", label="Import (kWh)")
    ax1.plot(df_daily.index, df_daily["kWh_EXP_interval"], marker="x", color="limegreen", label="Export (kWh)")

    ax1.axhline(avg_import, color="darkgreen", linestyle="--", label=f"Avg: {avg_import:.2f} kWh")
    ax1.set_title(f"{meter} - Daily Electricity Consumption (kWh)")
    ax1.set_ylabel("Consumption (kWh)")
    ax1.legend()
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax1.set_xlabel("")

    # Chart 2: Daily Charges
    ax2.bar(df_daily.index, df_daily["Charge_incGST"], color="seagreen")
    ax2.axhline(avg_charge, color="darkgreen", linestyle="--", label=f"Avg: ${avg_charge:.2f}")
    ax2.set_title(f"{meter} - Daily Electricity Charges ($, inc. GST)")
    ax2.set_ylabel("Charge ($)")
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.6)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.set_xlabel("")

    # Overall title
    date_min = df_daily.index.min().strftime("%m-%d")
    date_max = df_daily.index.max().strftime("%m-%d")
    fig.suptitle(f"{meter} Electricity Usage ({date_min} To {date_max})",
                 fontsize=14, y=0.98)

    plt.tight_layout(rect=[0.03, 0.03, 0.97, 0.95])

    # ================== Save PDF ==================
    output_file = os.path.join(output_dir, f"{meter}_Report.pdf")
    plt.savefig(output_file)
    plt.close(fig)

    print(f"Done: {output_file}")




