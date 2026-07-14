@echo off
title CUC 侵权商品检测系统

cd /d "%~dp0"

echo ==============================
echo CUC 侵权商品检测系统
echo ==============================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    pause
    exit /b 1
)
echo [OK] Python:
python --version

echo.
echo [安装] 检查依赖...
pip install playwright openpyxl requests -q
echo.
echo [信息] AI验证模块已集成 DeepSeek API
echo   - 混合模式：规则判定 + AI增强
echo   - 支持检测完成后批量AI深度验证
echo   - 配置文件: backend\config.py


python -c "from playwright.sync_api import sync_playwright; print(1)" >nul 2>&1
if errorlevel 1 (
    echo [安装] 首次运行，安装浏览器...
    python -m playwright install chromium
)

echo.
echo [启动] 正在启动GUI界面...
echo.
echo   - 报告目录: data\reports\
echo   - 截图目录: data\screenshots\
echo   - 双击商品可打开淘宝链接
echo.
python main.py

pause
