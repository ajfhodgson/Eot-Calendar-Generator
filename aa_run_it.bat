if exist "C:\Users\andre\source\repos\EoT Calendar Generator" (
    cd "C:\Users\andre\source\repos\EoT Calendar Generator"
) else (
    cd "C:\Users\andre\repos\EoT Calendar Generator"
)
call .venv\Scripts\activate.bat
python EoT-Calendar-Generator.py
pause
