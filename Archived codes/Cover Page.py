import os
import re
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent

# ============ Strip hidden characters from text ============
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
    cleaned = re.sub(r'[^\x20-\x7E\u00A0-\u024F]+', '', cleaned)
    return cleaned

# ============ Extract shop number from meter name ============
def extract_shop_no(meter_name: str) -> str:
    match = re.search(r'\d+', str(meter_name))
    if match:
        return match.group(0)
    return meter_name if meter_name in ["Common Service", "MDB"] else None

# ============ Electricity usage and cost calculation ============
def calculate_usage(df, meter, shop_info):
    df_meter = df[df["Meter"] == meter].copy()
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter.sort_values("DateTime")

    if df_meter.empty:
        return None

    start_time = df_meter["DateTime"].iloc[0]
    end_time = df_meter["DateTime"].iloc[-1]
    days = (end_time - start_time).days + 1

    prev_read = df_meter["kWh_IMP"].iloc[0]
    curr_read = df_meter["kWh_IMP"].iloc[-1]
    consumption = curr_read - prev_read

    # Daily Supply Charge
    daily_charge = shop_info.get("Daily Supply Charge $ (Exc. GST)", 0)
    daily_cost = daily_charge * days
    consumption_cost = 0
    peak_kwh, offpeak_kwh, peak_rate, offpeak_rate = None, None, None, None
    anytime_cost, after1650_cost = None, None

    # ===== AnyTime or tiered tariff =====
    if pd.notna(shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")):
        unit_rate = shop_info["AnyTime Consumption Rate $ (Exc. GST)"]

        if pd.notna(shop_info.get("After 1650 units (Exc. GST)")):
            after1650_rate = shop_info["After 1650 units (Exc. GST)"]
            if consumption <= 1650:
                anytime_cost = consumption * unit_rate
                after1650_cost = 0
            else:
                anytime_cost = 1650 * unit_rate
                after1650_cost = (consumption - 1650) * after1650_rate
            consumption_cost = anytime_cost + after1650_cost
        else:
            anytime_cost = consumption * unit_rate
            after1650_cost = 0
            consumption_cost = anytime_cost

    # ===== TOU (Peak / Off-Peak) =====
    elif pd.notna(shop_info.get("Peak Time Rate $ (Exc. GST)")) and pd.notna(shop_info.get("Off Peak Rate $ (Exc. GST)")):
        peak_rate = shop_info["Peak Time Rate $ (Exc. GST)"]
        offpeak_rate = shop_info["Off Peak Rate $ (Exc. GST)"]

        df_meter["diff_kwh"] = df_meter["kWh_IMP"].diff().fillna(0)

        def classify(row):
            ts = row["DateTime"]
            weekday = ts.weekday()
            hour = ts.hour
            if weekday < 5:  # Mon-Fri
                if 8 <= hour < 22:
                    return "peak"
                else:
                    return "offpeak"
            else:  # Sat-Sun
                return "offpeak"

        df_meter["period"] = df_meter.apply(classify, axis=1)
        peak_kwh = df_meter.loc[df_meter["period"]=="peak", "diff_kwh"].sum()
        offpeak_kwh = df_meter.loc[df_meter["period"]=="offpeak", "diff_kwh"].sum()

        consumption_cost = peak_kwh * peak_rate + offpeak_kwh * offpeak_rate

    # Total cost
    total_excl = daily_cost + consumption_cost
    gst = total_excl * 0.1
    total_incl = total_excl + gst
    avg_units = consumption / days if days > 0 else 0
    avg_cost_per_day = total_incl / days if days > 0 else 0

    return {
        "period": f"{start_time.date()} - {end_time.date()}",
        "days": days,
        "consumption": consumption,
        "daily_charge": daily_charge,
        "daily_cost": daily_cost,
        "anytime_cost": anytime_cost,
        "after1650_cost": after1650_cost,
        "consumption_cost": consumption_cost,
        "total_excl": total_excl,
        "gst": gst,
        "total_incl": total_incl,
        "avg_units": avg_units,
        "avg_cost_per_day": avg_cost_per_day,
        "peak_kwh": peak_kwh,
        "offpeak_kwh": offpeak_kwh,
        "peak_rate": peak_rate,
        "offpeak_rate": offpeak_rate
    }

# ============ Generate cover page PDF ============
def generate_cover_page(pdf_path, usage_data, shop_info, meter, statement_date="2025/07/22"):
    c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Header bar
    c.setFillColor(colors.HexColor("#2E7D32"))
    c.rect(40, height-60, width-80, 30, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.white)
    c.drawString(50, height-50, "YOUR_COMPANY_NAME")
    c.drawRightString(width-50, height-50, "Electricity Statement")

    # Statement date
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(40, height-90, f"Statement Date: {statement_date}")

    # Tenant info
    company = clean_text(shop_info.get("Company", "Unknown"))
    address = clean_text(shop_info.get("Address", "Unknown"))

    c.drawString(40, height-120, "To:")
    c.drawString(80, height-120, company)
    c.drawString(80, height-140, address)

    # Prepared by
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, height-190, "Prepared by YOUR_ORG_NAME on behalf of:")
    c.setFont("Helvetica", 9)
    c.drawString(40, height-205, "YOUR_ADDRESS")

    # Statement Summary box
    box_x = width - 300
    box_y = height - 120
    c.setFont("Helvetica-Bold", 9)
    c.drawString(box_x, box_y, "Statement Summary")
    c.setFont("Helvetica", 9)

    c.drawString(box_x, box_y-20, "Report Period")
    c.drawRightString(width-50, box_y-20, usage_data["period"])
    c.drawString(box_x, box_y-40, "Total (excl GST)")
    c.drawRightString(width-50, box_y-40, f"${usage_data['total_excl']:.2f}")
    c.drawString(box_x, box_y-60, "GST (10%)")
    c.drawRightString(width-50, box_y-60, f"${usage_data['gst']:.2f}")

    # Total incl GST
    row_y = box_y - 95
    c.setFillColor(colors.HexColor("#2E7D32"))
    c.rect(box_x, row_y, 120, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(box_x + 60, row_y + 5, "Total (incl GST)")
    c.setFillColor(colors.limegreen)
    c.rect(width - 120, row_y, 70, 18, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width - 85, row_y + 5, f"${usage_data['total_incl']:.2f}")

    # ===== Charges table =====
    table_y = height-300
    if usage_data.get("peak_rate") is not None:
        headers = [
            "Unit", "Date", "Consumption (kWh)", "Peak Usage (kWh)", "Off-Peak Usage (kWh)",
            "Peak Cost ($)", "Off-Peak Cost ($)", "Daily Supply Cost ($)", "Subtotal (excl GST) ($)"
        ]
        col_x = [40, 110, 210, 310, 420, 530, 620, 710, 850]

        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            c.drawString(col_x[i], table_y, h)
        c.line(40, table_y-2, width-40, table_y-2)

        row_y = table_y - 20
        c.setFont("Helvetica", 8)
        c.drawString(col_x[0], row_y, meter)
        c.drawString(col_x[1], row_y, usage_data["period"])
        c.drawString(col_x[2], row_y, f"{usage_data['consumption']:.3f}")

        peak_cost = usage_data["peak_kwh"] * usage_data["peak_rate"]
        offpeak_cost = usage_data["offpeak_kwh"] * usage_data["offpeak_rate"]
        c.drawString(col_x[3], row_y, f"{usage_data['peak_kwh']:.2f}")
        c.drawString(col_x[4], row_y, f"{usage_data['offpeak_kwh']:.2f}")
        c.drawString(col_x[5], row_y, f"{peak_cost:.2f}")
        c.drawString(col_x[6], row_y, f"{offpeak_cost:.2f}")
        c.drawString(col_x[7], row_y, f"{usage_data['daily_cost']:.2f}")
        subtotal = peak_cost + offpeak_cost + usage_data["daily_cost"]
        c.drawString(col_x[8], row_y, f"{subtotal:.2f}")

    else:
        headers = [
            "Unit", "Date", "Consumption (kWh)", "Anytime Usage (kWh)", "After1650 Usage (kWh)",
            "Anytime Cost ($)", "After1650 Cost ($)", "Daily Supply Cost ($)", "Subtotal (excl GST) ($)"
        ]
        col_x = [40, 110, 210, 310, 420, 530, 620, 710, 850]

        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            c.drawString(col_x[i], table_y, h)
        c.line(40, table_y-2, width-40, table_y-2)

        row_y = table_y - 20
        c.setFont("Helvetica", 8)
        c.drawString(col_x[0], row_y, meter)
        c.drawString(col_x[1], row_y, usage_data["period"])
        c.drawString(col_x[2], row_y, f"{usage_data['consumption']:.3f}")

        anytime_kwh = min(usage_data["consumption"], 1650)
        after1650_kwh = max(0, usage_data["consumption"] - 1650)
        c.drawString(col_x[3], row_y, f"{anytime_kwh:.2f}")
        c.drawString(col_x[4], row_y, f"{after1650_kwh:.2f}")
        c.drawString(col_x[5], row_y, f"{usage_data['anytime_cost'] or 0:.2f}")
        c.drawString(col_x[6], row_y, f"{usage_data['after1650_cost'] or 0:.2f}")
        c.drawString(col_x[7], row_y, f"{usage_data['daily_cost']:.2f}")
        subtotal = (usage_data['anytime_cost'] or 0) + (usage_data['after1650_cost'] or 0) + usage_data["daily_cost"]
        c.drawString(col_x[8], row_y, f"{subtotal:.2f}")

    c.line(40, row_y-2, width-40, row_y-2)

    # Summary
    y = row_y - 50
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Summary")
    c.setFont("Helvetica", 9)
    c.drawString(60, y-15, f"Average Units Per Day: {usage_data['avg_units']:.2f}")
    c.drawString(60, y-30, f"Average Cost Per Day: ${usage_data['avg_cost_per_day']:.2f}")

    # Tariff summary
    y = y - 40
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Tariff Summary")
    c.setFont("Helvetica", 9)

    if usage_data.get("peak_rate") is not None:
        c.drawString(60, y-15, f"Peak Rate: {usage_data['peak_rate']:.5f}")
        c.drawString(60, y-30, f"OffPeak Rate: {usage_data['offpeak_rate']:.5f}")
        c.drawString(60, y-45, f"Daily Supply Charge (per day): {usage_data['daily_charge']:.5f}")
        c.drawString(60, y-60, f"Billing Days: {usage_data['days']} days")
    else:
        c.drawString(60, y-15, f"AnyTime Rate: {shop_info['AnyTime Consumption Rate $ (Exc. GST)']:.5f}")
        c.drawString(60, y-30, f"After 1650 units Rate: {shop_info['After 1650 units (Exc. GST)']:.5f}")
        c.drawString(60, y-45, f"Daily Supply Charge (per day): {usage_data['daily_charge']:.5f}")
        c.drawString(60, y-60, f"Billing Days: {usage_data['days']} days")

    c.save()

# ============ Main: generate all cover pages ============
def generate_all_covers(results_file, mapping_file, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    df = pd.read_excel(results_file)
    mapping_df = pd.read_excel(mapping_file)

    mapping_df.columns = mapping_df.columns.str.strip().str.replace("（", "(", regex=False).str.replace("）", ")", regex=False)
    mapping_df["Shop No."] = mapping_df["Shop No."].astype(str)
    mapping = mapping_df.set_index("Shop No.").to_dict(orient="index")

    for meter in df["Meter"].unique():
        shop_no = extract_shop_no(meter)
        if not shop_no:
            continue

        # MDB and Common Service use Anytime table
        if shop_no in ["Common Service", "MDB"]:
            shop_info = mapping.get("2", {}).copy()  # Use Shop2 tariff as reference (adjust as needed)
        else:
            shop_info = mapping.get(shop_no, {})
        if not shop_info:
            continue

        usage_data = calculate_usage(df, meter, shop_info)
        if not usage_data:
            continue

        pdf_path = os.path.join(output_folder, f"{meter}_Cover.pdf")
        generate_cover_page(pdf_path, usage_data, shop_info, meter)
        print(f"Done: {pdf_path}")

# ============ Run ============
generate_all_covers(
    results_file=_BASE_DIR / "cleaned_30min.xlsx",
    mapping_file=_BASE_DIR / "C&E Report (Tariff after July).xlsx",
    output_folder=_BASE_DIR / "CoverPages",
)







