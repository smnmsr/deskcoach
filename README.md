# DeskCoach

A minimal PyQt6 system tray app for Windows that reminds you to take healthy breaks.

## Quick start

- Requirements: Windows 10/11, Python 3.10+
- Install deps:
  
  PowerShell
  
      python -m venv .venv
      .\.venv\Scripts\Activate.ps1
      python -m pip install -r requirements.txt

- Run the app:
  
      python -m deskcoach.main
  
  Or, after installing as a package (build or editable install), use the console script:
  
      deskcoach

The app places an icon in the system tray. Right-click for the menu (Open, Settings, Pause/Resume, Snooze, Exit).

## Project layout

- src\deskcoach\main.py — entry point
- src\deskcoach\views — simple windows/dialogs
- src\deskcoach\services — notifier, scheduler, reminders, session watcher
- src\deskcoach\models — lightweight SQLite-backed store
- src\deskcoach\resources\icons — app icons

## Tests

Run the test suite from the project root:

    pytest -q

## Build (optional)

You can create a Windows executable with PyInstaller. A starter spec file is provided:

    pyinstaller main.spec

This will produce dist\DeskCoach.exe.
