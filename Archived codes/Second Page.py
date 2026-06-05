import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ================== 读取 Excel ==================
df = pd.read_excel(BASE_DIR / "Results.xlsx")

# 只取 SHOP1
df = df[df["Meter"] == "SHOP1"].copy()

# 转换时间列
df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime")

# ================== 计算 Interval 用电量 ==================
df["kWh_IMP_interval"] = df["kWh_IMP"].diff().clip(lower=0)
df["kWh_EXP_interval"] = df["kWh_EXP"].diff().clip(lower=0)

# ================== 按天汇总 ==================
df_daily = df.resample("D", on="DateTime").sum()

# ================== 电费计算 ==================
daily_charge = 1.8796       # 每日固定费用
consumption_rate = 0.381783 # 每度电费用
gst_rate = 0.10             # 10% GST

df_daily["Charge_exGST"] = daily_charge + (df_daily["kWh_IMP_interval"] * consumption_rate)
df_daily["Charge_incGST"] = df_daily["Charge_exGST"] * (1 + gst_rate)

# ================== 平均值 ==================
avg_import = df_daily["kWh_IMP_interval"].mean()
avg_charge = df_daily["Charge_incGST"].mean()

# ================== 287.18 mm 画布 ==================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.3, 11.3))  # 287.18mm ≈ 11.3英寸

# ---------- 图1：Daily Consumption ----------
ax1.plot(df_daily.index, df_daily["kWh_IMP_interval"], marker="o", label="Import (kWh)")
ax1.plot(df_daily.index, df_daily["kWh_EXP_interval"], marker="x", label="Export (kWh)")

# 平均线 + 标签
ax1.axhline(avg_import, color="red", linestyle="--",
            label=f"Avg: {avg_import:.2f} kWh")

ax1.set_title("Daily Electricity Consumption (kWh)")
ax1.set_ylabel("Consumption (kWh)")
ax1.legend()
ax1.grid(True, linestyle="--", alpha=0.6)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax1.set_xlabel("")  # 去掉X轴标题

# ---------- 图2：Daily Charges ----------
ax2.bar(df_daily.index, df_daily["Charge_incGST"], color="orange")

# 平均线 + 标签
ax2.axhline(avg_charge, color="blue", linestyle="--",
            label=f"Avg: ${avg_charge:.2f}")

ax2.set_title("Daily Electricity Charges ($, inc. GST)")
ax2.set_ylabel("Charge ($)")
ax2.legend()
ax2.grid(True, linestyle="--", alpha=0.6)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax2.set_xlabel("")  # 去掉X轴标题

# ---------- 整体标题 ----------
date_min = df_daily.index.min().strftime("%m-%d")
date_max = df_daily.index.max().strftime("%m-%d")
fig.suptitle(f"Electricity Usage ({date_min} To {date_max})",
             fontsize=14, y=0.98)

# 自动调整排版，四周留白
plt.tight_layout(rect=[0.03, 0.03, 0.97, 0.95])

# ================== 导出 PDF ==================
plt.savefig(BASE_DIR / "Shop1_Report.pdf")

























