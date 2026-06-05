import os
import shutil
from PyPDF2 import PdfMerger
from pathlib import Path

# ================== Path setup ==================
base_dir = Path(__file__).parent.parent
cover_dir = base_dir / "CoverPages"
report_dir = base_dir / "MeterReports"
summary_file = base_dir / "Coding" / "Tenants_Summary_Report_Latest.pdf"
output_dir = base_dir / "FinalReports"

os.makedirs(output_dir, exist_ok=True)

# ================== Merge PDFs for each meter ==================
for file in os.listdir(cover_dir):
    if not file.endswith("_Cover.pdf"):
        continue

    meter = file.replace("_Cover.pdf", "")
    cover_path = os.path.join(cover_dir, file)
    report_path = os.path.join(report_dir, f"{meter}_Report.pdf")
    output_path = os.path.join(output_dir, f"{meter}_Final.pdf")

    merger = PdfMerger()
    merger.append(cover_path)

    if os.path.exists(report_path):
        merger.append(report_path)

    if meter == "MDB" and os.path.exists(summary_file):
        merger.append(summary_file)

    merger.write(output_path)
    merger.close()

    print(f"Done: {output_path}")

# ================== Clean up intermediate files ==================
try:
    if os.path.exists(cover_dir):
        shutil.rmtree(cover_dir)
    if os.path.exists(report_dir):
        shutil.rmtree(report_dir)
    if os.path.exists(summary_file):
        os.remove(summary_file)
    print("Cleanup complete. Only FinalReports retained.")
except Exception as e:
    print(f"Cleanup error: {e}")
