@echo off
rem Double-click this file to open the sleep dashboard in your browser.
rem Keep this window open while you use the dashboard; close it to stop.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m streamlit run app.py
pause
