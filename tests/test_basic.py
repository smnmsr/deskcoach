def test_import_main(monkeypatch):
    # Install minimal dummy PyQt6 modules to satisfy imports in main.py
    import sys, types
    import types as _types
    def _mod(name):
        m = _types.ModuleType(name)
        return m
    qtcore = _types.ModuleType("PyQt6.QtCore")
    for n in ["QTimer", "QObject", "QCoreApplication", "Qt"]:
        setattr(qtcore, n, object)
    qtwidgets = _types.ModuleType("PyQt6.QtWidgets")
    for n in [
        "QApplication","QSystemTrayIcon","QMenu","QMainWindow","QWidget","QVBoxLayout","QPushButton",
        "QDialog","QFormLayout","QLineEdit","QDoubleSpinBox","QSpinBox","QCheckBox","QMessageBox","QHBoxLayout"
    ]:
        setattr(qtwidgets, n, object)
    style = _types.SimpleNamespace(StandardPixmap=object)
    setattr(qtwidgets, "QStyle", style)
    qtgui = _types.ModuleType("PyQt6.QtGui")
    setattr(qtgui, "QIcon", object)
    setattr(qtgui, "QAction", object)
    pyqt6 = _types.ModuleType("PyQt6")
    setattr(pyqt6, "QtCore", qtcore)
    setattr(pyqt6, "QtWidgets", qtwidgets)
    setattr(pyqt6, "QtGui", qtgui)
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore
    sys.modules["PyQt6.QtWidgets"] = qtwidgets
    sys.modules["PyQt6.QtGui"] = qtgui

    # Provide a dummy session_watcher module to avoid heavy Qt deps
    import types as _types
    dummy_sw = _types.ModuleType("deskcoach.services.session_watcher")
    class _SW: ...
    setattr(dummy_sw, "SessionWatcher", _SW)
    sys.modules["deskcoach.services.session_watcher"] = dummy_sw

    sys.path.append('src')
    import deskcoach.main  # noqa: F401
    assert True
