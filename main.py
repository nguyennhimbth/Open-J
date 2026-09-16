"""Open-J: Main Orchestrator & Dual-Screen Launcher.
Coordinates QuestionEngine, ScoreEngine, HostControllerWindow, and TVDisplayWindow.
Supports multi-monitor setups (Screen 1 for Host, Screen 2 for TV Studio Display)
with High-DPI scaling and screen hot-plugging fallbacks.
"""

import os
import sys

# High DPI Scaling for Windows
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from PySide6.QtWidgets import QApplication
from ui.host_controller import HostControllerWindow
from ui.tv_display import TVDisplayWindow
from core.question_core import QuestionEngine
from core.score_core import ScoreEngine


def main():
    app = QApplication(sys.argv)

    # 1. Khởi tạo backend engines
    q_engine = QuestionEngine()
    q_engine.seed_sample_data(force_reset=False)
    s_engine = ScoreEngine(["Ken Jennings", "Gold Ship", "Agnes Tachyon"])

    # 2. Khởi tạo UI
    host_win = HostControllerWindow(q_engine, s_engine)
    tv_win = TVDisplayWindow()

    # 3. Nhận diện đa màn hình: TV sang màn hình thứ 2 nếu có
    screens = app.screens()
    if len(screens) > 1:
        tv_win.setScreen(screens[1])
        tv_win.showFullScreen()
        print(f"[Orchestrator] Multi-monitor detected. TV Display routed to screen 2: {screens[1].name()}")
    else:
        tv_win.resize(1024, 576)
        tv_win.show()
        print("[Orchestrator] Single monitor detected. TV Display running in windowed mode (1024x576).")

    # 4. Fallback khi cắm/rút màn hình phụ (Hot-plugging)
    def on_screen_removed(screen):
        if len(app.screens()) <= 1:
            tv_win.showNormal()
            tv_win.resize(1024, 576)
            print("[Orchestrator] Secondary screen disconnected. TV Display restored to windowed mode.")

    app.screenRemoved.connect(on_screen_removed)

    host_win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()