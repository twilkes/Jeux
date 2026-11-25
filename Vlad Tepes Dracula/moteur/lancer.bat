@echo off
rem Lance le prototype directement depuis l image CD (musique incluse)
cd /d "%~dp0"
python -m vlad "..\jeu-00936-dracula_guerrier_carpates-pcwin\Dracula.bin" %*
if errorlevel 1 pause
