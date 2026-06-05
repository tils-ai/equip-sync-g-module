@echo off
pip install -r requirements.txt
REM 가명 자산(vendor/) → 임시 .source/ 로 복원 (원본 이름 매핑은 vendor\.dll_manifest, 미추적)
python scripts\restore_vendor.py || exit /b 1
pyinstaller --onefile --windowed ^
    --hidden-import=win32print ^
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
