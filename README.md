# MC3 Ultimate Music Tools v1.1

Add your own MP3 or WAV music to Midnight Club 3: DUB Edition Remix and build a custom ISO to play in PCSX2. Customize gameplay, Garage Shop, the title screen, race transitions, and loading screens.

## Requirements

- Windows, PowerShell, and an internet connection for setup.
- Python 3.12. Setup can install it with Windows Package Manager (`winget`) and installs PySide6, NumPy, SciPy, SoundFile, and sounddevice in a local virtual environment.
- Your own supported base ISO (**Retail USA**, **VIP v1.0-C**, or **VIP v1.1-A**) and enough disk space for the extracted files and rebuilt ISO.
- [PCSX2](https://pcsx2.net/) to play the rebuilt ISO.

## Setup

1. Select **Code → Download ZIP** on GitHub and extract it to a short, writable path such as `C:\MC3Tools`.
2. Open PowerShell in the extracted project folder and run the setup command below. If `winget` is unavailable, install [Python 3.12](https://www.python.org/downloads/) manually, then reopen PowerShell and rerun setup.

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install_MC3_GUI_Dependencies.ps1"
   ```
3. After **Setup complete**, double-click **Launch.bat**. Use the same launcher for future sessions.
4. Open **ISO Extraction - Start Here**, select your base ISO, and run extraction. Apply your music, then open **Build ISO**.

## GUI quick reference

- **Dashboard** — View soundtrack counts, the current title theme, and estimated workspace capacity.
- **ISO Extraction - Start Here** — Extract your base ISO and prepare the workspace.
- **Remove Soundtracks** — Remove individual gameplay or Garage Shop tracks, a whole category, or the full gameplay and Garage Shop soundtrack.
- **Gameplay / Garage Music** — Stage MP3 or WAV tracks by genre or for Garage Shop, fill in artist and song names, then select **Add Tracks**.
- **Title Theme Soundtrack** — Replace the title-screen music with one MP3 or WAV track.
- **Lose/Win (Race Transition) Music** — Add, replace, or remove tracks for race wins and losses.
- **Loading Screen Music** — Assign clips up to 9.493 seconds long to 18 looping slots manually, randomly, or evenly.
- **Build ISO** — Rebuild the game archives and create a modified ISO for PCSX2.
- **Export/Import Music** — Save or restore your staged music and loading-slot selections as a ZIP.
- **About** — View information about the tools.
