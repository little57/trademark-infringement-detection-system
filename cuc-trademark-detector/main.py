# -*- coding: utf-8 -*-
"""
中国传媒大学 侵权商品检测系统 - 启动入口
带加载进度窗口，替代黑框等待
"""
import sys, os, traceback, threading, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(str(BASE))
sys.path.insert(0, str(BASE))

LOG = BASE / "error.log"

# ========== 加载进度窗口 ==========
try:
    import tkinter as tk
    from tkinter import ttk

    splash = tk.Tk()
    splash.title("加载中...")
    splash.geometry("420x180+500+300")
    splash.configure(bg="#1a3a5c")
    splash.resizable(False, False)

    # 标题
    tk.Label(
        splash, text="CUC 侵权商品检测系统",
        font=("微软雅黑", 16, "bold"), bg="#1a3a5c", fg="white"
    ).pack(pady=(30, 5))

    # 进度条
    progress = ttk.Progressbar(splash, length=320, mode="indeterminate")
    progress.pack(pady=10)
    progress.start(10)

    # 状态文字
    status_var = tk.StringVar(value="正在初始化...")
    tk.Label(
        splash, textvariable=status_var,
        font=("微软雅黑", 9), bg="#1a3a5c", fg="#b0c4de"
    ).pack(pady=5)

    splash.update()

    def update_status(msg):
        status_var.set(msg)
        splash.update()

    # 在后台线程中加载主程序
    load_ok = [True]
    exc_info = [None]
    app_holder = [None]  # 加载完成后存放 App 类

    def _load_main():
        try:
            update_status("正在加载依赖模块...")
            from backend.gui import App
            update_status("正在启动主界面...")
            # 注意：这里不能把 App().run() 交给 splash.after 回调去执行。
            # splash 一旦 destroy，其 after 回调链随之失效，主界面永远起不来，
            # 进程会直接结束（表现为窗口一闪而过/无反应）。
            # 正确做法：只做导入，主循环交由 splash.mainloop() 结束后在主线程启动。
            app_holder[0] = App
            splash.after(0, splash.quit)
        except Exception as e:
            load_ok[0] = False
            exc_info[0] = (e, traceback.format_exc())
            splash.after(0, splash.quit)

    def _start_app(App):
        """在主线程中启动主界面（必须在 splash.mainloop() 之后调用）"""
        try:
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
            input("\nPress Enter to exit...")

    threading.Thread(target=_load_main, daemon=True).start()
    splash.mainloop()

    # splash 已退出：若加载成功，销毁加载窗并在主线程启动主界面
    try:
        splash.destroy()
    except Exception:
        pass

    if load_ok[0] and app_holder[0] is not None:
        _start_app(app_holder[0])
        sys.exit(0)

    # 如果加载失败，回退到黑框模式
    if not load_ok[0]:
        e, detail = exc_info[0]
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("Error: " + str(e) + "\n")
            f.write(detail)
        print("=" * 40)
        print("ERROR: " + str(e))
        print("=" * 40)
        print(detail)
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

except Exception as e:
    # 如果连加载窗口都打不开（比如无GUI环境），回退到原始黑框模式
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("Splash Error: " + str(e) + "\n")
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
