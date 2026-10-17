"""
src/export_full_excel.py
Generates the complete, full-scale Excel rate deliverable containing all 857,206
curated PPO rates in a single streaming Excel worksheet using openpyxl write_only mode.
"""
import csv
import gc
import os
import time
from pathlib import Path
import openpyxl

def generate_full_excel(
    input_csv_path: str = "outputs/c6_curated_ppo_rates.csv",
    output_excel_path: str = "submission/full_curated_ppo_rates.xlsx",
) -> int:
    t0 = time.time()
    in_path = Path(input_csv_path)
    out_path = Path(output_excel_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Streaming {in_path} to {out_path} using openpyxl write_only mode...")
    
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Full Curated PPO Rates")
    
    headers = [
        "NPI",
        "NPI Type",
        "TIN",
        "Provider Name",
        "Facility / Location",
        "Address Line 1",
        "Address Line 2",
        "City",
        "State",
        "ZIP",
        "Address Status",
        "Specialty",
        "Billing Code",
        "Modifier",
        "Billing Class",
        "Setting",
        "Negotiated Rate ($)",
        "Rate Flag",
        "PPO Status",
    ]
    ws.append(headers)
    
    row_count = 0
    with open(in_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row_count += 1
            rate_val = float(r["negotiated_rate"]) if r["negotiated_rate"] else 0.0
            
            row = [
                str(r["npi"]),
                r["npi_type"],
                str(r["tin_value"]),
                r["provider_name"],
                r["ptd_business_name"],
                r["address_line_1"],
                r["address_line_2"],
                r["city"],
                r["state"],
                str(r["postal_code"]),
                r["address_verification_status"],
                r["specialty_description"],
                r["billing_code"],
                r["billing_code_modifier"],
                r["billing_class"],
                r["setting"],
                rate_val,
                r["rate_selection_flag"],
                r["ppo_applicability"],
            ]
            ws.append(row)
            
            if row_count % 100000 == 0:
                print(f"  Appended {row_count:,} rows in {time.time()-t0:.1f}s...")
                gc.collect()
                
    print(f"Saving workbook to {out_path} (zipping XML chunks)...")
    wb.save(out_path)
    elapsed = time.time() - t0
    sz = os.path.getsize(out_path)
    print(f"SUCCESS: Wrote {row_count:,} data rows to {out_path} ({sz:,} bytes, {sz/(1024*1024):.2f} MB) in {elapsed:.1f}s.")
    return row_count

if __name__ == "__main__":
    generate_full_excel()
