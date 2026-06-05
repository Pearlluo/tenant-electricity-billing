import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ================== 参数设置 ==================
file_path = BASE_DIR / "cleaned_30min.xlsx"
tariff_file = BASE_DIR / "C&E Report (Tariff after July).xlsx"
output_dir = BASE_DIR / "MeterReports"

# 确保输出文件夹存在
os.makedirs(output_dir, exist_ok=True)

# ================== 读取数据 ==================
df = pd.read_excel(file_path)
df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime")

# 读取 Tariff 映射
tariff_df = pd.read_excel(tariff_file)
tariff_df.columns = tariff_df.columns.str.strip()
tariff_df["Shop No."] = tariff_df["Shop No."].astype(str)
tariff_map = tariff_df.set_index("Shop No.").to_dict(orient="index")

# 🔧 修复 Common / MDB 的别名
if "Common Service" in tariff_map:
    tariff_map["Common"] = tariff_map["Common Service"]
    tariff_map["MDB"] = tariff_map["Common Service"]

# ================== 读取上个月均值参考表 ==================
last_month_df = pd.read_excel(tariff_file, sheet_name="Last Month Billing reference")
last_month_df["Shop No."] = last_month_df["Shop No."].astype(str)
last_month_map = last_month_df.set_index("Shop No.")[["Average Consumption/ Per day", "Average Cost / Per day"]].to_dict(orient="index")

# ================== 固定日期范围 ==================
start_date = pd.Timestamp("2025-07-17 00:00:00")
end_date = pd.Timestamp("2025-08-17 00:00:00")
date_range = pd.date_range(start_date, end_date - pd.Timedelta(days=1), freq="D")

# ================== 遍历所有 Meter ==================
for meter in df["Meter"].unique():
    df_meter = df[df["Meter"] == meter].copy()

    # 🔑 Shop No 提取
    shop_no = "".join([ch for ch in meter if ch.isdigit()])
    if not shop_no:
        if "MDB" in meter.upper():
            shop_no = "MDB"
        elif "COMMON" in meter.upper():
            shop_no = "Common"
        else:
            continue

    shop_info = tariff_map.get(shop_no)
    if not shop_info:
        print(f"⚠️ 未找到 {shop_no} 的 tariff 信息，跳过 {meter}")
        continue

    # ================== 计算间隔用电量 ==================
    df_meter["kWh_IMP_interval"] = df_meter["kWh_IMP"].diff().clip(lower=0).fillna(0)
    df_meter["kWh_EXP_interval"] = df_meter["kWh_EXP"].diff().clip(lower=0).fillna(0)

    # ================== 按天汇总 + 补齐固定日期 ==================
    df_daily = df_meter.resample("D", on="DateTime").sum()
    df_daily = df_daily.reindex(date_range, fill_value=0)
    df_daily.index.name = "DateTime"

    # ================== 费用计算 ==================
    daily_charge = shop_info.get("Daily Supply Charge $ (Exc. GST)", 0)
    gst_rate = 0.10

    anytime_rate = shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")
    after1650_rate = shop_info.get("After 1650 units (Exc. GST)")
    peak_rate = shop_info.get("Peak Time Rate $ (Exc. GST)")
    offpeak_rate = shop_info.get("Off Peak Rate $ (Exc. GST)")

    if pd.notna(anytime_rate):
        # Anytime / 阶梯电价 (每天 1650 阈值)
        df_daily["Anytime_kWh"] = df_daily["kWh_IMP_interval"].clip(upper=1650)
        df_daily["After1650_kWh"] = (df_daily["kWh_IMP_interval"] - 1650).clip(lower=0)
        df_daily["Charge_exGST"] = (daily_charge +
                                    df_daily["Anytime_kWh"] * anytime_rate +
                                    df_daily["After1650_kWh"] * after1650_rate)
        tariff_type = "Anytime/After1650"

    elif pd.notna(peak_rate) and pd.notna(offpeak_rate):
        # 精确 TOU 按时间分类
        df_meter["Period_kWh"] = df_meter["kWh_IMP_interval"]

        def classify_period(ts):
            weekday = ts.weekday()
            hour = ts.hour
            if weekday < 5 and 8 <= hour < 22:
                return "peak"
            return "offpeak"

        df_meter["period"] = df_meter["DateTime"].apply(classify_period)

        # 按天汇总
        df_peak = df_meter[df_meter["period"] == "peak"].resample("D", on="DateTime").sum()
        df_offpeak = df_meter[df_meter["period"] == "offpeak"].resample("D", on="DateTime").sum()

        df_daily["Peak_kWh"] = df_peak["kWh_IMP_interval"].reindex(df_daily.index, fill_value=0)
        df_daily["Offpeak_KWh"] = df_offpeak["kWh_IMP_interval"].reindex(df_daily.index, fill_value=0)

        df_daily["Charge_exGST"] = (daily_charge +
                                    df_daily["Peak_kWh"] * peak_rate +
                                    df_daily["Offpeak_KWh"] * offpeak_rate)
        tariff_type = "TOU (Peak/Offpeak)"

    else:
        # fallback
        df_daily["Charge_exGST"] = daily_charge + df_daily["kWh_IMP_interval"] * 0.3
        tariff_type = "Fallback"

    df_daily["Charge_incGST"] = df_daily["Charge_exGST"] * (1 + gst_rate)

    # ================== 本月均值 ==================
    avg_import = df_daily["kWh_IMP_interval"].mean()
    avg_charge = df_daily["Charge_incGST"].mean()

    # ================== 上月均值 ==================
    last_avg_import = None
    last_avg_charge = None
    if shop_no in last_month_map:
        last_avg_import = last_month_map[shop_no].get("Average Consumption/ Per day")
        last_avg_charge = last_month_map[shop_no].get("Average Cost / Per day")

    # ================== 绘图 ==================
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.7, 11.7))

    # ---------- 图1：Daily Consumption ----------
    ax1.plot(df_daily.index, df_daily["kWh_IMP_interval"], marker="o", color="green", label="Import (kWh)")
    ax1.plot(df_daily.index, df_daily["kWh_EXP_interval"], marker="x", color="limegreen", label="Export (kWh)")
    ax1.axhline(avg_import, color="darkgreen", linestyle="--", label=f"This Month Avg: {avg_import:.2f} kWh")
    if last_avg_import is not None:
        ax1.axhline(last_avg_import, color="red", linestyle=":", label=f"Last Month Avg: {last_avg_import:.2f} kWh")

    # 📌 Y 轴范围动态调整
    candidates = [df_daily["kWh_IMP_interval"].min(), df_daily["kWh_IMP_interval"].max(), avg_import]
    if last_avg_import is not None:
        candidates.append(last_avg_import)

    ymin = min(candidates) * 0.9
    ymax = max(candidates) * 1.1
    if abs(ymax - ymin) < 5:
        ymax = ymin + 5
    ax1.set_ylim(ymin, ymax)

    ax1.set_title(f"{meter} - Daily Electricity Consumption (kWh)")
    ax1.set_ylabel("Consumption (kWh)")
    ax1.legend()
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax1.set_xlabel("")

    # ---------- 图2：Daily Charges ----------
    ax2.bar(df_daily.index, df_daily["Charge_incGST"], color="seagreen")
    ax2.axhline(avg_charge, color="darkgreen", linestyle="--", label=f"This Month Avg: ${avg_charge:.2f}")
    if last_avg_charge is not None:
        ax2.axhline(last_avg_charge, color="red", linestyle=":", label=f"Last Month Avg: ${last_avg_charge:.2f}")
    ax2.set_ylim(0, df_daily["Charge_incGST"].max() * 1.2)

    ax2.set_title(f"{meter} - Daily Electricity Charges ($, inc. GST)")
    ax2.set_ylabel("Charge ($)")
    ax2.legend()
    ax2.grid(True, linestyle="--", alpha=0.6)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.set_xlabel("")

    # ---------- 整体标题 ----------
    fig.suptitle(f"{meter} Electricity Usage (07-17 To 08-17)\nTariff: {tariff_type}",
                 fontsize=14, y=0.98)

    plt.tight_layout(rect=[0.03, 0.03, 0.97, 0.95])

    # ================== 保存 PDF ==================
    output_file = os.path.join(output_dir, f"{meter}_Report.pdf")
    plt.savefig(output_file)
    plt.close(fig)

    print(f"✅ 已生成: {output_file} (Tariff = {tariff_type})")






