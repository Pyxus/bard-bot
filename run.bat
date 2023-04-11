@echo off
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed on your system.
    echo Please download and install Python from https://www.python.org/downloads/.
) else (
    echo This will now install/update some stuff. This was written by Pyxus so if you trust him you're good to go.
    echo If you don't... I see how it is.
    choice /m "Anyway do you want to continue?"
    
    if errorlevel 2 goto no

    pip install -U py-cord[voice]
    pip install -U PyNaCl
    pip install -U yt-dlp
    goto end

    :no
    echo Pyxus will remember this.

    :end
    echo Setup complete!
    cls
    echo Grabbing my lute...
    start "bard-bot" python %~dp0/src/bot.py ; echo "Test"
)