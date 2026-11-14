@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: ==========================================================================
:: MIDNIGHT CLUB 3: DUB EDITION - ULTIMATE MUSIC TOOLS
:: 108S candidate: Retail 108Q workflow + verified VIP v4 ISO builder.
:: ==========================================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Start a new interactive session with console output mirrored into support_logs.
if not defined MC3_LOG_ACTIVE (
    if exist "%SCRIPT_DIR%supporting_tools\session_logger.py" (
        where python.exe >nul 2>&1
        if not errorlevel 1 (
            python "%SCRIPT_DIR%supporting_tools\session_logger.py" "%~f0"
            exit /b %errorlevel%
        )
        where py.exe >nul 2>&1
        if not errorlevel 1 (
            py -3 "%SCRIPT_DIR%supporting_tools\session_logger.py" "%~f0"
            exit /b %errorlevel%
        )
    )
    echo [WARNING] Session logging unavailable: Python or session_logger.py missing.
)


:: Project files / folders
set "ORIGINAL_ISO=Midnight Club 3 - DUB Edition Remix (USA).iso"
set "TOOLS_DIR=supporting_tools"
set "EXTRACTED_ISO_DIR=ISO_FILES"
set "ASSET_FOLDER=ASSETS"
set "AUDIO_FOLDER=STREAMS"
set "CUSTOM_MUSIC=Custom Music"
set "PROFILE_FILE=%SCRIPT_DIR%ISO_FILES\MC3_PROFILE.txt"

:: Resolved executable paths (for future phases)
set "PYTHON_CMD="

 echo ===================================================
 echo   Angel Studios / Rockstar PS2
 echo   Ultimate Music Tools - Stage 2
 echo ===================================================
 echo.
 echo Project folder:
 echo "%SCRIPT_DIR%"
 echo.

call :CHECK_REQUIREMENTS
if errorlevel 1 (
    echo.
    echo ===================================================
    echo Required files or tools are missing.
    echo The program cannot continue.
    echo ===================================================
    pause
    exit /b 1
)

echo.
echo ===================================================
echo All required files and tools were found.
echo ===================================================

:MAIN_MENU
echo.
echo ===================================================
echo   Ultimate Music Tools - Main Menu
echo ===================================================
echo   SETUP
echo [1] Extract ISO and Decompile DAT Archives
echo.
echo   MUSIC CUSTOMIZATION
echo [2] Remove Current Gameplay Soundtrack(s)
echo [3] Update Lose and Win (also Race Transitions) Music
echo [4] Add Custom Gameplay Music and Title Theme Song
echo [5] Update Loading Screen Music
echo.
echo   BUILD
echo [6] Compile DAT Archives and Build ISO
echo.
echo [7] Exit
echo ===================================================
set "MENU_CHOICE="
set /p "MENU_CHOICE=Enter option (1-7), then press Enter: "
echo [MENU SELECTION] %MENU_CHOICE%
if "%MENU_CHOICE%"=="1" goto MENU_OPTION_1
if "%MENU_CHOICE%"=="2" goto MENU_OPTION_2
if "%MENU_CHOICE%"=="3" goto MENU_OPTION_3
if "%MENU_CHOICE%"=="4" goto MENU_OPTION_4
if "%MENU_CHOICE%"=="5" goto MENU_OPTION_5
if "%MENU_CHOICE%"=="6" goto MENU_OPTION_6
if "%MENU_CHOICE%"=="7" goto MENU_EXIT
echo [ERROR] Invalid selection. Enter 1, 2, 3, 4, 5, 6, or 7.
goto MAIN_MENU

:MENU_OPTION_1
call :PREPARE_GAME
goto MAIN_MENU

:MENU_OPTION_2
call :CHECK_WORKSPACE_LIGHT
if errorlevel 1 goto MAIN_MENU
call :SOUNDTRACK_MENU
goto MAIN_MENU

:MENU_OPTION_3
call :CHECK_WORKSPACE_LIGHT
if errorlevel 1 goto MAIN_MENU
call :SYNC_WINLOSE_FOLDERS
goto MAIN_MENU

:MENU_OPTION_4
call :CHECK_WORKSPACE_LIGHT
if errorlevel 1 goto MAIN_MENU
call :ADD_CUSTOM_GAMEPLAY_MUSIC
goto MAIN_MENU

:MENU_OPTION_5
call :CHECK_WORKSPACE_LIGHT
if errorlevel 1 goto MAIN_MENU
call :CUSTOMIZE_LOADING_SCREENS
goto MAIN_MENU

:MENU_OPTION_6
call :REQUIRE_PROFILE
if errorlevel 1 goto MAIN_MENU
call :COMPILE_AND_BUILD
goto MAIN_MENU

:MENU_EXIT
exit /b 0


:: Lightweight profile check for music customization; full validation remains for build.
:CHECK_WORKSPACE_LIGHT
if not exist "%PROFILE_FILE%" (
    echo [ERROR] Missing ISO_FILES\MC3_PROFILE.txt.
    echo [INFO] Run Option 1 to extract and decompile a game first.
    exit /b 1
)
set "MC3_PROFILE="
set /p "MC3_PROFILE="<"%PROFILE_FILE%"
if /i "%MC3_PROFILE%"=="retail" goto CHECK_WORKSPACE_LIGHT_FILES
if /i "%MC3_PROFILE%"=="vip" goto CHECK_WORKSPACE_LIGHT_FILES
echo [ERROR] Invalid workspace profile: %MC3_PROFILE%
exit /b 1
:CHECK_WORKSPACE_LIGHT_FILES
if not exist "%SCRIPT_DIR%ASSETS\" (
    echo [ERROR] Missing ASSETS workspace. Run Option 1 first.
    exit /b 1
)
if not exist "%SCRIPT_DIR%STREAMS\" (
    echo [ERROR] Missing STREAMS workspace. Run Option 1 first.
    exit /b 1
)
echo WORKSPACE READY: %MC3_PROFILE% (music customization)
exit /b 0

:REQUIRE_PROFILE
if not exist "%PROFILE_FILE%" (
    echo [ERROR] Missing ISO_FILES\MC3_PROFILE.txt.
    echo [INFO] Use Option 1 to create a profile-tagged workspace first.
    exit /b 1
)
set "MC3_PROFILE="
set /p "MC3_PROFILE="<"%PROFILE_FILE%"
if /i "%MC3_PROFILE%"=="retail" (
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_Profile_108S.py" validate "%SCRIPT_DIR%ISO_FILES"
    if errorlevel 1 exit /b 1
    exit /b 0
)
if /i "%MC3_PROFILE%"=="vip" (
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_Profile_108S.py" validate "%SCRIPT_DIR%ISO_FILES"
    if errorlevel 1 exit /b 1
    exit /b 0
)
echo [ERROR] Invalid workspace profile: %MC3_PROFILE%
exit /b 1

:PREPARE_GAME
echo.
echo ===================================================
echo Extract ISO and Decompile DAT Archives
echo ===================================================
set "OPTION1_OVERWRITE=0"
if exist "%SCRIPT_DIR%ISO_FILES\" set "OPTION1_OVERWRITE=1"
if exist "%SCRIPT_DIR%ASSETS\" set "OPTION1_OVERWRITE=1"
if exist "%SCRIPT_DIR%STREAMS\" set "OPTION1_OVERWRITE=1"
if "%OPTION1_OVERWRITE%"=="1" (
    echo.
    echo [WARNING] An existing game workspace was detected.
    echo Continuing will replace ISO_FILES, ASSETS, and STREAMS with files from the selected ISO.
    echo Unsaved music modifications in those folders will be lost.
    set "OPTION1_CONFIRM="
    set /p "OPTION1_CONFIRM=Overwrite the existing game workspace? (Y/N): "
    if /i not "!OPTION1_CONFIRM!"=="Y" (
        echo [CANCELLED] Existing workspace preserved.
        exit /b 0
    )
)
call :EXTRACT_ISO_NATIVE
if errorlevel 1 exit /b 1
call :DECOMPILE_DAT AUTO_OVERWRITE
exit /b %errorlevel%
:: ==========================================================================
:: LOADING SCREEN MUSIC - independent audio slot editing only.
:: Uses the already decompiled ASSETS directory; does not extract or compile.
:: ==========================================================================
:CUSTOMIZE_LOADING_SCREENS
if not exist "%SCRIPT_DIR%%ASSET_FOLDER%\audio\loadscreen\18.raw" (
    echo [ERROR] Loading-screen slots are missing from ASSETS.
    echo Extract the ISO and decompile ASSETS.DAT using menu options 1 and 2 first.
    pause
    exit /b 1
)
if not exist "%SCRIPT_DIR%%TOOLS_DIR%\customize_loading_screens.py" (
    echo [ERROR] Missing supporting_tools\customize_loading_screens.py
    pause
    exit /b 1
)
if not exist "%SCRIPT_DIR%Loading Music" mkdir "%SCRIPT_DIR%Loading Music"
call !PYTHON_CMD! "%SCRIPT_DIR%%TOOLS_DIR%\customize_loading_screens.py" "%SCRIPT_DIR%."
if errorlevel 1 (
    echo [WARNING] Loading-screen customization did not complete.
    pause
    exit /b 1
)
exit /b 0

:: ==========================================================================
:: GAMEPLAY SOUNDTRACK MANAGEMENT (separate from working music/ISO phases)
:: ==========================================================================
:SOUNDTRACK_MENU
echo.
echo ===================================================
echo   Remove Current Gameplay Soundtrack(s)
echo ===================================================
echo [1] View Current Gameplay Soundtrack
echo [2] Remove Individual Gameplay Song
echo [3] Remove All Songs from a Genre or Garage Shop
echo [4] Remove All Gameplay and Garage Shop Music
echo [5] Return to Main Menu
echo ===================================================
set "SM_CHOICE="
set /p "SM_CHOICE=Enter option (1-5), then press Enter: "
if "%SM_CHOICE%"=="5" exit /b 0
if "%SM_CHOICE%"=="1" (
    call :SOUNDTRACK_REQUIRE manager
    if errorlevel 1 goto SOUNDTRACK_MENU
    "%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\manage_gameplay_soundtrack.py" view
    pause
    goto SOUNDTRACK_MENU
)
if "%SM_CHOICE%"=="2" (
    call :SOUNDTRACK_REQUIRE manager
    if errorlevel 1 goto SOUNDTRACK_MENU
    echo.
    "%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\manage_gameplay_soundtrack.py" select-song
    if errorlevel 1 (
        echo [ERROR] Song selection failed. Review the output above.
        pause
    )
    goto SOUNDTRACK_MENU
)
if "%SM_CHOICE%"=="3" (
    call :SOUNDTRACK_REQUIRE genre
    if errorlevel 1 goto SOUNDTRACK_MENU
    echo.
    echo [1] Dancehall  [2] Drum and Bass  [3] Hip-Hop  [4] Rock  [5] Techno  [6] Garage Shop
    set "SM_GENRE_CHOICE="
    set /p "SM_GENRE_CHOICE=Select category (1-6; blank to cancel): "
    set "SM_GENRE="
    if "!SM_GENRE_CHOICE!"=="1" set "SM_GENRE=dancehall"
    if "!SM_GENRE_CHOICE!"=="2" set "SM_GENRE=drum-and-bass"
    if "!SM_GENRE_CHOICE!"=="3" set "SM_GENRE=hip-hop"
    if "!SM_GENRE_CHOICE!"=="4" set "SM_GENRE=rock"
    if "!SM_GENRE_CHOICE!"=="5" set "SM_GENRE=techno"
    if "!SM_GENRE_CHOICE!"=="6" set "SM_GENRE=garage-shop"
    if not defined SM_GENRE (
        echo [CANCELLED] No valid genre selected.
        goto SOUNDTRACK_MENU
    )
    call :SOUNDTRACK_RUN genre "!SM_GENRE!"
    goto SOUNDTRACK_MENU
)
if "%SM_CHOICE%"=="4" (
    call :SOUNDTRACK_REQUIRE manager
    if errorlevel 1 goto SOUNDTRACK_MENU
    call :SOUNDTRACK_RUN manager all
    goto SOUNDTRACK_MENU
)
echo [ERROR] Invalid selection.
goto SOUNDTRACK_MENU

:SOUNDTRACK_REQUIRE
if /i "%~1"=="manager" (
    if not exist "%SCRIPT_DIR%supporting_tools\manage_gameplay_soundtrack.py" (
        echo [ERROR] Missing supporting_tools\manage_gameplay_soundtrack.py.
        pause
        exit /b 1
    )
) else (
    if not exist "%SCRIPT_DIR%supporting_tools\manage_gameplay_genre.py" (
        echo [ERROR] Missing supporting_tools\manage_gameplay_genre.py.
        pause
        exit /b 1
    )
)
if not exist "%SCRIPT_DIR%supporting_tools\gameplay_placeholders.py" (
    echo [ERROR] Missing supporting_tools\gameplay_placeholders.py.
    pause
    exit /b 1
)
exit /b 0

:SOUNDTRACK_RUN
set "SM_SCRIPT=%SCRIPT_DIR%supporting_tools\manage_gameplay_soundtrack.py"
rem Genre and Garage Shop removal use the shared manager for consistent cleanup.
if /i "%~1"=="manager" (
    if /i "%~2"=="song" (
        echo.
        echo [PREVIEW] Individual-song removal
        "%PYTHON_CMD%" "%SM_SCRIPT%" check song "%~3"
    ) else (
        echo.
        echo [PREVIEW] Remove all gameplay and Garage Shop music
        "%PYTHON_CMD%" "%SM_SCRIPT%" check all
    )
) else (
    echo.
    echo [PREVIEW] Remove genre: %~2
    "%PYTHON_CMD%" "%SM_SCRIPT%" check genre "%~2"
)
if errorlevel 1 (
    echo [STOPPED] Preview failed. Nothing will be applied.
    pause
    exit /b 1
)
echo.
echo [WARNING] Applying will delete RSM files and modify playlists/metadata.
echo [WARNING] Back up ASSETS and STREAMS before proceeding.
set "SM_CONFIRM="
set /p "SM_CONFIRM=Type APPLY to confirm, or press Enter to cancel: "
if /i not "%SM_CONFIRM%"=="APPLY" (
    echo [CANCELLED] No changes applied.
    pause
    exit /b 0
)
if /i "%~1"=="manager" (
    if /i "%~2"=="song" (
        "%PYTHON_CMD%" "%SM_SCRIPT%" apply song "%~3"
    ) else (
        "%PYTHON_CMD%" "%SM_SCRIPT%" apply all
    )
) else (
    "%PYTHON_CMD%" "%SM_SCRIPT%" apply genre "%~2"
)
if errorlevel 1 (
    echo [ERROR] Soundtrack operation failed. Review the output above.
) else (
    echo [DONE] Soundtrack operation finished. Rebuild ISO with main menu Option 6.
)
pause
exit /b 0

:: ==========================================================================
:: PHASE 2 - ISO EXTRACTION (never changes original ISO)
:: ==========================================================================
:: PHASE 4E - BUILD BOTH ARCHIVES, NATIVE PYTHON ISO
:: ==========================================================================
:COMPILE_AND_BUILD
setlocal EnableDelayedExpansion
echo.
echo ===================================================
echo   Phase 4E - Compile DAT Archives and Build ISO
echo ===================================================
if not exist "%SCRIPT_DIR%ASSETS\" goto PHASE4E_ERROR
if not exist "%SCRIPT_DIR%STREAMS\" goto PHASE4E_ERROR
if not exist "%SCRIPT_DIR%ISO_FILES\" goto PHASE4E_ERROR
for %%T in (dave.py hash_build.py) do (
    if not exist "%SCRIPT_DIR%supporting_tools\%%T" (
        echo [ERROR] Missing supporting_tools\%%T
        goto PHASE4E_ERROR
    )
)
call :REQUIRE_PROFILE
if errorlevel 1 goto PHASE4E_ERROR
set "ISO_OUT=%SCRIPT_DIR%MC3_Modified_DUB.iso"
if /i "!MC3_PROFILE!"=="vip" set "ISO_OUT=%SCRIPT_DIR%MC3_Modified_VIP.iso"
echo [PROFILE] !MC3_PROFILE!
:: The source/output collision check below remains mandatory.
:: Resolve the VIP source and protect it BEFORE overwriting either DAT archive.
if /i "!MC3_PROFILE!"=="vip" (
    set "VIP_SOURCE="
    if not exist "%SCRIPT_DIR%ISO_FILES\MC3_SOURCE_ISO.txt" (
        echo [ERROR] Missing ISO_FILES\MC3_SOURCE_ISO.txt.
        goto PHASE4E_ERROR
    )
    for /f "usebackq delims=" %%S in ("%SCRIPT_DIR%ISO_FILES\MC3_SOURCE_ISO.txt") do set "VIP_SOURCE=%%S"
    if not defined VIP_SOURCE (
        echo [ERROR] VIP source ISO path is empty.
        goto PHASE4E_ERROR
    )
    if not exist "!VIP_SOURCE!" (
        echo [ERROR] VIP source ISO does not exist: "!VIP_SOURCE!"
        goto PHASE4E_ERROR
    )
    for %%S in ("!VIP_SOURCE!") do set "VIP_SOURCE_FULL=%%~fS"
    for %%O in ("!ISO_OUT!") do set "VIP_OUTPUT_FULL=%%~fO"
    if /i "!VIP_SOURCE_FULL!"=="!VIP_OUTPUT_FULL!" (
        echo [ERROR] Source and output ISO are the same file. Build cancelled.
        goto PHASE4E_ERROR
    )
)
:: Ask once before replacing an existing final ISO. Keep it intact until the new ISO is verified.
if exist "!ISO_OUT!" (
    echo.
    echo ===================================================
    echo   Existing Output ISO Detected
    echo ===================================================
    echo Output: "!ISO_OUT!"
    set "ISO_OVERWRITE_CONFIRM="
    set /p "ISO_OVERWRITE_CONFIRM=Overwrite existing output ISO? (Y/N): "
    if /i not "!ISO_OVERWRITE_CONFIRM!"=="Y" (
        echo [CANCELLED] Existing ISO preserved. No archives compiled.
        goto PHASE4E_DONE
    )
)
:: Use a distinct pending ISO so the current output survives a failed build.
for %%O in ("!ISO_OUT!") do set "ISO_PENDING=%%~dpnO.pending_build.iso"
if exist "!ISO_PENDING!" (
    echo [ERROR] Pending build ISO already exists: "!ISO_PENDING!"
    echo Move or remove it manually after checking its contents.
    goto PHASE4E_ERROR
)
:: Never package accidental backups or temporary files into game archives.
set "EXTRA_FILES=0"
for %%D in ("%SCRIPT_DIR%ASSETS" "%SCRIPT_DIR%STREAMS") do (
    for /r "%%~D" %%F in (*.bak *.bak.*) do (
        echo [WARNING] Backup file inside game folder: %%~fF
        set "EXTRA_FILES=1"
    )
)
if "!EXTRA_FILES!"=="1" (
    echo [ERROR] Move or delete the listed backup files before compiling.
    echo No files were changed.
    goto PHASE4E_ERROR
)
echo.
echo The following files will be REPLACED:
echo   "%SCRIPT_DIR%ISO_FILES\ASSETS.DAT"
echo   "%SCRIPT_DIR%ISO_FILES\STREAMS.DAT"
echo Your extracted ASSETS and STREAMS folders will remain unchanged.

echo.
echo [1/2] Compiling ASSETS.DAT with dave.py...
if /i "!MC3_PROFILE!"=="vip" (
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\dave.py" B -ca -cn -cf -fc 1 -d "%SCRIPT_DIR%ASSETS" "%SCRIPT_DIR%ISO_FILES\ASSETS.DAT"
) else (
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\dave.py" B -ca -cn -cf -fc 1 "%SCRIPT_DIR%ASSETS" "%SCRIPT_DIR%ISO_FILES\ASSETS.DAT"
)
if errorlevel 1 (
    echo [ERROR] ASSETS.DAT compilation failed. Stopping.
    goto PHASE4E_ERROR
)
if not exist "%SCRIPT_DIR%ISO_FILES\ASSETS.DAT" (
    echo [ERROR] ASSETS.DAT output was not created.
    goto PHASE4E_ERROR
)
echo.
echo [2/2] Compiling STREAMS.DAT with hash_build.py...
call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\hash_build.py" B "%SCRIPT_DIR%STREAMS" "%SCRIPT_DIR%ISO_FILES\STREAMS.DAT" -a MClub
if errorlevel 1 (
    echo [ERROR] STREAMS.DAT compilation failed. Stopping.
    goto PHASE4E_ERROR
)
if not exist "%SCRIPT_DIR%ISO_FILES\STREAMS.DAT" (
    echo [ERROR] STREAMS.DAT output was not created.
    goto PHASE4E_ERROR
)
echo [OK] Both DAT archives compiled.
if not exist "%SCRIPT_DIR%ISO_FILES\STREAMS.LST" (
    echo [ERROR] Missing ISO_FILES\STREAMS.LST; cannot embed filename manifest.
    goto PHASE4E_ERROR
)
call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_Profile_108S.py" validate "%SCRIPT_DIR%ISO_FILES"
if errorlevel 1 goto PHASE4E_ERROR
if /i "!MC3_PROFILE!"=="vip" (
    set "ISO_OUT=%SCRIPT_DIR%MC3_Modified_VIP.iso"
    echo [INFO] Building VIP with embedded STREAMS.LST from verified source.
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder.py" --profile vip --source "!VIP_SOURCE!" --replacement-dir ISO_FILES --manifest ISO_FILES/STREAMS.LST --output "!ISO_OUT!" --check-only
    if errorlevel 1 goto PHASE4E_ERROR
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder.py" --profile vip --source "!VIP_SOURCE!" --replacement-dir ISO_FILES --manifest ISO_FILES/STREAMS.LST --output "!ISO_PENDING!"
    if errorlevel 1 goto PHASE4E_ERROR
) else (
    set "ISO_OUT=%SCRIPT_DIR%MC3_Modified_DUB.iso"
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder.py" --profile retail --replacement-dir ISO_FILES --manifest ISO_FILES/STREAMS.LST --check-only
    if errorlevel 1 goto PHASE4E_ERROR
    call %PYTHON_CMD% "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder.py" --profile retail --replacement-dir ISO_FILES --manifest ISO_FILES/STREAMS.LST --output "!ISO_PENDING!"
    if errorlevel 1 goto PHASE4E_ERROR
)

if not exist "!ISO_PENDING!" (
    echo [ERROR] Expected pending ISO was not created.
    goto PHASE4E_ERROR
)
for %%I in ("!ISO_PENDING!") do if %%~zI LEQ 0 (
    echo [ERROR] Pending ISO file is empty.
    goto PHASE4E_ERROR
)
:: Replace only after the builder finishes and verifies the new ISO.
call %PYTHON_CMD% -c "import os,sys; os.replace(sys.argv[1],sys.argv[2])" "!ISO_PENDING!" "!ISO_OUT!"
if errorlevel 1 (
    echo [ERROR] Could not replace the final ISO. Previous ISO should remain intact.
    echo [INFO] Completed pending ISO: "!ISO_PENDING!"
    goto PHASE4E_ERROR
)
if not exist "!ISO_OUT!" (
    echo [ERROR] Expected output ISO was not created.
    goto PHASE4E_ERROR
)
for %%I in ("!ISO_OUT!") do if %%~zI LEQ 0 (
    echo [ERROR] ISO file is empty.
    goto PHASE4E_ERROR
)
echo [OK] ISO created and verified: "!ISO_OUT!"
echo Boot the image in PCSX2 to verify gameplay and audio.
:PHASE4E_DONE
echo.
echo [DONE] Phase 4E finished.
pause
endlocal
exit /b 0
:PHASE4E_CANCEL
echo [CANCELLED] No archives compiled.
pause
endlocal
exit /b 0
:PHASE4E_ERROR
echo [STOPPED] See error above.
pause
endlocal
exit /b 1

:: PHASE 4B-4D - UNIFIED GAMEPLAY MUSIC ADDITION
:ADD_CUSTOM_GAMEPLAY_MUSIC
echo.
echo ===================================================
echo   Add Custom Gameplay Music and Title Theme Song
echo ===================================================
for %%F in (add_gameplay_songs.py register_song_playlists.py register_song_metadata.py update_title_theme.py) do (
    if not exist "%SCRIPT_DIR%supporting_tools\%%F" (
        echo [ERROR] Missing supporting_tools\%%F
        goto ADD_MUSIC_FAILED
    )
)
echo This will convert music, register playlists and metadata, and update the title theme song.
echo Unchanged RSMs will be skipped; modified source audio will replace existing RSMs.
set "MUSIC_CONFIRM="
set /p "MUSIC_CONFIRM=Proceed with all four stages? (Y/N), then press Enter: "
if /i not "%MUSIC_CONFIRM%"=="Y" (
    echo [CANCELLED] No music processing started.
    pause
    exit /b 0
)
echo.
echo [1/4] Converting gameplay music...
"%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\add_gameplay_songs.py" "%SCRIPT_DIR%." --yes
if errorlevel 1 goto ADD_MUSIC_FAILED
echo.
echo [2/4] Registering playlists...
"%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\register_song_playlists.py" "%SCRIPT_DIR%." --yes
if errorlevel 1 goto ADD_MUSIC_FAILED
echo.
echo [3/4] Registering metadata...
"%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\register_song_metadata.py" "%SCRIPT_DIR%." --yes
if errorlevel 1 goto ADD_MUSIC_FAILED
echo.
echo.
echo [4/4] Updating title theme song...
"%PYTHON_CMD%" "%SCRIPT_DIR%supporting_tools\update_title_theme.py" "%SCRIPT_DIR%." --yes
if errorlevel 1 goto ADD_MUSIC_FAILED
echo.
echo [DONE] Custom gameplay music processed successfully.
echo Next: Select Option 6 to compile DAT archives and build the ISO.
pause
exit /b 0
:ADD_MUSIC_FAILED
echo.
echo [STOPPED] A stage failed. Later stages were not run.
echo Fix the error shown above and rerun Option 4. Already completed conversions are tracked and will be skipped if unchanged.
pause
exit /b 1



:EXTRACT_ISO_NATIVE
setlocal EnableDelayedExpansion
echo.
echo ===================================================
echo Extract ISO - Retail USA or Supported Modified ISO
echo ===================================================
set "TARGET=%SCRIPT_DIR%%EXTRACTED_ISO_DIR%"
if exist "!TARGET!\" goto NATIVE_EXISTING
goto SELECT_SOURCE

:NATIVE_EXISTING
:: Overwrite authorization is collected once in PREPARE_GAME.
goto SELECT_SOURCE

:SELECT_SOURCE
echo.
echo Enter the Retail USA or VIP Expansion ISO filename or full path.
echo Original and manifest-enabled modified ISOs are supported.
set "SOURCE_ISO="
set /p "SOURCE_ISO=Source ISO (or C to cancel): "
if /i "!SOURCE_ISO!"=="C" (endlocal & exit /b 1)
if not defined SOURCE_ISO goto NATIVE_FAILED
if not exist "!SOURCE_ISO!" if exist "%SCRIPT_DIR%!SOURCE_ISO!" set "SOURCE_ISO=%SCRIPT_DIR%!SOURCE_ISO!"
if not exist "!SOURCE_ISO!" goto NATIVE_FAILED
echo [PREFLIGHT] Verifying ISO and its embedded manifest...
call !PYTHON_CMD! "%SCRIPT_DIR%supporting_tools\MC3_ISO_Extractor.py" "!SOURCE_ISO!" --output-dir "%SCRIPT_DIR%MC3_108S_Staging" --production
if errorlevel 1 goto NATIVE_FAILED
call !PYTHON_CMD! "%SCRIPT_DIR%supporting_tools\MC3_Profile_108S.py" inspect "!SOURCE_ISO!"
if errorlevel 1 goto NATIVE_FAILED
if exist "%SCRIPT_DIR%MC3_108S_Staging" (
    echo [ERROR] MC3_108S_Staging already exists. Move it aside before extracting.
    goto NATIVE_FAILED
)
echo Extracting into a separate staging directory...
call !PYTHON_CMD! "%SCRIPT_DIR%supporting_tools\MC3_ISO_Extractor.py" "!SOURCE_ISO!" --output-dir "%SCRIPT_DIR%MC3_108S_Staging" --extract --production --yes
if errorlevel 1 goto NATIVE_FAILED
call !PYTHON_CMD! "%SCRIPT_DIR%supporting_tools\MC3_Profile_108S.py" record "!SOURCE_ISO!" "%SCRIPT_DIR%MC3_108S_Staging" "%SCRIPT_DIR%supporting_tools\MC3_PS2_Streams.lst"
if errorlevel 1 goto NATIVE_FAILED
if exist "!TARGET!" (
    if exist "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" (
        echo [ERROR] Temporary previous ISO_FILES directory already exists. Nothing replaced.
        goto NATIVE_FAILED
    )
    move "!TARGET!" "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" >nul
    if errorlevel 1 goto NATIVE_FAILED
)
move "%SCRIPT_DIR%MC3_108S_Staging" "!TARGET!" >nul
if errorlevel 1 (
    echo [ERROR] Could not activate staged extraction. Restoring previous ISO_FILES...
    if exist "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" move "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" "!TARGET!" >nul
    goto NATIVE_FAILED
)
if exist "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" (
    echo [INFO] Removing superseded ISO_FILES after successful activation...
    rmdir /s /q "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES"
    if exist "%SCRIPT_DIR%MC3_108S_Previous_ISO_FILES" echo [WARNING] Could not remove previous ISO_FILES. Remove it manually after confirming extraction.
)
call :VALIDATE_ISO_FOLDER "!TARGET!"
if errorlevel 1 goto NATIVE_FAILED
echo [OK] Verified extraction and manifest recovery complete.
endlocal & exit /b 0

:NATIVE_FAILED
echo [ERROR] Source preflight, extraction, or folder validation failed.
echo [WARNING] Inspect ISO_FILES before retrying. No automatic cleanup performed.
pause
endlocal & exit /b 1

:VALIDATE_ISO_FOLDER
if not exist "%~1\ASSETS.DAT" (
    echo [MISSING] ASSETS.DAT in "%~1"
    exit /b 1
)
if not exist "%~1\STREAMS.DAT" (
    echo [MISSING] STREAMS.DAT in "%~1"
    exit /b 1
)
echo [OK] ASSETS.DAT found.
echo [OK] STREAMS.DAT found.
exit /b 0


:: ==========================================================================
:: PHASE 3 - DAT ARCHIVE EXTRACTION
:: Original DATs inside ISO_FILES are never changed by this operation.
:: ==========================================================================
:DECOMPILE_DAT
setlocal EnableDelayedExpansion
echo.
echo ===================================================
echo Decompile Game Archives
echo ===================================================
call :VALIDATE_ISO_FOLDER "%SCRIPT_DIR%%EXTRACTED_ISO_DIR%"
if errorlevel 1 (
    echo [ERROR] ISO_FILES is missing or incomplete. Use setup option 1 first.
    echo No files were modified.
    echo.
    pause
    endlocal & exit /b 1
)

:: Ask at each existing folder during the normal process; no setup submenu.
:: Resolve choices before deleting anything, so Cancel preserves both folders.
set "EXTRACT_ASSETS=1"
set "EXTRACT_STREAMS=1"
set "CLEAR_ASSETS=0"
set "CLEAR_STREAMS=0"
if /i "%~1"=="AUTO_OVERWRITE" (
    if exist "%SCRIPT_DIR%%ASSET_FOLDER%\" set "CLEAR_ASSETS=1"
    if exist "%SCRIPT_DIR%%AUDIO_FOLDER%\" set "CLEAR_STREAMS=1"
    goto DECOMPILE_CHOICES_DONE
)
if exist "%SCRIPT_DIR%%ASSET_FOLDER%\" (
    echo.
    echo Existing %ASSET_FOLDER% folder detected.
    call :CHOOSE_EXISTING "%SCRIPT_DIR%%ASSET_FOLDER%" "%ASSET_FOLDER%" EXTRACT_ASSETS CLEAR_ASSETS
    if errorlevel 1 (
        echo [CANCELLED] Decompilation canceled. No folders deleted.
        endlocal & exit /b 1
    )
)
if exist "%SCRIPT_DIR%%AUDIO_FOLDER%\" (
    echo.
    echo Existing %AUDIO_FOLDER% folder detected.
    call :CHOOSE_EXISTING "%SCRIPT_DIR%%AUDIO_FOLDER%" "%AUDIO_FOLDER%" EXTRACT_STREAMS CLEAR_STREAMS
    if errorlevel 1 (
        echo [CANCELLED] Decompilation canceled. No folders deleted.
        endlocal & exit /b 1
    )
)
:DECOMPILE_CHOICES_DONE
if "!CLEAR_ASSETS!"=="1" (
    call :REMOVE_GAME_FOLDER "%SCRIPT_DIR%%ASSET_FOLDER%" "ASSETS"
    if errorlevel 1 (endlocal & exit /b 1)
)
if "!CLEAR_STREAMS!"=="1" (
    call :REMOVE_GAME_FOLDER "%SCRIPT_DIR%%AUDIO_FOLDER%" "STREAMS"
    if errorlevel 1 (endlocal & exit /b 1)
)

if "!EXTRACT_ASSETS!"=="0" if "!EXTRACT_STREAMS!"=="0" (
    echo.
    echo [INFO] Both existing folders were reused. No archives extracted.
    echo.
    pause
    endlocal & exit /b 0
)

if "!EXTRACT_ASSETS!"=="1" (
    echo.
    echo ---------------------------------------------------
    echo [1/2] Decompiling ASSETS.DAT using dave.py...
    echo ---------------------------------------------------
    :: -o avoids copying a multi-gigabyte DAT to the project root.
    call !PYTHON_CMD! "%SCRIPT_DIR%%TOOLS_DIR%\dave.py" X "%SCRIPT_DIR%%EXTRACTED_ISO_DIR%\ASSETS.DAT" -o "%SCRIPT_DIR%%ASSET_FOLDER%"
    if errorlevel 1 (
        echo [ERROR] dave.py failed. Check the ASSETS folder for partial output.
        goto DECOMPILE_FAILED
    )
    call :CHECK_NONEMPTY "%SCRIPT_DIR%%ASSET_FOLDER%"
    if errorlevel 1 (
        echo [ERROR] ASSETS extraction produced no files.
        goto DECOMPILE_FAILED
    )
    echo [OK] ASSETS folder extracted.
) else (
    echo [SKIPPED] Reusing existing ASSETS folder.
)

if "!EXTRACT_STREAMS!"=="1" (
    echo.
    echo ---------------------------------------------------
    echo [2/2] Decompiling STREAMS.DAT using hash_build.py...
    echo ---------------------------------------------------
    set "STREAMS_NAME_LIST=%SCRIPT_DIR%%TOOLS_DIR%\MC3_PS2_Streams.lst"
    if exist "%SCRIPT_DIR%%EXTRACTED_ISO_DIR%\STREAMS.LST" (
        set "STREAMS_NAME_LIST=%SCRIPT_DIR%%EXTRACTED_ISO_DIR%\STREAMS.LST"
        echo [INFO] Using filename list included in the extracted ISO.
    ) else (
        echo [INFO] Using original STREAMS filename list.
    )
    call !PYTHON_CMD! "%SCRIPT_DIR%%TOOLS_DIR%\hash_build.py" X "%SCRIPT_DIR%%EXTRACTED_ISO_DIR%\STREAMS.DAT" -nl "!STREAMS_NAME_LIST!" -a mclub -th 45 -o "%SCRIPT_DIR%%AUDIO_FOLDER%"
    if errorlevel 1 (
        echo [ERROR] hash_build.py failed. Check the STREAMS folder for partial output.
        goto DECOMPILE_FAILED
    )
    call :CHECK_NONEMPTY "%SCRIPT_DIR%%AUDIO_FOLDER%"
    if errorlevel 1 (
        echo [ERROR] STREAMS extraction produced no files.
        goto DECOMPILE_FAILED
    )
    echo [OK] STREAMS folder extracted.
) else (
    echo [SKIPPED] Reusing existing STREAMS folder.
)

echo.
echo ===================================================
echo [OK] Phase 3 decompilation completed.
echo Original ASSETS.DAT and STREAMS.DAT remain unchanged.
echo ===================================================
echo.
pause
endlocal & exit /b 0

:DECOMPILE_FAILED
echo.
echo [WARNING] Any partial output has been preserved for inspection.
echo [WARNING] Original DAT files in ISO_FILES were not modified.
echo.
pause
endlocal & exit /b 1

:: Existing folder: reuse or cancel; never overwrite in place.
:CHOOSE_EXISTING
set "CHOICE_PATH=%~1"
set "CHOICE_LABEL=%~2"
echo "%CHOICE_PATH%"
echo [O] Overwrite - Clear this folder and decompile fresh
echo [R] Reuse existing folder without changes
echo [C] Cancel and return to Main Menu
set "FOLDER_CHOICE="
set /p "FOLDER_CHOICE=Choose O, R or C and press Enter: "
if /i "%FOLDER_CHOICE%"=="R" (
    call :CHECK_NONEMPTY "%CHOICE_PATH%"
    if errorlevel 1 (
        echo [ERROR] Existing %CHOICE_LABEL% folder contains no files.
        exit /b 1
    )
    set "%~3=0"
    set "%~4=0"
    exit /b 0
)
if /i not "%FOLDER_CHOICE%"=="O" exit /b 1
echo [OVERWRITE] Clearing %CHOICE_LABEL% and decompiling fresh files...
set "%~3=1"
set "%~4=1"
exit /b 0

:REMOVE_GAME_FOLDER
:: Only ever called with the three known project work directories.
set "REMOVE_TARGET=%~f1"
if /i not "%~2"=="ISO_FILES" if /i not "%~2"=="ASSETS" if /i not "%~2"=="STREAMS" exit /b 1
if not exist "%REMOVE_TARGET%\" exit /b 0
echo [CLEARING] "%REMOVE_TARGET%"
rmdir /s /q "%REMOVE_TARGET%"
if exist "%REMOVE_TARGET%\" (
    echo [ERROR] Unable to completely clear %~2. Stopping.
    exit /b 1
)
exit /b 0

:CHECK_NONEMPTY
if not exist "%~1\" exit /b 1
for /f "delims=" %%F in ('dir /a-d /b /s "%~1" 2^>nul') do exit /b 0
exit /b 1

:: ==========================================================================
:: PHASE 4A - CONVERT CUSTOM MUSIC
:: ========================================================================== 
:: ==========================================================================
:: WIN/LOSE FOLDER-DRIVEN MUSIC SYNC
:: Only Option 3 uses this helper. All other options retain their original code.
:: ==========================================================================

:SYNC_WINLOSE_FOLDERS
echo.
echo ===================================================
echo Win/Lose Music Customization
echo ===================================================
echo [1] Replace Existing Win/Lose Music
echo [2] Add New Win/Lose Music
echo [3] Return to Main Menu
echo.
set "WINLOSE_MODE="
set /p "WINLOSE_MODE=Enter choice (1-3), then press Enter: "
if "%WINLOSE_MODE%"=="3" exit /b 0
if "%WINLOSE_MODE%"=="1" set "WINLOSE_ACTION=replace"
if "%WINLOSE_MODE%"=="2" set "WINLOSE_ACTION=add"
if not defined WINLOSE_ACTION (
    echo [ERROR] Invalid selection.
    pause
    exit /b 1
)
echo.
echo [INFO] Win source:  Custom Music\2_Win
echo [INFO] Lose source: Custom Music\2_Lose
echo [INFO] Empty folders are skipped without modifying game files.
if not exist "%SCRIPT_DIR%%TOOLS_DIR%\sync_winlose_folders.py" (
    echo [ERROR] Missing supporting_tools\sync_winlose_folders.py
    pause
    exit /b 1
)
"%PYTHON_CMD%" "%SCRIPT_DIR%%TOOLS_DIR%\sync_winlose_folders.py" "%SCRIPT_DIR%." "%WINLOSE_ACTION%"
set "WINLOSE_RESULT=%ERRORLEVEL%"
if not "%WINLOSE_RESULT%"=="0" echo [ERROR] Win/Lose customization failed. Review messages above.
pause
exit /b %WINLOSE_RESULT%

:: ==========================================================================
:: REQUIREMENT CHECKER
:: ==========================================================================
:CHECK_REQUIREMENTS
set "CHECK_FAILED=0"
echo ===================================================
echo Checking Required Files and Tools
echo ===================================================
echo.

if exist "%SCRIPT_DIR%%ORIGINAL_ISO%" (
    echo [OK] Retail USA source ISO
) else (
    echo [INFO] Retail USA source ISO not found.
)
if exist "%SCRIPT_DIR%MC3-VIP-Expansion-ONLY.iso" (
    echo [OK] VIP Expansion source ISO
) else (
    echo [INFO] VIP Expansion source ISO not found.
)
if not exist "%SCRIPT_DIR%%ORIGINAL_ISO%" if not exist "%SCRIPT_DIR%MC3-VIP-Expansion-ONLY.iso" (
    echo [ERROR] Neither supported original ISO is present.
    set "CHECK_FAILED=1"
)

if exist "%SCRIPT_DIR%supporting_tools\MC3_ISO_Extractor.py" (
    echo [OK]      supporting_tools\MC3_ISO_Extractor.py - Unified extractor
) else (
    echo [MISSING] supporting_tools\MC3_ISO_Extractor.py
    set "CHECK_FAILED=1"
)
if exist "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder_VIP.py" (
    echo [OK] supporting_tools\MC3_ISO_Builder_VIP.py - VIP
) else (
    echo [MISSING] supporting_tools\MC3_ISO_Builder_VIP.py
    set "CHECK_FAILED=1"
)
if exist "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder.py" (
    echo [OK] supporting_tools\MC3_ISO_Builder.py - Unified dispatcher
) else (
    echo [MISSING] supporting_tools\MC3_ISO_Builder.py
    set "MISSING_TOOLS=1"
)
if exist "%SCRIPT_DIR%supporting_tools\MC3_ISO_Builder_Retail.py" (
    echo [OK]      supporting_tools\MC3_ISO_Builder_Retail.py
) else (
    echo [MISSING] supporting_tools\MC3_ISO_Builder_Retail.py
    set "CHECK_FAILED=1"
)

if exist "%SCRIPT_DIR%%TOOLS_DIR%\dave.py" (
    echo [OK]      dave.py
) else (
    echo [MISSING] dave.py
    echo           Expected: "%SCRIPT_DIR%%TOOLS_DIR%\dave.py"
    set "CHECK_FAILED=1"
)

if exist "%SCRIPT_DIR%%TOOLS_DIR%\hash_build.py" (
    echo [OK]      hash_build.py
) else (
    echo [MISSING] hash_build.py
    echo           Expected: "%SCRIPT_DIR%%TOOLS_DIR%\hash_build.py"
    set "CHECK_FAILED=1"
)

if exist "%SCRIPT_DIR%%TOOLS_DIR%\MC3_PS2_Streams.lst" (
    echo [OK]      MC3_PS2_Streams.lst
) else (
    echo [MISSING] MC3_PS2_Streams.lst
    echo           Expected: "%SCRIPT_DIR%%TOOLS_DIR%\MC3_PS2_Streams.lst"
    set "CHECK_FAILED=1"
)

:: Python is needed by the bundled archive scripts, not as the main interface.
where python.exe >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    echo [OK]      Python
) else (
    where py.exe >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py"
        echo [OK]      Python launcher
    ) else (
        echo [MISSING] Python
        echo           Needed to run dave.py and hash_build.py.
        set "CHECK_FAILED=1"
    )
)

if exist "%SCRIPT_DIR%%TOOLS_DIR%\rstm_build.py" (
    echo [OK]      rstm_build.py
) else (
    echo [PENDING]  rstm_build.py - needed in music phase
)
if exist "%SCRIPT_DIR%%TOOLS_DIR%\strtbl.py" (
    echo [OK]      strtbl.py
) else (
    echo [PENDING]  strtbl.py - needed in metadata phase
)

echo.
if "!CHECK_FAILED!" NEQ "0" exit /b 1
exit /b 0
