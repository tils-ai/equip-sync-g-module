@echo off
pip install -r requirements.txt
pyinstaller --onefile --windowed ^
    --hidden-import=win32print ^
    --hidden-import=win32ui ^
    --hidden-import=win32api ^
    --collect-all customtkinter ^
    --collect-all reportlab ^
    --collect-all qrcode ^
    --collect-submodules gui ^
    --add-data ".source;.source" ^
    --add-data "assets/fonts;assets/fonts" ^
    --name gtx4-manager ^
    main.py
echo.
echo 빌드 완료: dist\gtx4-manager.exe
pause
