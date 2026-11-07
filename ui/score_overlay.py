"""Standalone three-player score overlay.

Run with: python ui/score_overlay.py
Press F5 to choose a font. Edit names and scores directly in their panels.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFontDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


PLAYER_COLORS = (
    ("#153b63", "#2878a8", "#0c2138"),
    ("#5a3519", "#bd752c", "#301b10"),
    ("#3d285c", "#815bb5", "#211633"),
)


class ScoreOverlayWindow(QMainWindow):
    def __init__(self, linked=False):
        super().__init__()
        self.setWindowTitle("Open-J | Score Overlay")
        self.linked = linked
        self.resize(1200, 460)
        self.setMinimumSize(720, 320)
        self.current_font = QFont("Arial", 24, QFont.Bold)
        self.name_fields = []
        self.score_fields = []

        root = QWidget(self)
        root.setStyleSheet("background-color: #0b1018;")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(12)

        cards_layout = QGridLayout()
        cards_layout.setSpacing(16)
        for index, (start, end, border) in enumerate(PLAYER_COLORS):
            card = QFrame()
            card.setObjectName(f"player_card_{index}")
            card.setStyleSheet(
                f"QFrame#player_card_{index} {{ background-color: #111a26; "
                "border: 1px solid #26364a; border-radius: 12px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 14, 14, 14)
            card_layout.setSpacing(12)

            name = QLineEdit(f"PLAYER {index + 1}")
            name.setAlignment(Qt.AlignCenter)
            name.setPlaceholderText("Contestant name")
            name.setReadOnly(linked)
            name.setStyleSheet(self._field_style(start, end, border))

            score = QLineEdit("0")
            score.setAlignment(Qt.AlignCenter)
            score.setValidator(QIntValidator(-99999999, 99999999, score))
            score.setReadOnly(linked)
            score.setStyleSheet(self._field_style(end, start, border))
            score.setProperty("last_score", 0)
            if not linked:
                score.editingFinished.connect(lambda field=score: self._format_score(field))

            card_layout.addWidget(name, 1)
            card_layout.addWidget(score, 2)
            cards_layout.addWidget(card, 0, index)
            cards_layout.setColumnStretch(index, 1)
            self.name_fields.append(name)
            self.score_fields.append(score)

        layout.addLayout(cards_layout, 1)

        hint_text = "Linked to controller scores  |  F5: Choose font" if linked else "Edit names/scores directly  |  F5: Choose font"
        hint = QLabel(hint_text)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #8392a5; font-size: 12px;")
        layout.addWidget(hint)

        self.setCentralWidget(root)
        self._apply_font()

        self.font_shortcut = QShortcut(QKeySequence(Qt.Key_F5), self)
        self.font_shortcut.setContext(Qt.ApplicationShortcut)
        self.font_shortcut.activated.connect(self._choose_font)

    def set_players(self, players):
        for index, player_id in enumerate(("p1", "p2", "p3")):
            player = players.get(player_id, {})
            if index < len(self.name_fields):
                name = str(player.get("name", f"PLAYER {index + 1}"))
                self.name_fields[index].setText(name)

    def set_scores(self, scores):
        for index, player_id in enumerate(("p1", "p2", "p3")):
            if index < len(self.score_fields) and player_id in scores:
                score = int(scores[player_id])
                self.score_fields[index].setProperty("last_score", score)
                self.score_fields[index].setText(f"$ {score:,}")

    @staticmethod
    def _field_style(start, end, border):
        return (
            "QLineEdit {"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {start}, stop:1 {end});"
            f"border: 2px solid {border}; border-radius: 10px;"
            "color: #ffffff; padding: 8px;"
            "font-weight: 700;"
            "}"
            "QLineEdit:focus { border: 2px solid #e6edf3; }"
        )

    def _format_score(self, field):
        value = field.text().replace(",", "").replace("$", "").strip()
        try:
            score = int(value)
        except ValueError:
            score = field.property("last_score")
            QMessageBox.warning(self, "Invalid Score", "Enter a whole-number score.")
        field.setProperty("last_score", score)
        field.setText(f"$ {score:,}")

    def _choose_font(self):
        font, accepted = QFontDialog.getFont(self.current_font, self, "Choose score display font")
        if accepted:
            self.current_font = font
            self._apply_font()

    def _apply_font(self):
        name_font = QFont(self.current_font)
        name_font.setPointSize(max(12, int(self.current_font.pointSize() * 0.65)))
        score_font = QFont(self.current_font)
        score_font.setPointSize(max(18, int(self.current_font.pointSize() * 1.35)))
        for field in self.name_fields:
            field.setFont(name_font)
        for field in self.score_fields:
            field.setFont(score_font)


def main():
    app = QApplication(sys.argv)
    window = ScoreOverlayWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
