import os
import re
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

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
    cleaned = re.sub(r'[^\x20-\x7E\u00A0-\u024F]+', '', cleaned)
    return cleaned

# ============ 提取 Shop No ============
def extract_shop_no(meter_name: str) -> str:
    match = re.search(r'\d+', str(meter_name))
    if match:
        return match.group(0)
    return meter_name if meter_name in ["Common", "MDB"] else None

# ============ 电费计算函数 ============
def calculate_usage(df, meter, shop_info, start_date, end_date):
    df_meter = df[df["Meter"] == meter].copy()
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter[(df_meter["DateTime"] >= start_date) & (df_meter["DateTime"] < end_date)]

    if df_meter.empty:
        return None

    prev_read = df_meter["kWh_IMP"].iloc[0]
    curr_read = df_meter["kWh_IMP"].iloc[-1]
    consumption = curr_read - prev_read

    # 固定 31 天
    days = 31

    daily_charge = shop_info.get("Daily Supply Charge $ (Exc. GST)", 0)
    daily_cost = daily_charge * days
    anytime_cost, after1650_cost, peak_cost, offpeak_cost = 0, 0, 0, 0

    # Anytime 阶梯电价
    if pd.notna(shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")):
        unit_rate = shop_info["AnyTime Consumption Rate $ (Exc. GST)"]
        after1650_rate = shop_info.get("After 1650 units (Exc. GST)", 0)

        if consumption <= 1650:
            anytime_cost = consumption * unit_rate
        else:
            anytime_cost = 1650 * unit_rate
            after1650_cost = (consumption - 1650) * after1650_rate

        total_excl = daily_cost + anytime_cost + after1650_cost

        return {
            "type": "anytime",
            "meter": meter,
            "period": f"{start_date.date()} - {end_date.date()}",
            "prev": prev_read,
            "curr": curr_read,
            "consumption": consumption,
            "anytime_cost": anytime_cost,
            "after1650_cost": after1650_cost,
            "daily_cost": daily_cost,
            "total_excl": total_excl,
            "gst": total_excl * 0.1,
            "total_incl": total_excl * 1.1
        }

    # TOU
    elif pd.notna(shop_info.get("Peak Time Rate $ (Exc. GST)")) and pd.notna(shop_info.get("Off Peak Rate $ (Exc. GST)")):
        peak_rate = shop_info["Peak Time Rate $ (Exc. GST)"]
        offpeak_rate = shop_info["Off Peak Rate $ (Exc. GST)"]

        df_meter["diff_kwh"] = df_meter["kWh_IMP"].diff().clip(lower=0).fillna(0)

        def classify(row):
            ts = row["DateTime"]
            weekday = ts.weekday()
            hour = ts.hour
            if weekday < 5 and 8 <= hour < 22:
                return "peak"
            return "offpeak"

        df_meter["period"] = df_meter.apply(classify, axis=1)
        peak_kwh = df_meter.loc[df_meter["period"]=="peak", "diff_kwh"].sum()
        offpeak_kwh = df_meter.loc[df_meter["period"]=="offpeak", "diff_kwh"].sum()

        peak_cost = peak_kwh * peak_rate
        offpeak_cost = offpeak_kwh * offpeak_rate

        total_excl = daily_cost + peak_cost + offpeak_cost

        return {
            "type": "tou",
            "meter": meter,
            "period": f"{start_date.date()} - {end_date.date()}",
            "prev": prev_read,
            "curr": curr_read,
            "consumption": consumption,
            "peak_cost": peak_cost,
            "offpeak_cost": offpeak_cost,
            "daily_cost": daily_cost,
            "total_excl": total_excl,
            "gst": total_excl * 0.1,
            "total_incl": total_excl * 1.1
        }
    return None

# ============ 生成 Summary Report ============
def generate_summary_report(results_file, mapping_file, output_pdf):
    df = pd.read_excel(results_file)
    df["DateTime"] = pd.to_datetime(df["DateTime"])

    start_date = pd.to_datetime("2025-07-17 00:00:00")
    end_date = pd.to_datetime("2025-08-17 00:00:00")

    mapping_df = pd.read_excel(mapping_file)
    mapping_df.columns = mapping_df.columns.str.strip()
    mapping_df["Shop No."] = mapping_df["Shop No."].astype(str)
    mapping = mapping_df.set_index("Shop No.").to_dict(orient="index")

    # MDB 和 Common 用 Shop11 的 tariff
    shop11_tariff = mapping.get("11", {})
    mapping["MDB"] = shop11_tariff
    mapping["Common"] = shop11_tariff

    order = ["MDB", "Common"] + [str(i) for i in range(1, 20)]

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output_pdf, pagesize=landscape(A4), leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=20)
    elements = []

    elements.append(Paragraph("<para align='center'><b><font size=14>Tenants Summary Report</font></b></para>", styles["Normal"]))
    elements.append(Spacer(1, 20))

    for shop_no in order:
        meter = shop_no if shop_no in ["MDB", "Common"] else f"SHOP{shop_no}"
        shop_info = mapping.get(shop_no, {})
        if not shop_info:
            continue
        usage = calculate_usage(df, meter, shop_info, start_date, end_date)
        if not usage:
            continue

        elements.append(Paragraph(f"<b>{meter}</b>", styles["Normal"]))
        elements.append(Spacer(1, 4))

        if usage["type"] == "anytime":
            data = [
                ["Date", "Prev (kWh)", "Curr (kWh)", "Consumption (kWh)", "Anytime Cost ($)", "After1650 Cost ($)", "Daily Supply ($)", "Total excl GST ($)"],
                [usage["period"], f"{usage['prev']:.3f}", f"{usage['curr']:.3f}", f"{usage['consumption']:.3f}",
                 f"{usage['anytime_cost']:.2f}", f"{usage['after1650_cost']:.2f}", f"{usage['daily_cost']:.2f}", f"{usage['total_excl']:.2f}"],
                ["", "", "", "", "", "", "GST (10%)", f"{usage['gst']:.2f}"],
                ["", "", "", "", "", "", "TOTAL inc GST", f"{usage['total_incl']:.2f}"]
            ]
        else:
            data = [
                ["Date", "Prev (kWh)", "Curr (kWh)", "Consumption (kWh)", "Peak Cost ($)", "Off-Peak Cost ($)", "Daily Supply ($)", "Total excl GST ($)"],
                [usage["period"], f"{usage['prev']:.3f}", f"{usage['curr']:.3f}", f"{usage['consumption']:.3f}",
                 f"{usage['peak_cost']:.2f}", f"{usage['offpeak_cost']:.2f}", f"{usage['daily_cost']:.2f}", f"{usage['total_excl']:.2f}"],
                ["", "", "", "", "", "", "GST (10%)", f"{usage['gst']:.2f}"],
                ["", "", "", "", "", "", "TOTAL inc GST", f"{usage['total_incl']:.2f}"]
            ]

        table = Table(data, colWidths=[130, 80, 80, 100, 100, 100, 100, 120])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('SPAN', (0, 2), (-5, 2)),
            ('SPAN', (0, 3), (-5, 3)),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 15))

    doc.build(elements)
    print(f"✅ 报告已生成: {output_pdf}")

# ============ 使用 ============
generate_summary_report(
    results_file="/cleaned_30min.xlsx",
    mapping_file="/C&E Report (Tariff after July).xlsx",
    output_pdf="Tenants_Summary_Report.pdf"
)






