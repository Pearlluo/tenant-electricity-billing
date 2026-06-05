import os
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ===== 输入文件路径 =====
results_file = BASE_DIR / "cleaned_30min.xlsx"
mapping_file = BASE_DIR / "C&E Report (Tariff after July).xlsx"
input_pdf = BASE_DIR / "CoverPages" / "Common_Cover.pdf"
output_pdf = BASE_DIR / "CoverPages" / "Common_Cover_with_Loss.pdf"

# ===== 参数 =====
rate_loss = 0.347075

# ===== 数据导入 =====
df = pd.read_excel(results_file)

# 时间范围
start_time = pd.Timestamp("2025-07-17 00:00:00")
end_time = pd.Timestamp("2025-08-17 00:00:00")

# ===== 按 Meter 计算总耗电 =====
def get_consumption(df, meter):
    df_meter = df[df["Meter"] == meter].copy()
    if df_meter.empty:
        return 0
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter.sort_values("DateTime")

    try:
        prev_read = df_meter.loc[df_meter["DateTime"] == start_time, "kWh_IMP"].iloc[0]
        curr_read = df_meter.loc[df_meter["DateTime"] == end_time, "kWh_IMP"].iloc[0]
    except IndexError:
        return 0  # 防止没有数据时报错

    return curr_read - prev_read

mdb_consumption = get_consumption(df, "MDB")
common_consumption = get_consumption(df, "Common Service")

shops_total = 0
for meter in df["Meter"].unique():
    if meter not in ["MDB", "Common Service"]:
        shops_total += get_consumption(df, meter)

# ===== 计算 All Meter Loss =====
meter_loss_consumption = mdb_consumption - (shops_total + common_consumption)
meter_loss_total = meter_loss_consumption * rate_loss

print("MDB:", mdb_consumption)
print("Shops Total:", shops_total)
print("Common Service:", common_consumption)
print("Meter Loss Consumption:", meter_loss_consumption)
print("Meter Loss Total $:", meter_loss_total)

# ===== 合并 PDF (不再生成 overlay)=====
reader = PdfReader(open(input_pdf, "rb"))
writer = PdfWriter()

# 直接复制原 PDF 页
for page in reader.pages:
    writer.add_page(page)

with open(output_pdf, "wb") as f_out:
    writer.write(f_out)

print(f"✅ 已生成新账单: {output_pdf}")



