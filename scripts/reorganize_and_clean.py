"""
InsightOS Full Project Cleanup and Restructuring Script.
Reorganizes files into the standard InsightOS structure:
InsightOS/
├── app/
│   ├── main.py
│   ├── api/
│   ├── services/
│   ├── core/
│   ├── modules/
│   └── ml_models/
├── frontend/
├── live_data/
├── models/
├── scripts/
├── tests/
├── .env
├── requirements.txt
└── README.md
"""

import os
import shutil
import glob

def clean_and_reorganize():
    root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    print(f"Cleaning and restructuring InsightOS at: {root}")

    # 1. Accidental / Corrupt Directories
    corrupt_dirs = [
        "d\uf03apooectfrontend-next",
        "d\uf03apoojectdocssuperpowersplans",
        "d\uf03apoojectdocssuperpowersspecs",
        "d:pooectfrontend-next",
        "d:poojectdocssuperpowersplans",
        "d:poojectdocssuperpowersspecs",
        "spa",
        "sp"
    ]
    for d in corrupt_dirs:
        p = os.path.join(root, d)
        if os.path.exists(p):
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                print(f"  [REMOVED] Corrupt dir/file: {d.encode('ascii', 'replace').decode('ascii')}")
            except Exception as e:
                print(f"  [ERROR] Removing {d.encode('ascii', 'replace').decode('ascii')}: {e}")

    # 2. Junk text/log and temp files
    junk_files = [
        "deep_test_output.txt",
        "deep_test_results.txt",
        "engine_log.txt",
        "pdf_extracted.txt",
        "qubrid_resp.txt",
        "server_output.txt",
        "extract_pdf.js",
        "inject_anomalies (1).py",
        "catch_500.py",
        "debug_complex_query.py",
        "debug_imports.py",
        "sp"
    ]
    for f in junk_files:
        p = os.path.join(root, f)
        if os.path.exists(p):
            try:
                os.remove(p)
                print(f"  [REMOVED] Temp/Junk file: {f}")
            except Exception as e:
                print(f"  [ERROR] Removing {f}: {e}")

    # 3. Move root test files to tests/
    test_files = [
        "test_api_features.py",
        "test_dashboards.py",
        "test_deep_analysis.py",
        "test_features.py",
        "test_sentinel.py",
        "test_slack.py",
        "test_tally_verification.py",
        "test_pydantic.py"
    ]
    tests_dir = os.path.join(root, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    for tf in test_files:
        src = os.path.join(root, tf)
        if os.path.exists(src):
            dst = os.path.join(tests_dir, tf)
            shutil.move(src, dst)
            print(f"  [MOVED] {tf} -> tests/{tf}")

    # 4. Move root utility scripts to scripts/
    script_files = [
        "benchmark_speed.py",
        "build_retail_db.py",
        "get_actual_schema.py",
        "init_dashboard_db.py",
        "merge_db.py",
        "run_alerts_engine.py",
        "run_sql.py",
        "sample_data.py",
        "update_dates.py"
    ]
    scripts_dir = os.path.join(root, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    for sf in script_files:
        src = os.path.join(root, sf)
        if os.path.exists(src):
            dst = os.path.join(scripts_dir, sf)
            shutil.move(src, dst)
            print(f"  [MOVED] {sf} -> scripts/{sf}")

    # 5. Ensure models/ directory exists
    models_dir = os.path.join(root, "models")
    os.makedirs(models_dir, exist_ok=True)

    print("\n[SUCCESS] Cleanup and restructuring completed successfully.")

if __name__ == "__main__":
    clean_and_reorganize()
