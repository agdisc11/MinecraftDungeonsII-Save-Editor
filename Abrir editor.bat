@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul && (python editor_mcd2.py) || (py editor_mcd2.py)
pause
