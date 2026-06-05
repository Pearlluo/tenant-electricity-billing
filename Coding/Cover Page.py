import os
import re
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent


# ============ 清理隐藏字符 ============
def clean_text(text):
    if pd.isna(text):
        return ""
    cleaned = (
        str(text)
        .replace("\u202c", "")
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .strip()
    )
    cleaned = re.sub(r"[^\x20-\x7E\u00A0-\u024F]+", "", cleaned)
    return cleaned


# ============ 提取 Shop No ============
def extract_shop_no(meter_name: str) -> str:
    match = re.search(r"\d+", str(meter_name))
    if match:
        return match.group(0)
    return meter_name if meter_name in ["Common", "MDB", "Common Service"] else None


# ============ 电费计算函数 ============
def calculate_usage(df, meter, shop_info):
    df_meter = df[df["Meter"] == meter].copy()
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter.sort_values("DateTime")

    if df_meter.empty:
        return None

    # 固定周期
    start_time = pd.Timestamp("2025-07-17 00:00:00")
    end_time = pd.Timestamp("2025-08-17 00:00:00")
    days = 31

    prev_read = df_meter.loc[df_meter["DateTime"] == start_time, "kWh_IMP"].iloc[0]
    curr_read = df_meter.loc[df_meter["DateTime"] == end_time, "kWh_IMP"].iloc[0]
    consumption = curr_read - prev_read
    avg_daily_kwh = consumption / days if days > 0 else 0

    # Daily Supply Charge
    daily_charge = shop_info.get("Daily Supply Charge $ (Exc. GST)", 0)
    daily_cost = daily_charge * days

    # 阶梯电价 / TOU
    anytime_cost, after1650_cost, peak_cost, offpeak_cost = 0, 0, 0, 0
    peak_kwh, offpeak_kwh = 0, 0

    if pd.notna(shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")):
        anytime_rate = shop_info["AnyTime Consumption Rate $ (Exc. GST)"]
        after1650_rate = shop_info.get("After 1650 units (Exc. GST)", 0)

        if avg_daily_kwh <= 1650:
            anytime_cost = consumption * anytime_rate
        else:
            anytime_cost = 1650 * days * anytime_rate
            after1650_cost = (consumption - 1650 * days) * after1650_rate

    elif pd.notna(shop_info.get("Peak Time Rate $ (Exc. GST)")) and pd.notna(
        shop_info.get("Off Peak Rate $ (Exc. GST)")
    ):
        peak_rate = shop_info["Peak Time Rate $ (Exc. GST)"]
        offpeak_rate = shop_info["Off Peak Rate $ (Exc. GST)"]

        df_meter["diff_kwh"] = df_meter["kWh_IMP"].diff().fillna(0)

        def classify(row):
            ts = row["DateTime"]
            weekday = ts.weekday()
            hour = ts.hour
            if weekday < 5 and 8 <= hour < 22:
                return "peak"
            return "offpeak"

        df_meter["period"] = df_meter.apply(classify, axis=1)
        peak_kwh = df_meter.loc[df_meter["period"] == "peak", "diff_kwh"].sum()
        offpeak_kwh = df_meter.loc[df_meter["period"] == "offpeak", "diff_kwh"].sum()

        peak_cost = peak_kwh * peak_rate
        offpeak_cost = offpeak_kwh * offpeak_rate

    # ===== 总费用 =====
    consumption_cost = anytime_cost + after1650_cost + peak_cost + offpeak_cost
    total_excl = daily_cost + consumption_cost
    gst = total_excl * 0.1
    total_incl = total_excl + gst
    avg_cost_per_day = total_incl / days if days > 0 else 0

    return {
        "period": f"{start_time.date()} - {end_time.date()}",
        "days": days,
        "consumption": consumption,
        "daily_charge": daily_charge,
        "daily_cost": daily_cost,
        "anytime_cost": anytime_cost,
        "after1650_cost": after1650_cost,
        "peak_cost": peak_cost,
        "offpeak_cost": offpeak_cost,
        "peak_kwh": peak_kwh,
        "offpeak_kwh": offpeak_kwh,
        "total_excl": total_excl,
        "gst": gst,
        "total_incl": total_incl,
        "avg_units": avg_daily_kwh,
        "avg_cost_per_day": avg_cost_per_day,
    }


# ============ PDF 生成函数 ============
def generate_cover_page(pdf_path, usage_data, shop_info, meter, embedded_data=None, statement_date="2025/08/20"):
    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
    width, height = landscape(A4)

    # ===== Header =====
    c.setFillColor(colors.HexColor("#2E7D32"))
    c.rect(40, height - 60, width - 80, 30, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.white)
    c.drawString(50, height - 50, "H & N Perry")
    c.drawRightString(width - 50, height - 50, "Electricity Statement")

    # ===== Statement Date =====
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(40, height - 90, f"Statement Date: {statement_date}")

    # ===== To (Tenant) =====
    company = clean_text(shop_info.get("Company", "Unknown"))
    address = clean_text(shop_info.get("Address", "Unknown"))

    c.drawString(40, height - 120, "To:")
    c.drawString(80, height - 120, company)
    c.drawString(80, height - 140, address)

    # ===== Asset Name 和 BFM Serial =====
    asset_name = clean_text(shop_info.get("Electrical Meter Asset Name", ""))
    bfm_serial = clean_text(shop_info.get("BFM Serial", ""))
    c.drawString(40, height - 170, f"Electrical Meter Asset Name: {asset_name}")
    c.drawString(40, height - 185, f"BFM Serial: {bfm_serial}")

    # ===== Prepared by =====
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, height - 210, "Prepared by Element47 Pty Ltd on behalf of:")
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 225, "The Plaza Centre, 38 Mandurah Terrace, Mandurah 6210")

    # ===== Statement Summary =====
    box_x = width - 300
    box_y = height - 120
    c.setFont("Helvetica-Bold", 9)
    c.drawString(box_x, box_y, "Statement Summary")
    c.setFont("Helvetica", 9)

    c.drawString(box_x, box_y - 20, "Report Period")
    c.drawRightString(width - 50, box_y - 20, usage_data["period"])

    # 如果是 Common，加上 Loss
    elec_excl = usage_data["total_excl"]
    loss_excl = embedded_data["loss_cost"] if embedded_data else 0
    total_excl = elec_excl + loss_excl
    gst = total_excl * 0.1
    total_incl = total_excl + gst

    c.drawString(box_x, box_y - 40, "Electricity Usage excl GST")
    c.drawRightString(width - 50, box_y - 40, f"${elec_excl:.2f}")

    if embedded_data:
        c.drawString(box_x, box_y - 60, "All Meter Loss Cost excl GST")
        c.drawRightString(width - 50, box_y - 60, f"${loss_excl:.2f}")
        c.drawString(box_x, box_y - 80, "Total excl GST")
        c.drawRightString(width - 50, box_y - 80, f"${total_excl:.2f}")
        c.drawString(box_x, box_y - 100, "GST (10%)")
        c.drawRightString(width - 50, box_y - 100, f"${gst:.2f}")
        row_y = box_y - 130
    else:
        c.drawString(box_x, box_y - 60, "Total excl GST")
        c.drawRightString(width - 50, box_y - 60, f"${elec_excl:.2f}")
        c.drawString(box_x, box_y - 80, "GST (10%)")
        c.drawRightString(width - 50, box_y - 80, f"${usage_data['gst']:.2f}")
        row_y = box_y - 110

    c.setFillColor(colors.HexColor("#2E7D32"))
    c.rect(box_x, row_y, 120, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(box_x + 60, row_y + 5, "Total (incl GST)")
    c.setFillColor(colors.limegreen)
    c.rect(width - 120, row_y, 70, 18, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width - 85, row_y + 5, f"${total_incl:.2f}")

    # ===== Charges 表格 =====
    table_y = height - 300

    if usage_data["anytime_cost"] or usage_data["after1650_cost"]:
        headers = [
            "Unit", "Date", "Consumption (kWh)", "Anytime Usage (kWh)", "After1650 Usage (kWh)",
            "Anytime Cost ($)", "After1650 Cost ($)", "Daily Supply Cost ($)"
        ]
        col_x = [40, 90, 190, 300, 410, 520, 620, 710]
        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            c.drawString(col_x[i], table_y, h)
        c.line(40, table_y - 2, width - 40, table_y - 2)

        row_y = table_y - 20
        c.setFont("Helvetica", 8)
        c.drawString(col_x[0], row_y, meter)
        c.drawString(col_x[1], row_y, usage_data["period"])
        c.drawString(col_x[2], row_y, f"{usage_data['consumption']:.3f}")

        anytime_kwh = min(usage_data["consumption"], 1650 * usage_data["days"])
        after1650_kwh = max(0, usage_data["consumption"] - 1650 * usage_data["days"])

        c.drawString(col_x[3], row_y, f"{anytime_kwh:.2f}")
        c.drawString(col_x[4], row_y, f"{after1650_kwh:.2f}")
        c.drawString(col_x[5], row_y, f"{usage_data['anytime_cost']:.2f}")
        c.drawString(col_x[6], row_y, f"{usage_data['after1650_cost']:.2f}")
        c.drawString(col_x[7], row_y, f"{usage_data['daily_cost']:.2f}")

    else:  # TOU Tariff
        headers = [
            "Unit", "Date", "Consumption (kWh)", "Peak Usage (kWh)", "Off-Peak Usage (kWh)",
            "Peak Cost ($)", "Off-Peak Cost ($)", "Daily Supply Cost ($)"
        ]
        col_x = [40, 90, 190, 300, 410, 520, 620, 710]
        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            c.drawString(col_x[i], table_y, h)
        c.line(40, table_y - 2, width - 40, table_y - 2)

        row_y = table_y - 20
        c.setFont("Helvetica", 8)
        c.drawString(col_x[0], row_y, meter)
        c.drawString(col_x[1], row_y, usage_data["period"])
        c.drawString(col_x[2], row_y, f"{usage_data['consumption']:.3f}")
        c.drawString(col_x[3], row_y, f"{usage_data['peak_kwh']:.2f}")
        c.drawString(col_x[4], row_y, f"{usage_data['offpeak_kwh']:.2f}")
        c.drawString(col_x[5], row_y, f"{usage_data['peak_cost']:.2f}")
        c.drawString(col_x[6], row_y, f"{usage_data['offpeak_cost']:.2f}")
        c.drawString(col_x[7], row_y, f"{usage_data['daily_cost']:.2f}")

    c.line(40, row_y - 2, width - 40, row_y - 2)

    # ===== Embedded 表格 (仅 Common) =====
    if meter == "Common" and embedded_data:
        row_y -= 40
        headers2 = [
            "Embedded Network Sum (kWh)", "Grid Costs (MDB) (kWh)",
            "Var (kWh)", "Tariff Rate", "Loss Cost per day ($)", "Period (days)", "Loss Cost Total ($)"
        ]
        col_x2 = [40, 190, 300, 410, 520, 620, 710]

        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers2):
            c.drawString(col_x2[i], row_y, h)
        c.line(40, row_y - 2, width - 40, row_y - 2)

        row_y -= 20
        c.setFont("Helvetica", 8)

        loss_cost_per_day = embedded_data["loss_cost"] / embedded_data["days"]

        c.drawString(col_x2[0], row_y, f"{embedded_data['embedded_sum']:.3f}")
        c.drawString(col_x2[1], row_y, f"{embedded_data['mdb']:.3f}")
        c.drawString(col_x2[2], row_y, f"{embedded_data['var']:.3f}")
        c.drawString(col_x2[3], row_y, "0.347075")
        c.drawString(col_x2[4], row_y, f"{loss_cost_per_day:.2f}")
        c.drawString(col_x2[5], row_y, f"{embedded_data['days']}")
        c.drawString(col_x2[6], row_y, f"{embedded_data['loss_cost']:.2f}")
        c.line(40, row_y - 2, width - 40, row_y - 2)

    # ===== Summary =====
    y = row_y - 50
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Summary")
    c.setFont("Helvetica", 9)
    c.drawString(60, y - 15, f"Average Units Per Day: {usage_data['avg_units']:.2f}")
    c.drawString(60, y - 30, f"Average Cost Per Day: ${usage_data['avg_cost_per_day']:.2f}")

    # ===== Tariff Summary =====
    y = y - 40
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Tariff Summary")
    c.setFont("Helvetica", 9)
    if pd.notna(shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")):
        c.drawString(60, y - 15, f"AnyTime Rate: {shop_info['AnyTime Consumption Rate $ (Exc. GST)']:.5f}")
        if pd.notna(shop_info.get("After 1650 units (Exc. GST)")):
            c.drawString(60, y - 30, f"After 1650 units Rate: {shop_info['After 1650 units (Exc. GST)']:.5f}")
    elif pd.notna(shop_info.get("Peak Time Rate $ (Exc. GST)")) and pd.notna(shop_info.get("Off Peak Rate $ (Exc. GST)")):
        c.drawString(60, y - 15, f"Peak Rate: {shop_info['Peak Time Rate $ (Exc. GST)']:.5f}")
        c.drawString(60, y - 30, f"Off-Peak Rate: {shop_info['Off Peak Rate $ (Exc. GST)']:.5f}")
    if pd.notna(shop_info.get("Daily Supply Charge $ (Exc. GST)")):
        c.drawString(60, y - 45, f"Daily Supply Charge (per day): {usage_data['daily_charge']:.5f}")
    c.drawString(60, y - 60, f"Billing Days: {usage_data['days']} days")

    c.save()
# ============ 主程序 ============
def generate_all_covers(results_file, mapping_file, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    # ===== 读取数据 =====
    df = pd.read_excel(results_file)
    mapping_df = pd.read_excel(mapping_file)

    mapping_df.columns = mapping_df.columns.str.strip()
    mapping_df["Shop No."] = mapping_df["Shop No."].astype(str)
    mapping = mapping_df.set_index("Shop No.").to_dict(orient="index")

    results = {}
    mdb_val = 0
    embedded_sum = 0

    # ===== 遍历每个 meter，计算用电量 =====
    for meter in df["Meter"].unique():
        shop_no = extract_shop_no(meter)
        if not shop_no:
            continue

        shop_info = mapping.get(shop_no, {})
        if not shop_info:
            print(f"⚠️ 未找到 {shop_no} 的 tariff 信息，跳过 {meter}")
            continue

        usage_data = calculate_usage(df, meter, shop_info)
        if not usage_data:
            continue

        results[meter] = usage_data

        # 特殊处理 MDB 和 Common
        if meter == "MDB":
            mdb_val = usage_data["consumption"]
        else:
            embedded_sum += usage_data["consumption"]

    # ===== 计算 Embedded Network 数据（只给 Common 用） =====
    var_val = mdb_val - embedded_sum
    loss_cost = max(0, var_val) * 0.347075
    embedded_data = {
        "embedded_sum": embedded_sum,
        "mdb": mdb_val,
        "var": var_val,
        "loss_cost": loss_cost,
        "days": 31
    }

    # ===== 生成每个 PDF =====
    for meter, usage_data in results.items():
        shop_no = extract_shop_no(meter)
        shop_info = mapping.get(shop_no, {})

        pdf_path = os.path.join(output_folder, f"{meter}_Cover.pdf")

        if meter == "Common":
            generate_cover_page(
                pdf_path,
                usage_data,
                shop_info,
                meter,
                embedded_data=embedded_data
            )
        else:
            generate_cover_page(
                pdf_path,
                usage_data,
                shop_info,
                meter
            )

        print(f"✅ {meter} done: {pdf_path}")


# ============ 使用 ============
generate_all_covers(
    results_file=_BASE_DIR / "cleaned_30min.xlsx",
    mapping_file=_BASE_DIR / "C&E Report (Tariff after July).xlsx",
    output_folder=_BASE_DIR / "CoverPages",
)



