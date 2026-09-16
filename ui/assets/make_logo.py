import sys
from pathlib import Path
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QFont, QColor, QLinearGradient

app = QGuiApplication(sys.argv)

img = QImage(900, 450, QImage.Format_ARGB32)
img.fill(QColor(0, 0, 0, 0))

p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setRenderHint(QPainter.TextAntialiasing)

font = QFont("Impact", 110, QFont.Bold)
p.setFont(font)

rect = img.rect()
# Shadow
p.setPen(QColor(0, 0, 0, 220))
p.drawText(rect.adjusted(6, 6, 6, 6), 0x0084, "JEOPARDY!")

# Gold gradient
grad = QLinearGradient(0, 100, 0, 350)
grad.setColorAt(0.0, QColor("#FFF4A3"))
grad.setColorAt(0.4, QColor("#FFCC00"))
grad.setColorAt(1.0, QColor("#CC8800"))

p.setPen(QColor("#402000"))
p.setBrush(grad)
p.drawText(rect, 0x0084, "JEOPARDY!")
p.end()

out_path = Path("ui/assets/image/jeopardy_logo.png")
out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(str(out_path))
print("Successfully generated default logo:", out_path)

