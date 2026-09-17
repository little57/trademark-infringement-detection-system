# -*- coding: utf-8 -*-
"""
浏览器可用性自检工具
被 start.bat 调用：启动前确认 系统Edge / 内置Chromium 至少有一个能真正跑起来。
输出（stdout 单行）：
    msedge    -> 系统 Edge 可用（优先）
    chromium  -> 内置 Chromium 可用
    none      -> 都不可用，需要执行 playwright install chromium
"""
import os
import sys


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("none")
        return

    with sync_playwright() as p:
        # 1) 系统 Edge（Windows 上的首选，无需下载）
        if os.name == "nt":
            try:
                b = p.chromium.launch(headless=True, channel="msedge", timeout=20000)
                b.close()
                print("msedge")
                return
            except Exception:
                pass

        # 2) 编译内置 Chromium
        try:
            b = p.chromium.launch(headless=True, args=["--no-sandbox"], timeout=20000)
            b.close()
            print("chromium")
            return
        except Exception:
            pass

    print("none")


if __name__ == "__main__":
    main()
