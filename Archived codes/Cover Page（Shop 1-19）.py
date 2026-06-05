import os
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent

# ===== 数据计算函数 =====
def calculate_usage(df, meter="SHOP1", daily_charge=1.87964, unit_rate=0.381783):
    df_meter = df[df["Meter"] == meter].copy()
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter.sort_values("DateTime")

    start_time = df_meter["DateTime"].iloc[0]
    end_time = df_meter["DateTime"].iloc[-1]
    days = (end_time - start_time).days + 1

    # 起始、结束读数
    prev_read = df_meter["kWh_IMP"].iloc[0]
    curr_read = df_meter["kWh_IMP"].iloc[-1]

    # 用电量（kWh）
    consumption = curr_read - prev_read

    # 每天平均用电
    avg_units = consumption / days if days > 0 else 0

    # ====== 费用计算规则 ======
    if consumption == 0:
        daily_cost = 0
        consumption_cost = 0
        total_excl = 0
        gst = 0
        total_incl = 0
        avg_cost_per_day = 0
    else:
        daily_cost = daily_charge * days
        consumption_cost = consumption * unit_rate
        total_excl = daily_cost + consumption_cost
        gst = total_excl * 0.1
        total_incl = total_excl + gst
        avg_cost_per_day = total_incl / days if days > 0 else 0

    return {
        "period": f"{start_time.date()} - {end_time.date()}",
        "days": days,
        "prev_read": prev_read,
        "curr_read": curr_read,
        "consumption": consumption,
        "avg_units": avg_units,
        "daily_charge": daily_charge,
        "unit_rate": unit_rate,
        "daily_cost": daily_cost,
        "consumption_cost": consumption_cost,
        "total_excl": total_excl,
        "gst": gst,
        "total_incl": total_incl,
        "avg_cost_per_day": avg_cost_per_day
    }

# ===== PDF 生成函数 =====
def generate_cover_page(pdf_path, usage_data, tenant_name="Tenant Name", premise="Premise Address", statement_date="2025/07/22", meter_name="Meter"):
    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Header 深绿色条
    c.setFillColor(colors.HexColor("#2E7D32"))  # 深绿色
    c.rect(40, height-60, width-80, 30, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.white)
    c.drawString(50, height-50, "H & N Perry")
    c.drawRightString(width-50, height-50, "Electricity Statement")

    # Statement Date
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(40, height-90, f"Statement Date: {statement_date}")

    # Tenant Info
    c.drawString(40, height-120, "To:")
    c.drawString(80, height-120, tenant_name)
    c.drawString(80, height-140, premise)

    # Prepared By
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, height-170, "Prepared by Element47 Pty Ltd on behalf of:")
    c.setFont("Helvetica", 9)
    c.drawString(40, height-185, "The Plaza Centre")
    c.drawString(40, height-200, "38 Mandurah Terrace")
    c.drawString(40, height-215, "Mandurah   6210")
    c.drawString(40, height-235, "Property Manager: H & N Perry")

    # ===== 右侧 Statement Summary =====
    box_x = width - 300
    box_y = height - 120
    c.setFont("Helvetica-Bold", 9)
    c.drawString(box_x, box_y, "Statement Summary")
    c.setFont("Helvetica", 9)

    c.drawString(box_x, box_y-20, "Report Period")
    c.drawRightString(width-50, box_y-20, usage_data["period"])
    c.drawString(box_x, box_y - 40, "Total (excl GST)")
    c.drawRightString(width - 50, box_y - 40, f"${usage_data['total_excl']:.2f}")

    c.drawString(box_x, box_y - 60, "GST")
    c.drawRightString(width - 50, box_y - 60, f"${usage_data['gst']:.2f}")

    # === Total incl GST ===
    row_height = 18
    row_y = box_y - 95

    # 左边绿色框
    c.setFillColor(colors.HexColor("#2E7D32"))  # 深绿色
    c.rect(box_x, row_y, 120, row_height, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(box_x + 60, row_y + 5, "Total (incl GST)")

    # 右边绿色框
    c.setFillColor(colors.limegreen)  # 浅绿色
    c.rect(width - 120, row_y, 70, row_height, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width - 85, row_y + 5, f"${usage_data['total_incl']:.2f}")

    # ===== Charges 表格 =====
    table_y = height-300
    headers = ["Unit", "Date", "Previous Reading (kWh)", "Current Reading (kWh)",
               "Consumption (kWh)", "Rate", "Daily Charge"]

    col_x = [40, 120, 240, 360, 480, 600, 700]

    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(headers):
        c.drawString(col_x[i], table_y, h)
    c.line(40, table_y-2, width-40, table_y-2)

    # 数据行
    row_y = table_y - 20
    c.setFont("Helvetica", 8)
    c.drawString(col_x[0], row_y, meter_name)
    c.drawString(col_x[1], row_y, usage_data["period"])
    c.drawString(col_x[2], row_y, f"{usage_data['prev_read']:.3f}")
    c.drawString(col_x[3], row_y, f"{usage_data['curr_read']:.3f}")
    c.drawString(col_x[4], row_y, f"{usage_data['consumption']:.3f}")
    c.drawString(col_x[5], row_y, f"{usage_data['unit_rate']:.6f}")
    c.drawString(col_x[6], row_y, f"{usage_data['daily_charge']:.5f}")

    c.line(40, row_y-2, width-40, row_y-2)

    # ===== Summary + Tariff =====
    y = row_y - 50
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Summary")
    c.setFont("Helvetica", 9)
    c.drawString(60, y-15, f"Average Units Per Day: {usage_data['avg_units']:.2f}")
    c.drawString(60, y-30, f"Average Cost Per Day: ${usage_data['avg_cost_per_day']:.2f}")

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y-60, "Tariff Summary")
    c.setFont("Helvetica", 9)
    c.drawString(60, y-75, f"Daily Charge: {usage_data['daily_charge']:.5f}")
    c.drawString(60, y-90, f"Consumption Rate: {usage_data['unit_rate']:.6f}")

    c.save()


# === 批量生成所有 Meter 的 Cover PDF ===
def generate_all_covers(file_path, output_folder, daily_charge=1.87964, unit_rate=0.381783):
    os.makedirs(output_folder, exist_ok=True)
    df = pd.read_excel(file_path)

    meters = df["Meter"].unique()
    for meter in meters:
        usage_data = calculate_usage(df, meter, daily_charge, unit_rate)
        pdf_path = os.path.join(output_folder, f"{meter}_Cover.pdf")
        generate_cover_page(pdf_path, usage_data, tenant_name=meter, premise=f"Premise ({meter})", meter_name=meter)
        print(f"✅ {meter} done: {pdf_path}")


# === 使用方法 ===
generate_all_covers(
    file_path=_BASE_DIR / "Results.xlsx",
    output_folder=_BASE_DIR / "CoverPages",
)



