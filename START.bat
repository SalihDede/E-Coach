@echo off
echo BTK Hackaton - Environment Setup
echo =================================

echo AI_Agent environment kontrol ediliyor...
call conda info --envs | findstr "AI_Agent" >nul 2>&1
if %errorlevel% == 0 (
    echo AI_Agent environment zaten mevcut, atlanıyor...
) else (
    echo AI_Agent environment kuruluyor...
    call conda create -n AI_Agent python=3.11.13 -y
    if %errorlevel% neq 0 (
        echo HATA: Conda environment olusturulamadi!
        pause
        exit /b 1
    )
)

echo AI_Agent environment aktif ediliyor...
call conda activate AI_Agent
if %errorlevel% neq 0 (
    echo HATA: Environment aktif edilemedi!
    pause
    exit /b 1
)

echo.
echo Keyboard Mouse requirements yukleniyor...
pip install -r Keyboard_Mouse_Processing/requirementsMouseKybrd.txt
echo.
echo Klavye Mouse Tamamlandi! 
echo N tusuna basin devam etmek icin...
pause

echo.
echo Voice requirements yukleniyor...
pip install -r SpeeachNLP/requirementsVoice.txt
echo.
echo Voice islemi tamamlandi!
echo N ile devam edin...
pause

echo.
echo Ana requirements yukleniyor...
pip install -r requirements.txt
echo.
echo Tamamlandi!
echo ESC tusuna basin bitirmek icin...
pause

echo.
echo =================================
echo Vision environment kontrol ediliyor...
call conda info --envs | findstr "vision_conda" >nul 2>&1
if %errorlevel% == 0 (
    echo vision_conda environment zaten mevcut, atlanıyor...
) else (
    echo Vision environment kuruluyor...
    call conda create -n vision_conda python=3.8.20 -y
    if %errorlevel% neq 0 (
        echo HATA: Vision conda environment olusturulamadi!
        pause
        exit /b 1
    )
)

echo vision_conda environment aktif ediliyor...
call conda activate vision_conda
if %errorlevel% neq 0 (
    echo HATA: Vision environment aktif edilemedi!
    pause
    exit /b 1
)

echo.
echo OpenMP cakismasi icin environment variable ayarlaniyor...
call conda env config vars set KMP_DUPLICATE_LIB_OK=TRUE -n vision_conda

echo.
echo CMake ve dlib icin gerekli paketler kuruluyor...
echo Bu islem uzun surebilir, lutfen bekleyin...
call conda install -c conda-forge cmake -y
call conda install -c conda-forge dlib -y

echo.
echo Mediapipe ve diger vision kutuphaneleri kuruluyor...
pip install mediapipe opencv-python

echo.
echo Vision requirements yukleniyor...
pip install -r Vision_Process/requirementsVision.txt
echo.
echo Tamamlandi!
echo ESC ile bitirin...
pause

echo.
echo Tum kurulumlar tamamlandi!
pause