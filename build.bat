@echo off
chcp 65001 >nul
title dangnagui build
echo.
echo =========================================
echo   dangnagui build system
echo =========================================
echo.

echo [1/5] Installing dependencies...
pip install -q pyperclip duckduckgo-search lxml pyinstaller
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
echo       Done

echo [2/5] Cleaning previous build...
if exist "dist\dangnagui" rmdir /s /q "dist\dangnagui"
if exist "build" rmdir /s /q "build"
if exist "dangnagui.spec" del /q "dangnagui.spec"
if exist "__pycache__" rmdir /s /q "__pycache__"
echo       Done

echo [3/5] Building dangnagui.exe with PyInstaller...
pyinstaller --name dangnagui --onedir --noconsole --noconfirm --clean --icon "dangnagui.ico" --add-data "common.py;." --add-data "app_settings.py;." --add-data "report_engine.py;." --add-data "dangnagui.ico;." --hidden-import pyperclip --hidden-import duckduckgo_search --hidden-import lxml --hidden-import lxml.etree main.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)
echo       Done

echo [4/5] Setting up distribution folder...
if exist "readme.txt" copy /y "readme.txt" "dist\dangnagui\readme.txt" >nul
if exist "sites_config.json" copy /y "sites_config.json" "dist\dangnagui\sites_config.json" >nul
if exist "dangnagui.ico" copy /y "dangnagui.ico" "dist\dangnagui\dangnagui.ico" >nul
for %%f in (*.md) do copy /y "%%f" "dist\dangnagui\%%f" >nul
if not exist "dist\dangnagui\IMoutput" mkdir "dist\dangnagui\IMoutput"
if not exist "dist\dangnagui\logs" mkdir "dist\dangnagui\logs"
if exist "dist\dangnagui\.instance.lock" del /q "dist\dangnagui\.instance.lock"
echo       Done

echo [5/5] Checking for Inno Setup...
set ISCC_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH (
    echo       Inno Setup found! Creating installer...
    "%ISCC_PATH%" dangnagui.iss
    if errorlevel 1 (
        echo       [WARN] Installer creation failed.
    ) else (
        echo       Installer: Output\dangnagui_setup.exe
    )
) else (
    echo       [INFO] Inno Setup not found.
    echo              Install from https://jrsoftware.org/isinfo.php
    echo              Or distribute the dist\dangnagui folder as ZIP.
)

echo.
echo =========================================
echo   Build complete!
echo   EXE: dist\dangnagui\dangnagui.exe
echo =========================================
echo.
pause
