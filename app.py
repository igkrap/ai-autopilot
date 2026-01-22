from __future__ import annotations

import os
import sys
from PySide6 import QtWidgets

from ui.main_window import MainWindow


def main() -> int:
    os.environ.setdefault("QT_DPI_AWARENESS_CONTEXT", "DPI_AWARENESS_CONTEXT_UNAWARE")
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
