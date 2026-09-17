@echo off
chcp 65001 >nul
title CUC 侵权商品检测系统

cd /d "%~dp0"

echo ==============================
echo CUC 侵权商品检测系统
echo ==============================
echo.

rem ========== 定位 Python（必须使用 conda 环境 pyExcel）==========
rem 说明：不同 playwright 版本要求的 chromium 版本号不同（1.60->1223, 1.61->1228），
rem       混用环境会导致“浏览器不存在”报错，因此这里禁止回退到 base/系统 Python。
rem
rem 查找顺序（按通用性排列，不依赖任何个人机器路径）：
rem   1) %CONDA_PREFIX% 同级的 envs\pyExcel            （在已激活的 conda 环境里启动时最快）
rem   2) conda run -n pyExcel 动态询问                  （装了 conda 即可用）
rem   3) %CONDA_ROOT%\envs\pyExcel                    （conda 安装目录）
rem   4) 常见 Anaconda/Miniconda 安装位置的 envs\pyExcel （兜底）
set "PYTHON_EXE="

rem 1) 当前已激活 conda 环境 -> 同级 envs 下找 pyExcel
if defined CONDA_PREFIX (
    for %%e in ("%CONDA_PREFIX%\..\envs\pyExcel\python.exe") do (
        if exist "%%~fe" (
            set "PYTHON_EXE=%%~fe"
            goto :found
        )
    )
)

rem 2) 通过 conda 动态定位 pyExcel（最通用）
where conda >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('conda run -n pyExcel python -c "import sys;print(sys.executable)" 2^>nul') do (
        if exist "%%i" (
            set "PYTHON_EXE=%%i"
            goto :found
        )
    )
)

rem 3) %CONDA_ROOT%（部分版本提供）
if defined CONDA_ROOT (
    if exist "%CONDA_ROOT%\envs\pyExcel\python.exe" (
        set "PYTHON_EXE=%CONDA_ROOT%\envs\pyExcel\python.exe"
        goto :found
    )
)

rem 4) 兜底：扫描常见 conda 安装位置
for %%d in (
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\Anaconda3"
    "%LOCALAPPDATA%\Continuum\anaconda3"
    "C:\ProgramData\anaconda3"
    "C:\ProgramData\miniconda3"
    "C:\anaconda3"
    "C:\miniconda3"
    "D:\anaconda3"
    "D:\miniconda3"
    "E:\anaconda3"
    "E:\miniconda3"
) do (
    if exist "%%~d\envs\pyExcel\python.exe" (
        set "PYTHON_EXE=%%~d\envs\pyExcel\python.exe"
        goto :found
    )
)

rem 5) 都没找到 -> 明确报错，不再静默回退（否则会用 base 环境报出难懂的浏览器错误）
echo.
echo [错误] 未找到 conda 环境 pyExcel
echo.
echo   本项目必须运行在 pyExcel 环境下，原因：
echo     - pyExcel 的 playwright 为 1.60.0，对应 chromium-1223
echo     - base/系统 Python 的 playwright 版本不同，要求的 chromium 版本也不同
echo       混用会报 "Executable doesn't exist ... chromium_headless_shell-xxxx"
echo.
echo   请先创建并初始化该环境（二选一）：
echo.
echo   [方式A] 用 conda 命令（推荐）
echo     conda create -n pyExcel python=3.9 -y
echo     conda run -n pyExcel pip install playwright openpyxl requests
echo     set PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers
echo     conda run -n pyExcel python -m playwright install chromium
echo.
echo   [方式B] 已有 pyExcel 环境，但不在常见路径
echo     请编辑本文件 start.bat，在 "查找顺序" 的第 4 步里
echo     加入你的 python.exe 所在目录，或直接把 PYTHON_EXE 写死为该路径。
echo.
pause
exit /b 1

:found
echo [环境] 使用 conda 环境: pyExcel
"%PYTHON_EXE%" --version

echo.
echo [安装] 检查依赖...
"%PYTHON_EXE%" -m pip install playwright openpyxl requests -q
echo.
echo [信息] AI验证模块已集成 DeepSeek API
echo   - 混合模式：规则判定 + AI增强
echo   - 支持检测完成后批量AI深度验证
echo   - 配置文件: backend\config.py

rem 浏览器统一装到项目目录内，避免依赖全局缓存
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"

rem 检查浏览器是否真的可启动：系统 Edge 或 内置 Chromium 任一可用即可
set "BROWSER_OK="
for /f "delims=" %%i in ('"%PYTHON_EXE%" check_env.py 2^>nul') do set "BROWSER_OK=%%i"

if /i "%BROWSER_OK%"=="none" (
    echo [安装] 未检测到可用浏览器，正在安装内置 Chromium（约180MB，仅需一次）...
    "%PYTHON_EXE%" -m playwright install chromium
) else (
    echo [浏览器] 可用: %BROWSER_OK%
)

echo.
echo [启动] 正在启动GUI界面...
echo.
echo   - 报告目录: data\reports\
echo   - 截图目录: data\screenshots\
echo   - 双击商品可打开淘宝链接
echo.
"%PYTHON_EXE%" main.py

pause
