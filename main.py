"""Project Open-J: Primary Broadcast Orchestrator & Dual-Screen Launcher.
Coordinates Finite State Machine (GameEngine), QuestionEngine, ScoreEngine,
BuzzerCoordinator, HostControllerWindow, and TVStudioDisplayWindow.
Supports multi-screen broadcasting with High-DPI scaling, OpenGL hardware acceleration
(VSync + 4x MSAA), and display hot-plugging.
"""

import os
import sys

# High DPI Scaling for Windows
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from data.db import DatabaseManager
from data.history import HistoryManager
from core.questions import QuestionEngine
from core.scoring import ScoreEngine
from core.buzzer import BuzzerCoordinator
from core.engine import GameEngine
from ui.audio_manager import AudioManager
from ui.host_controller import HostControllerWindow
from ui.tv_display import TVDisplayWindow


def configure_opengl_surface():
    """Configures hardware-accelerated OpenGL surface format with VSync and 4x MSAA."""
    try:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
        fmt.setSwapInterval(1)  # VSync enabled for tear-free 60/120/144Hz output
        fmt.setSamples(4)       # 4x MSAA hardware antialiasing for 3D flips & edges
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)
    except Exception as e:
        print(f"[Main] OpenGL surface format setup notice: {e}")


def main():
    configure_opengl_surface()
    app = QApplication(sys.argv)
    app.setApplicationName("Project Open-J")
    app.setOrganizationName("Open-J Broadcast Engine")

    # 1. Initialize Persistence & History Managers
    print("[Main] Initializing SQLite database and schema migrations...")
    db_manager = DatabaseManager()
    db_manager.init_db()
    db_manager.reset_ongame()
    history_manager = HistoryManager(db_manager)

    # 2. Instantiate Core Engines & FSM
    print("[Main] Instantiating Core Logic Engines (Question, Score, Buzzer, FSM)...")
    q_engine = QuestionEngine(db=db_manager)
    s_engine = ScoreEngine(["Ken Jennings", "Gold Ship", "Agnes Tachyon"])
    buzzer_coordinator = BuzzerCoordinator(list(s_engine.players.keys()))
    game_fsm = GameEngine(
        question_engine=q_engine,
        score_engine=s_engine,
        buzzer_coordinator=buzzer_coordinator,
        history_manager=history_manager
    )

    # 3. Initialize Singleton Audio & UI Subsystems
    print("[Main] Initializing Audio Subsystem and Windows...")
    audio_mgr = AudioManager()
    tv_win = TVDisplayWindow()
    host_win = HostControllerWindow(q_engine, s_engine)

    # Link FSM reference to Host window for deep telemetry
    host_win.game_fsm = game_fsm

    # 4. Multi-Screen Studio Routing: Route TV Display to Screen 2 if present
    screens = app.screens()
    if len(screens) > 1:
        tv_win.setScreen(screens[1])
        tv_win.showFullScreen()
        print(f"[Main Orchestrator] Multi-monitor detected. TV Studio Display routed to screen 2: {screens[1].name()}")
    else:
        tv_win.resize(1024, 576)
        tv_win.show()
        print("[Main Orchestrator] Single monitor detected. TV Studio Display running in windowed mode (1024x576).")

    # 5. Hot-Plugging Safeguard for screen disconnection
    def on_screen_removed(screen):
        if len(app.screens()) <= 1:
            tv_win.showNormal()
            tv_win.resize(1024, 576)
            print("[Main Orchestrator] Secondary screen removed. TV Display restored to windowed mode.")

    app.screenRemoved.connect(on_screen_removed)

    # 6. Show Host Controller Console on Primary Screen
    host_win.show()
    print("[Main] Open-J broadcast engine successfully initialized and active.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()