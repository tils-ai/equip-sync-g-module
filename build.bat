@echo off
pip install -r requirements.txt
python scripts\restore_vendor.py || exit /b 1
pyinstaller --onefile --windowed ^
    --hidden-import=win32print ^
    --hidden-import=win32timezone ^
    --hidden-import=win32ui ^
    --hidden-import=win32api ^
    --hidden-import=device_status ^
    --collect-all customtkinter ^
    --collect-all reportlab ^
    --collect-all qrcode ^
    --collect-submodules gui ^
    --add-data ".source;.source" ^
    --add-data "assets/fonts;assets/fonts" ^
    --name equip-sync-g ^
    main.py
echo.
echo 빌드 완료: dist\equip-sync-g.exe
pause
