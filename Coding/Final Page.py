import re
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
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
    return meter_name if meter_name in ["Common", "MDB"] else None

# ============ 安全获取读数（支持插值） ============
def get_read_at(df_meter, target_time, column="kWh_IMP"):
    df_exact = df_meter.loc[df_meter["DateTime"] == target_time, column]
    if not df_exact.empty:
        return df_exact.iloc[0]
    # 没有精确点 → 前后点插值
    df_before = df_meter[df_meter["DateTime"] < target_time].tail(1)
    df_after = df_meter[df_meter["DateTime"] > target_time].head(1)
    if not df_before.empty and not df_after.empty:
        t1, v1 = df_before["DateTime"].iloc[0], df_before[column].iloc[0]
        t2, v2 = df_after["DateTime"].iloc[0], df_after[column].iloc[0]
        ratio = (target_time - t1) / (t2 - t1)
        return v1 + ratio * (v2 - v1)
    # fallback：取头尾
    if not df_before.empty:
        return df_before[column].iloc[0]
    if not df_after.empty:
        return df_after[column].iloc[0]
    return None

# ============ 电费计算函数 ============
def calculate_usage(df, meter, shop_info, start_date, end_date, skip_cost=False):
    df_meter = df[df["Meter"] == meter].copy()
    df_meter["DateTime"] = pd.to_datetime(df_meter["DateTime"])
    df_meter = df_meter.sort_values("DateTime")

    if df_meter.empty:
        return None

    prev_read = get_read_at(df_meter, start_date)
    curr_read = get_read_at(df_meter, end_date)
    if prev_read is None or curr_read is None:
        return None

    consumption = curr_read - prev_read

    # 固定 31 天
    days = 31
    daily_charge = shop_info.get("Daily Supply Charge $ (Exc. GST)", 0)
    anytime_rate = shop_info.get("AnyTime Consumption Rate $ (Exc. GST)")
    after1650_rate = shop_info.get("After 1650 units (Exc. GST)")
    peak_rate = shop_info.get("Peak Time Rate $ (Exc. GST)")
    offpeak_rate = shop_info.get("Off Peak Rate $ (Exc. GST)")

    # Anytime 阶梯电价
    if pd.notna(anytime_rate):
        df_meter["kWh_IMP_interval"] = df_meter["kWh_IMP"].diff().clip(lower=0).fillna(0)
        df_daily = df_meter.resample("D", on="DateTime").sum()

        df_daily["Anytime_kWh"] = df_daily["kWh_IMP_interval"].clip(upper=1650)
        df_daily["After1650_kWh"] = (df_daily["kWh_IMP_interval"] - 1650).clip(lower=0)

        anytime_cost = (df_daily["Anytime_kWh"] * anytime_rate).sum()
        after1650_cost = (df_daily["After1650_kWh"] * after1650_rate).sum()
        daily_cost = daily_charge * days

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
            "total_incl": total_excl * 1.1,
        }

    # TOU
    elif pd.notna(peak_rate) and pd.notna(offpeak_rate):
        df_meter["diff_kwh"] = df_meter["kWh_IMP"].diff().clip(lower=0).fillna(0)

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
        daily_cost = daily_charge * days

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
            "total_incl": total_excl * 1.1,
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

    order = ["MDB", "Common"] + [str(i) for i in range(1, 20)]

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output_pdf, pagesize=landscape(A4),
                            leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=20)
    elements = []

    elements.append(Paragraph("<para align='center'><b><font size=14>Tenants Summary Report</font></b></para>", styles["Normal"]))
    elements.append(Spacer(1, 20))

    total_consumption = 0
    total_cost_incl = 0
    check_consumption = 0
    check_cost_incl = 0

    skip_shops = {"13", "17", "18"}

    # 固定 Loss Cost
    loss_cost_excl = 310.35
    loss_cost_incl = loss_cost_excl * 1.1

    for shop_no in order:
        if shop_no in skip_shops:
            continue

        meter = shop_no if shop_no in ["MDB", "Common"] else f"SHOP{shop_no}"
        shop_info = mapping.get(shop_no, {})
        if not shop_info:
            continue

        usage = calculate_usage(df, meter, shop_info, start_date, end_date, skip_cost=False)
        if not usage:
            continue

        if shop_no == "MDB":
            check_consumption = usage["consumption"]
            check_cost_incl = usage["total_incl"]
        else:
            total_consumption += usage["consumption"]
            total_cost_incl += usage["total_incl"]

        elements.append(Paragraph(f"<b>{meter}</b>", styles["Normal"]))
        elements.append(Spacer(1, 4))

        if usage["type"] == "anytime":
            data = [
                ["Date", "Prev (kWh)", "Curr (kWh)", "Consumption (kWh)",
                 "Anytime Cost ($)", "After1650 Cost ($)", "Daily Supply ($)", "Total excl GST ($)"],
                [usage["period"], f"{usage['prev']:.3f}", f"{usage['curr']:.3f}", f"{usage['consumption']:.3f}",
                 f"{usage['anytime_cost']:.2f}", f"{usage['after1650_cost']:.2f}",
                 f"{usage['daily_cost']:.2f}", f"{usage['total_excl']:.2f}"],
                ["", "", "", "", "", "", "GST (10%)", f"{usage['gst']:.2f}"],
                ["", "", "", "", "", "", "TOTAL inc GST", f"{usage['total_incl']:.2f}"],
            ]

            # === 如果是 Common，加 Loss Cost ===
            if shop_no == "Common":
                data.append(["", "", "", "", "", "", "All Meter Loss Cost", f"{loss_cost_excl:.2f}"])
                data.append(["", "", "", "", "", "", "TOTAL inc GST (with Loss)", f"{usage['total_incl'] + loss_cost_incl:.2f}"])

        else:
            data = [
                ["Date", "Prev (kWh)", "Curr (kWh)", "Consumption (kWh)",
                 "Peak Cost ($)", "Off-Peak Cost ($)", "Daily Supply ($)", "Total excl GST ($)"],
                [usage["period"], f"{usage['prev']:.3f}", f"{usage['curr']:.3f}", f"{usage['consumption']:.3f}",
                 f"{usage['peak_cost']:.2f}", f"{usage['offpeak_cost']:.2f}",
                 f"{usage['daily_cost']:.2f}", f"{usage['total_excl']:.2f}"],
                ["", "", "", "", "", "", "GST (10%)", f"{usage['gst']:.2f}"],
                ["", "", "", "", "", "", "TOTAL inc GST", f"{usage['total_incl']:.2f}"],
            ]

        table = Table(data, colWidths=[130, 80, 80, 100, 100, 100, 100, 120])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("SPAN", (0, 2), (-5, 2)),
            ("SPAN", (0, 3), (-5, 3)),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 15))

    # ========= Summary Check =========
    var_kwh = total_consumption - check_consumption
    var_pct_kwh = var_kwh / check_consumption if check_consumption != 0 else 0
    # ⚠️ Revenue 要加 Loss Cost
    var_cost = (total_cost_incl + loss_cost_incl) - check_cost_incl
    var_pct_cost = var_cost / check_cost_incl if check_cost_incl != 0 else 0

    elements.append(Paragraph("<b>Summary Check (Revenue vs Grid Costs)</b>", styles["Normal"]))
    elements.append(Spacer(1, 8))

    summary_data1 = [
        ["Embedded Network Sum (kWh)", "Grid Costs (MDB) (kWh)", "Var (kWh)", "Var % (kWh)"],
        [f"{total_consumption:,.0f}", f"{check_consumption:,.0f}", f"{var_kwh:,.0f}", f"{var_pct_kwh:.3%}"],
    ]
    summary_data2 = [
        ["Embedded Network Revenue incl GST ($)", "Grid Costs (MDB) incl GST ($)", "Var ($)", "Var % ($)"],
        [f"{total_cost_incl + loss_cost_incl:,.2f}", f"{check_cost_incl:,.2f}", f"{var_cost:,.2f}", f"{var_pct_cost:.3%}"],
    ]

    table1 = Table(summary_data1, colWidths=[220, 220, 120, 120])
    table1.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    table2 = Table(summary_data2, colWidths=[220, 220, 120, 120])
    table2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    elements.append(table1)
    elements.append(Spacer(1, 20))
    elements.append(table2)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"<font size=8>Note: Embedded Network Revenue includes all Shops, Common, plus All Meter Loss Cost (${loss_cost_excl:.2f} excl GST, {loss_cost_incl:.2f} incl GST)</font>",
        styles["Normal"]
    ))

    doc.build(elements)
    print(f"✅ 报告已生成: {output_pdf}")


# ============ 使用 ============
generate_summary_report(
    results_file=_BASE_DIR / "cleaned_30min.xlsx",
    mapping_file=_BASE_DIR / "C&E Report (Tariff after July).xlsx",
    output_pdf="Tenants_Summary_Report_Latest.pdf",
)







