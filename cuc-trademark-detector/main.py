# -*- coding: utf-8 -*-
import sys, os, traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(str(BASE))
sys.path.insert(0, str(BASE))

LOG = BASE / "error.log"

try:
    from backend.gui import App
    App().run()
except Exception as e:
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("Error: " + str(e) + "\n")
        f.write(traceback.format_exc())
    print("=" * 40)
    print("ERROR: " + str(e))
    print("=" * 40)
    print(traceback.format_exc())
    print("\nError saved to: " + str(LOG))
    try:
        from backend.detector import Detector
        det = Detector(progress_cb=lambda msg: print("  " + msg))
        result = det.run()
        if len(result) == 5:
            results, inf_cnt, book_cnt, total_scanned, excel_path = result
        elif len(result) == 4:
            results, inf_cnt, book_cnt, excel_path = result
        else:
            results, inf_cnt, book_cnt = result[:3]
            excel_path = ""
        print("\nDone: " + str(len(results)) + " items collected")
        print("Excel: " + (excel_path or str(BASE / "cuc-taobao.xlsx")))
    except Exception as e2:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("CLI Error: " + str(e2) + "\n")
            f.write(traceback.format_exc())
        print("\nCLI Error: " + str(e2))
    input("\nPress Enter to exit...")
