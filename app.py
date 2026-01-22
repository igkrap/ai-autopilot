from __future__ import annotations

import sys
from PySide6 import QtWidgets

from ui.main_window import MainWindow


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
