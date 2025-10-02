from __future__ import annotations

try:
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
    import qdarktheme  # type: ignore
    _HAVE_QT_GUI = True
except Exception:
    # In test environments, a minimal dummy PyQt6 or missing qdarktheme may be present; gracefully degrade.
    _HAVE_QT_GUI = False
    QFont = object  # type: ignore
    QApplication = object  # type: ignore
    qdarktheme = None  # type: ignore








def apply_modern_style(app: QApplication, theme: str = "auto") -> None:
    """Apply PyQtDarkTheme as the single source of styling.

    - Uses qdarktheme.setup_theme with theme = 'auto' | 'dark' | 'light'.
    - When theme='auto', the app follows the OS theme and updates live.
    - On supported OSes, accent color sync is handled by qdarktheme.
    """
    # Apply PyQtDarkTheme (do not set Fusion or manual palettes/stylesheets)
    if qdarktheme is not None:
        if hasattr(qdarktheme, "setup_theme"):
            qdarktheme.setup_theme(
                theme=theme,
                corner_shape="rounded",
                additional_qss=(
                    """
                    QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
                        border-radius: 8px;
                        padding: 6px 10px;
                    }
                    QMenu::item { border-radius: 6px; padding: 6px 12px; }

                    /* DeskCoach dashboard styles */
                    QLabel[dc="date"] {
                        font-weight: 600;
                        font-size: 16px;
                    }
                    QLabel[dc="muted"] {
                        color: palette(mid);
                    }
                    QFrame[dc="card"] {
                        border-radius: 10px;
                        border: 1px solid palette(mid);
                    }
                    QLabel[dc="cardTitle"] { color: palette(mid); }
                    QLabel[dc="value"] {
                        font-size: 28px;
                        font-weight: 700;
                        padding: 2px 0 6px 0;
                    }
                    QLabel[dc="pill"] {
                        padding: 3px 8px;
                        border-radius: 10px;
                        background: palette(button);
                        color: palette(button-text);
                    }
                    QLabel[dc="pill"][class="good"] { background: #2e7d32; color: white; }
                    QLabel[dc="pill"][class="bad"]  { background: #c62828; color: white; }
                    """
                ),
            )
        else:
            # Compatibility for PyQtDarkTheme < 2.0: use stylesheet string API if available
            try:
                if hasattr(qdarktheme, "load_stylesheet"):
                    base_theme = theme if theme in ("dark", "light") else "dark"
                    qss = qdarktheme.load_stylesheet(base_theme)
                    qss += """
                    QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
                        border-radius: 8px;
                        padding: 6px 10px;
                    }
                    QMenu::item { border-radius: 6px; padding: 6px 12px; }

                    /* DeskCoach dashboard styles */
                    QLabel[dc=\"date\"] {
                        font-weight: 600;
                        font-size: 16px;
                    }
                    QLabel[dc=\"muted\"] {
                        color: palette(mid);
                    }
                    QFrame[dc=\"card\"] {
                        border-radius: 10px;
                        border: 1px solid palette(mid);
                    }
                    QLabel[dc=\"cardTitle\"] { color: palette(mid); }
                    QLabel[dc=\"value\"] {
                        font-size: 28px;
                        font-weight: 700;
                        padding: 2px 0 6px 0;
                    }
                    QLabel[dc=\"pill\"] {
                        padding: 3px 8px;
                        border-radius: 10px;
                        background: palette(button);
                        color: palette(button-text);
                    }
                    QLabel[dc=\"pill\"][class=\"good\"] { background: #2e7d32; color: white; }
                    QLabel[dc=\"pill\"][class=\"bad\"]  { background: #c62828; color: white; }
                    """
                    try:
                        app.setStyleSheet(qss)
                    except Exception:
                        pass
            except Exception:
                pass

    # Slightly larger, readable default font
    f: QFont = app.font()
    if hasattr(f, "pointSize") and f.pointSize() > 0:
        f.setPointSize(max(f.pointSize(), 10))
    elif hasattr(f, "pixelSize"):
        f.setPixelSize(max(f.pixelSize(), 14))
    try:
        app.setFont(f)
    except Exception:
        pass
