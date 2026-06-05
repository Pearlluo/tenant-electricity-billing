import os
import shutil
from PyPDF2 import PdfMerger
from pathlib import Path

# ================== 路径设置 ==================
base_dir = Path(__file__).parent.parent
cover_dir = base_dir / "CoverPages"
report_dir = base_dir / "MeterReports"
summary_file = base_dir / "Coding" / "Tenants_Summary_Report_Latest.pdf"
output_dir = base_dir / "FinalReports"

os.makedirs(output_dir, exist_ok=True)

# ================== 遍历 Cover 文件 ==================
for file in os.listdir(cover_dir):
    if not file.endswith("_Cover.pdf"):
        continue

    meter = file.replace("_Cover.pdf", "")  # e.g. SHOP1
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

    print(f"✅ 已合并: {output_path}")

# ================== 删除输入目录和文件 ==================
try:
    if os.path.exists(cover_dir):
        shutil.rmtree(cover_dir)   # 删除整个 CoverPages 文件夹
    if os.path.exists(report_dir):
        shutil.rmtree(report_dir)  # 删除整个 MeterReports 文件夹
    if os.path.exists(summary_file):
        os.remove(summary_file)    # 删除 summary 文件
    print("🗑️ 已清理所有输入文件，只保留 FinalReports")
except Exception as e:
    print(f"⚠️ 删除时出错: {e}")

