import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ========== Configuration ==========
excel_file = BASE_DIR / "Results.xlsx"
output_pdf = "Tenants_Summary_Report.pdf"

RATE = 0.381783
DAILY_CHARGE = 1.87964
GST_RATE = 0.1  # 10%

# ========== Load Excel ==========
df = pd.read_excel(excel_file)

# Group by meter
summary = []
for meter, group in df.groupby("Meter"):
    prev = group.iloc[0]["kWh_IMP"]
    curr = group.iloc[-1]["kWh_IMP"]
    consumption = curr - prev

    start_date = pd.to_datetime(group.iloc[0]["DateTime"])
    end_date = pd.to_datetime(group.iloc[-1]["DateTime"])
    days = (end_date - start_date).days

    # ========== Rule 1: Common meter has no daily charge ==========
    if meter.lower() == "common":
        daily_total = 0
    else:
        daily_total = days * DAILY_CHARGE

    consumption_total = consumption * RATE
    excl_gst = daily_total + consumption_total

    # ========== Rule 2: Zero cost if no consumption ==========
    if consumption <= 0:
        excl_gst = 0
        gst = 0
        total = 0
    else:
        gst = excl_gst * GST_RATE
        total = excl_gst + gst

    summary.append({
        "shop": meter,
        "period": f"{start_date.date()} - {end_date.date()}",
        "previous": prev,
        "current": curr,
        "consumption": consumption,
        "rate": RATE,
        "daily_charge": daily_total,
        "total_charge": excl_gst,
        "gst": gst,
        "total_inc_gst": total
    })

# ========== Generate PDF ==========
styles = getSampleStyleSheet()

doc = SimpleDocTemplate(
    output_pdf,
    pagesize=landscape(A4),
    leftMargin=40,
    rightMargin=40,
    topMargin=40,
    bottomMargin=30
)
elements = []

# Header (left aligned)
elements.append(Paragraph(
    "<para align='left'><font size=9>Prepared by YOUR_ORG_NAME<br/>YOUR_ADDRESS</font></para>",
    styles["Normal"]
))
elements.append(Spacer(1, 12))

# Title (centred)
elements.append(Paragraph(
    "<para align='center'><b><font size=14>Tenants Summary Report</font></b></para>",
    styles["Normal"]
))
elements.append(Spacer(1, 18))

# Table for each shop
for s in summary:
    elements.append(Paragraph(
        f"<para align='left'><font size=9><b>{s['shop']}</b></font></para>",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 4))

    data = [
        ["Date", "Previous Reading (kWh)", "Current Reading (kWh)",
         "Consumption (kWh)", "Rate", "Daily Charge", "Total Charge"],
        [s["period"], f"{s['previous']:.3f}", f"{s['current']:.3f}",
         f"{s['consumption']:.3f}", f"{s['rate']:.6f}", f"{s['daily_charge']:.5f}", f"{s['total_charge']:.2f}"],
        ["", "", "", "", "", "GST (10%)", f"{s['gst']:.2f}"],
        ["", "", "", "", "", "TOTAL inc GST", f"{s['total_inc_gst']:.2f}"],
    ]

    table = Table(data, colWidths=[160, 110, 110, 110, 80, 100, 120])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('SPAN', (0, 2), (-3, 2)),
        ('SPAN', (0, 3), (-3, 3)),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

doc.build(elements)
print(f"Report generated: {output_pdf}")

