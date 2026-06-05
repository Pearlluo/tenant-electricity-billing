import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).parent

# === 1. 读取数据 ===
df = pd.read_excel(BASE_DIR / "Results.xlsx")
df["DateTime"] = pd.to_datetime(df["DateTime"])

# === 2. 清洗函数 ===
def clean_meter_data(sub_df, meter):
    start_time = pd.Timestamp("2025-07-17 00:00:00")
    end_time   = pd.Timestamp("2025-08-17 00:00:00")

    # 只保留区间范围内的数据
    sub_df = sub_df[(sub_df["DateTime"] >= start_time) & (sub_df["DateTime"] <= end_time)].copy()

    # 插入起始点
    if start_time not in sub_df["DateTime"].values:
        first_row = pd.DataFrame({
            "DateTime": [start_time],
            "kWh_IMP": [0],
            "kWh_EXP": [0],
            "Meter": [meter]
        })
        sub_df = pd.concat([first_row, sub_df]).sort_values("DateTime").reset_index(drop=True)

    # 插入结束点（保证时间完整）
    if end_time not in sub_df["DateTime"].values:
        last_row = pd.DataFrame({
            "DateTime": [end_time],
            "kWh_IMP": [np.nan],
            "kWh_EXP": [np.nan],
            "Meter": [meter]
        })
        sub_df = pd.concat([sub_df, last_row]).sort_values("DateTime").reset_index(drop=True)

    # 去重：同一时间取最后一个值
    sub_df = sub_df.groupby("DateTime", as_index=False).agg({
        "kWh_IMP": "last",
        "kWh_EXP": "last",
        "Meter": "first"
    })

    # 生成完整 5 分钟时间序列（固定区间）
    full_range = pd.date_range(start_time, end_time, freq="5min")
    sub_df = sub_df.set_index("DateTime").reindex(full_range).rename_axis("DateTime").reset_index()
    sub_df["Meter"] = meter

    # 异常值处理
    for col in ["kWh_IMP", "kWh_EXP"]:
        sub_df.loc[sub_df[col] < 0, col] = np.nan
        sub_df[col] = sub_df[col].mask(sub_df[col].diff().abs() > sub_df[col].median() * 5)

    # 线性插值
    sub_df[["kWh_IMP", "kWh_EXP"]] = sub_df[["kWh_IMP", "kWh_EXP"]].interpolate(method="linear")

    # 采样为 30 分钟
    sub_df = sub_df.set_index("DateTime").resample("30min").first().reset_index()

    # 保留 1 位小数
    sub_df["kWh_IMP"] = sub_df["kWh_IMP"].round(1)
    sub_df["kWh_EXP"] = sub_df["kWh_EXP"].round(1)

    return sub_df


# === 3. 按 Meter 分组处理 ===
result_list = []
for meter, group in df.groupby("Meter"):
    cleaned = clean_meter_data(group, meter)
    result_list.append(cleaned)

# 合并
df_30min = pd.concat(result_list).reset_index(drop=True)

# === 4. 导出结果 ===
df_30min.to_excel("cleaned_30min.xlsx", index=False)

print("✅ 清理完成，已生成 cleaned_30min.xlsx （区间 7/17 00:00 ~ 8/17 00:00，30分钟，保留1位小数）")


