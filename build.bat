@echo off
REM ============================================================
REM  Construit Capri.exe puis l'installateur CapriSetup.exe
REM  Prerequis : Python 3.12, Inno Setup 6, .NET SDK 8 (pour le HUD)
REM ============================================================
cd /d "%~dp0"

echo [1/5] Environnement virtuel...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/5] Dependances...
python -m pip install --upgrade pip
pip install -r requirements-build.txt || goto :erreur

echo [3/5] Construction de Capri.exe...
pyinstaller --noconfirm Capri.spec || goto :erreur

echo [4/5] Construction du HUD CapriDesktop (C#)...
where dotnet >nul 2>nul
if errorlevel 1 (
  echo .NET SDK 8 introuvable : HUD ignore. Installe-le depuis https://dotnet.microsoft.com/download/dotnet/8.0
) else (
  dotnet publish CapriDesktop\CapriDesktop.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o dist\CapriDesktop || goto :erreur
)

echo [5/5] Construction de l'installateur...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup introuvable : installe-le depuis https://jrsoftware.org/isdl.php
  echo Capri.exe est quand meme pret dans dist\Capri\
  goto :fin
)
%ISCC% installer\Capri.iss || goto :erreur

echo.
echo Termine ! Installateur : installer\Output\CapriSetup.exe
goto :fin

:erreur
echo.
echo *** ERREUR pendant la construction, voir les messages ci-dessus ***

:fin
pause
