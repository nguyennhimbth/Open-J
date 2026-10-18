"""
Open-J - Host Board Controller Components
Provides:
1. ControllerGridCell: [X (Auto Play)] + [Point Button (Manual Select)] for 6x5 matrix.
2. EditClueDialog: Dialog for live clue and answer editing during matches.
3. ClueControlPanel: Playout action controls including 3-second rapid playout, replay, and edit.
"""

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QPushButton,
    QDialog, QLabel, QTextEdit, QLineEdit, QDialogButtonBox, QMessageBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor


class EditClueDialog(QDialog):
    """Hộp thoại chỉnh sửa nhanh câu hỏi và câu trả lời trong trận đấu."""
    def __init__(self, current_clue: str, current_answer: str, point_value: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Chỉnh sửa câu hỏi (${point_value})")
        self.resize(520, 340)
        self.setStyleSheet("""
            QDialog { background-color: #0d1117; color: #e6edf3; }
            QLabel { color: #f0f6fc; font-weight: bold; font-size: 13px; }
            QTextEdit, QLineEdit {
                background-color: #161b22; color: #ffffff; border: 1px solid #30363d;
                border-radius: 6px; padding: 8px; font-size: 13px;
            }
            QTextEdit:focus, QLineEdit:focus { border: 1px solid #58a6ff; }
            QPushButton {
                background-color: #21262d; border: 1px solid #30363d; border-radius: 6px;
                color: #c9d1d9; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #30363d; }
        """)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nội dung Manh mối / Câu hỏi:"))
        self.clue_edit = QTextEdit(current_clue)
        layout.addWidget(self.clue_edit)

        layout.addWidget(QLabel("Đáp án chuẩn (Host Answer):"))
        self.answer_edit = QLineEdit(current_answer)
        layout.addWidget(self.answer_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return self.clue_edit.toPlainText().strip(), self.answer_edit.text().strip()


class ControllerGridCell(QWidget):
    """
    Tổ hợp 1 ô trên Controller: 
    [X (Auto Play)] + [Point Button (Manual Select)]
    """
    auto_trigger_requested = Signal(int, int) # (col, row)
    manual_select_requested = Signal(int, int)

    def __init__(self, col: int, row: int, point_value: int, parent=None):
        super().__init__(parent)
        self.col = col
        self.row = row
        self.point_value = point_value
        self.is_played = False
        self.is_selected = False
        self.is_daily_double = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(76, 48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(2)

        # NÚT [X] BÊN TRÁI: Kích hoạt hoạt ảnh tự động
        self.btn_auto = QPushButton("X")
        self.btn_auto.setFixedWidth(28)
        self.btn_auto.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_auto.setCursor(Qt.PointingHandCursor)
        self.btn_auto.setToolTip("Kích hoạt hoạt ảnh tự động (Zoom điểm số -> 1.5s -> Hiện câu hỏi)")
        self.btn_auto.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #ff4444;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #FF0000; }
            QPushButton:disabled { background-color: #222222; color: #555555; border: 1px solid #333333; }
        """)
        self.btn_auto.clicked.connect(lambda: self.auto_trigger_requested.emit(self.col, self.row))
        layout.addWidget(self.btn_auto)

        # NÚT ĐIỂM SỐ: Chạy thủ công
        self.btn_manual = QPushButton(f"${point_value}")
        self.btn_manual.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_manual.setCursor(Qt.PointingHandCursor)
        self.btn_manual.setStyleSheet("""
            QPushButton {
                background-color: #060CE9;
                color: #FFA500;
                font-weight: 900;
                font-size: 13px;
                border: 1px solid #1c279c;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #1E90FF; }
        """)
        self.btn_manual.clicked.connect(lambda: self.manual_select_requested.emit(self.col, self.row))
        layout.addWidget(self.btn_manual)

    def set_played_state(self, played: bool):
        self.is_played = played
        if played:
            self.btn_manual.setStyleSheet("background-color: #161b22; color: #484f58; font-size: 13px; font-weight: bold; border: 1px solid #21262d; border-radius: 3px;")
            self.btn_auto.setEnabled(False)
        else:
            self.btn_auto.setEnabled(True)
            self._update_manual_style()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_manual_style()

    def set_points(self, points: int, is_dd: bool = False):
        self.point_value = points
        self.is_daily_double = is_dd
        prefix = "[DD] " if is_dd else ""
        self.btn_manual.setText(f"{prefix}${points}")
        self._update_manual_style()

    def _update_manual_style(self):
        if self.is_played:
            self.btn_manual.setStyleSheet("background-color: #161b22; color: #484f58; font-size: 13px; font-weight: bold; border: 1px solid #21262d; border-radius: 3px;")
            return

        if self.is_selected:
            self.btn_manual.setStyleSheet("background-color: #060CE9; color: #FFCC00; font-size: 14px; font-weight: 900; border: 2px solid #ff3333; border-radius: 3px;")
        else:
            color = "#ff5555" if self.is_daily_double else "#FFA500"
            self.btn_manual.setStyleSheet(f"""
                QPushButton {{
                    background-color: #060CE9;
                    color: {color};
                    font-weight: 900;
                    font-size: 13px;
                    border: 1px solid #1c279c;
                    border-radius: 3px;
                }}
                QPushButton:hover {{ background-color: #1E90FF; }}
            """)

    # Forwarding helper methods for full compatibility with QPushButton calls
    def setText(self, text: str):
        self.btn_manual.setText(text)

    def text(self) -> str:
        return self.btn_manual.text()

    def setStyleSheet(self, style: str):
        self.btn_manual.setStyleSheet(style)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.btn_manual.setEnabled(enabled)
        self.btn_auto.setEnabled(enabled and not self.is_played)


class ClueControlPanel(QWidget):
    """
    Bảng điều khiển Playout bên phải:
    - Nút 1: Zoom Point Cell
    - Nút 2: Reveal Clue Text
    - Nút 3: Toggle TV Answer
    - Nút 4: Close Clue
    - Nút Mới: Chỉnh câu hỏi (Edit Clue)
    - Nút Mới: Chơi lại (Replay Clue)
    - Nút Chạy nhanh toàn bộ trong 3 giây (Fast Playout 3s)
    """
    zoom_splash_signal = Signal()
    reveal_clue_signal = Signal()
    toggle_answer_signal = Signal()
    close_clue_signal = Signal()
    replay_clue_signal = Signal()
    edit_clue_signal = Signal()
    fast_3s_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        self.btn_zoom = QPushButton("1. ZOOM POINT CELL / TV SPLASH")
        self.btn_zoom.setStyleSheet("background-color: #1E90FF; color: white; font-weight: bold; padding: 8px;")
        self.btn_zoom.clicked.connect(self.zoom_splash_signal.emit)
        layout.addWidget(self.btn_zoom)

        self.btn_reveal = QPushButton("2. REVEAL CLUE TEXT")
        self.btn_reveal.setStyleSheet("background-color: #8A2BE2; color: white; font-weight: bold; padding: 8px;")
        self.btn_reveal.clicked.connect(self.reveal_clue_signal.emit)
        layout.addWidget(self.btn_reveal)

        self.btn_answer = QPushButton("TOGGLE TV ANSWER")
        self.btn_answer.setStyleSheet("background-color: #333333; color: white; padding: 6px;")
        self.btn_answer.clicked.connect(self.toggle_answer_signal.emit)
        layout.addWidget(self.btn_answer)

        self.btn_close = QPushButton("CLOSE CLUE / RETURN TO BOARD")
        self.btn_close.setStyleSheet("background-color: #D2691E; color: white; font-weight: bold; padding: 8px;")
        self.btn_close.clicked.connect(self.close_clue_signal.emit)
        layout.addWidget(self.btn_close)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        # Nút Chỉnh câu hỏi
        self.btn_edit = QPushButton("CHỈNH CÂU HỎI")
        self.btn_edit.setStyleSheet("background-color: #2E8B57; color: white; font-weight: bold; padding: 6px;")
        self.btn_edit.clicked.connect(self.edit_clue_signal.emit)
        action_layout.addWidget(self.btn_edit)

        # Nút Chơi lại (Replay / Uncover)
        self.btn_replay = QPushButton("CHƠI LẠI (REPLAY)")
        self.btn_replay.setStyleSheet("background-color: #CD5C5C; color: white; font-weight: bold; padding: 6px;")
        self.btn_replay.clicked.connect(self.replay_clue_signal.emit)
        action_layout.addWidget(self.btn_replay)

        layout.addLayout(action_layout)

        # Nút Chạy thủ công nhanh trong 3 giây
        self.btn_fast_3s = QPushButton("CHẠY NHANH TOÀN BỘ (3 GIÂY)")
        self.btn_fast_3s.setStyleSheet("background-color: #FF8C00; color: black; font-weight: bold; padding: 8px;")
        self.btn_fast_3s.clicked.connect(self._run_fast_3s_sequence)
        layout.addWidget(self.btn_fast_3s)

    def _run_fast_3s_sequence(self):
        """Kích hoạt tuần tự Zoom -> Reveal -> Đóng chỉ trong đúng 3 giây."""
        self.fast_3s_signal.emit()
        self.zoom_splash_signal.emit()
        QTimer.singleShot(1500, self.reveal_clue_signal.emit)
        QTimer.singleShot(3000, self.close_clue_signal.emit)


__all__ = ["EditClueDialog", "ControllerGridCell", "ClueControlPanel"]
