@echo off
echo BTK Hackaton - Backend Calistirici
echo ===================================

echo Mouse/Keyboard modulu baslatiliyor (Sol Ust)...
start "Mouse_Keyboard_Process" /D "%CD%" cmd /k "mode con: cols=80 lines=25 && title Mouse_Keyboard_Process && conda activate AI_Agent && cd Keyboard_Mouse_Processing && python mouse_keyboard3.py"

timeout /t 2 /nobreak >nul

echo Voice Comparison modulu baslatiliyor (Sag Ust)...
start "Voice_Comparison_Process" /D "%CD%" cmd /k "mode con: cols=80 lines=25 && title Voice_Comparison_Process && conda activate AI_Agent && cd SpeeachNLP && python optimized_voice_comparison.py"

timeout /t 2 /nobreak >nul

echo Unified Voice App baslatiliyor (Sol Alt)...
start "Unified_Voice_Process" /D "%CD%" cmd /k "mode con: cols=80 lines=25 && title Unified_Voice_Process && conda activate AI_Agent && cd SpeeachNLP && python unified_voice_app.py"

timeout /t 2 /nobreak >nul

echo Webcam Vision modulu baslatiliyor (Sag Alt)...
echo Vision modulu yukleniyor, lutfen bekleyin...
start "Vision_Webcam_Process" /D "%CD%" cmd /k "mode con: cols=80 lines=25 && title Vision_Webcam_Process && set KMP_DUPLICATE_LIB_OK=TRUE && conda activate vision_conda && cd Vision_Process && python run_with_webcam.py"

echo Vision modulu icin ek yukleme suresi bekleniyor...
timeout /t 10 /nobreak >nul

echo.
echo =================================
echo Tum backend moduller ayri processlerde baslatildi!
echo 4 ayri pencere acildi:
echo - Mouse_Keyboard_Process
echo - Voice_Comparison_Process  
echo - Unified_Voice_Process
echo - Vision_Webcam_Process
echo =================================
echo Her proces bagimsiz olarak calisiyor.
echo Kapatmak icin ilgili pencereleri kapatin.
echo =================================
pause