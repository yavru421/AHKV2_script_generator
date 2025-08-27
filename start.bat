@echo off
set LOGFILE=runlog.txt
echo ==== START: %DATE% %TIME% ==== > %LOGFILE%

echo [STEP] Activating venv... >> %LOGFILE%
call .venv\Scripts\activate.bat >> %LOGFILE% 2>&1

echo [STEP] Installing requirements... >> %LOGFILE%
pip install -r requirements.txt >> %LOGFILE% 2>&1

echo [STEP] Launching main app... >> %LOGFILE%
python AHK-Python-FullApp.py >> %LOGFILE% 2>&1

echo ==== END: %DATE% %TIME% ==== >> %LOGFILE%
