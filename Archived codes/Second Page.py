import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ================== Load Excel ==================
df = pd.read_excel(BASE_DIR / "Results.xlsx")

# Filter to SHOP1 only
df = df[df["Meter"] == "SHOP1"].copy()

# Parse datetime column
df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime")

# ================== Calculate interval consumption ==================
df["kWh_IMP_interval"] = df["kWh_IMP"].diff().clip(lower=0)
df["kWh_EXP_interval"] = df["kWh_EXP"].diff().clip(lower=0)

# ================== Daily aggregation ==================
df_daily = df.resample("D", on="DateTime").sum()

# ================== Cost calculation ==================
daily_charge = 1.8796       # Daily supply charge
consumption_rate = 0.381783 # Consumption rate (per kWh)
gst_rate = 0.10             # 10% GST

df_daily["Charge_exGST"] = daily_charge + (df_daily["kWh_IMP_interval"] * consumption_rate)
df_daily["Charge_incGST"] = df_daily["Charge_exGST"] * (1 + gst_rate)

# ================== Averages ==================
avg_import = df_daily["kWh_IMP_interval"].mean()
avg_charge = df_daily["Charge_incGST"].mean()

# ================== Figure size (287.18mm canvas) ==================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.3, 11.3))  # 287.18mm ~ 11.3in

# Chart 1: Daily Consumption
ax1.plot(df_daily.index, df_daily["kWh_IMP_interval"], marker="o", label="Import (kWh)")
ax1.plot(df_daily.index, df_daily["kWh_EXP_interval"], marker="x", label="Export (kWh)")

# Average line + label
ax1.axhline(avg_import, color="red", linestyle="--",
            label=f"Avg: {avg_import:.2f} kWh")

ax1.set_title("Daily Electricity Consumption (kWh)")
ax1.set_ylabel("Consumption (kWh)")
ax1.legend()
ax1.grid(True, linestyle="--", alpha=0.6)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax1.set_xlabel("")  # Remove x-axis label

# Chart 2: Daily Charges
ax2.bar(df_daily.index, df_daily["Charge_incGST"], color="orange")

# Average line + label
ax2.axhline(avg_charge, color="blue", linestyle="--",
            label=f"Avg: ${avg_charge:.2f}")

ax2.set_title("Daily Electricity Charges ($, inc. GST)")
ax2.set_ylabel("Charge ($)")
ax2.legend()
ax2.grid(True, linestyle="--", alpha=0.6)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax2.set_xlabel("")  # Remove x-axis label

# Overall title
date_min = df_daily.index.min().strftime("%m-%d")
date_max = df_daily.index.max().strftime("%m-%d")
fig.suptitle(f"Electricity Usage ({date_min} To {date_max})",
             fontsize=14, y=0.98)

# Auto-adjust layout with padding
plt.tight_layout(rect=[0.03, 0.03, 0.97, 0.95])

# ================== Export PDF ==================
plt.savefig(BASE_DIR / "Shop1_Report.pdf")

























