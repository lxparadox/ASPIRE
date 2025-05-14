import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox
from PyQt5.QtGui import QPixmap, QIcon, QFont, QTextDocument, QTextCursor, QTextCharFormat
from PyQt5.QtCore import Qt
from pathlib import Path
import UV_HOME
import IR_HOME


class ASPIRE_home(QWidget):
    def __init__(self):
        super().__init__()
        project_root = Path(os.path.abspath(__file__)).parent.parent
        icon_path = project_root/"pictures"/"logo.png"
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"Icon file not found: {icon_path}")
        self.logo_pixmap = QPixmap(str(icon_path))
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ASPIRE")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon(self.logo_pixmap))
        self.setStyleSheet(self.styleSheet())
        self.setFixedSize(800, 600)

        # Main layout
        main_layout = QVBoxLayout()

        # Add a spacer to push the logo down slightly
        main_layout.addStretch(1)  # 上方弹性空间，使Logo稍微下移

        # Display software icon (假设 logo_pixmap 已定义)
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.logo_label)

        # Add a small spacer between logo and title
        main_layout.addSpacing(20)  # Logo和标题之间的间距

        # Software Name
        title_label = QLabel()
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setTextFormat(Qt.RichText)  # 启用富文本格式
        title_text = "A Software sPecialized In Radiation-related gene Extraction"
        formatted_text = self.format_text(title_text)  # 格式化文本
        title_label.setText(formatted_text)
        main_layout.addWidget(title_label)

        # Add a spacer between title and introduction
        main_layout.addSpacing(30)  # 标题和Introduction之间的间距

        # Software Introduction
        intro_label = QLabel(
            "Software Introduction\n\n"
            "    ASPIRE is an advanced text mining tool designed for the radiation field.\n "
            "    It extracts and analyzes genes related to ultraviolet and ionizing radiation "
            "from biomedical literature, providing intuitive visualizations and knowledge "
            "graphs for easy updates and analysis."
        )
        intro_label.setAlignment(Qt.AlignLeft)
        intro_label.setWordWrap(True)  # 自动换行
        intro_label.setFont(QFont("Segoe UI", 12))  # 设置Introduction字体
        main_layout.addWidget(intro_label)

        # Add a spacer between introduction and radiation type selection
        main_layout.addSpacing(30)  # Introduction和辐射类型选择之间的间距

        # Radiation Type Selection
        radiation_group = QGroupBox("Select Radiation Type")
        radiation_layout = QHBoxLayout()  # 水平布局
        UV_button = QPushButton("Ultraviolet")
        IR_button = QPushButton("Ionizing Radiation")

        # 设置按钮字体和大小
        button_font = QFont("Segoe UI", 14)
        UV_button.setFont(button_font)
        IR_button.setFont(button_font)

        # 设置按钮的固定大小
        UV_button.setFixedSize(200, 80)  # 设置按钮的宽度和高度
        IR_button.setFixedSize(200, 80)  # 设置按钮的宽度和高度

        # 添加按钮到布局
        radiation_layout.addWidget(UV_button)
        radiation_layout.addWidget(IR_button)
        radiation_group.setLayout(radiation_layout)
        main_layout.addWidget(radiation_group)

        # Add a spacer at the bottom for balance
        main_layout.addStretch(2)  # 下方弹性空间，使页面整体均衡

        # Connect button events
        UV_button.clicked.connect(self.on_UV_clicked)
        IR_button.clicked.connect(self.on_IR_clicked)

        # Set the main layout
        self.setLayout(main_layout)

    def format_text(self, text):
        # 创建 QTextDocument 和 QTextCursor
        document = QTextDocument()
        cursor = QTextCursor(document)

        # 设置默认字体
        default_format = QTextCharFormat()
        default_format.setFont(QFont("Segoe UI", 16))  # 设置默认字体大小

        # 设置加粗字体
        bold_format = QTextCharFormat()
        bold_format.setFont(QFont("Segoe UI", 24, QFont.Bold))  # 设置加粗字体大小

        # 遍历文本，根据字符是否大写应用不同的格式
        for char in text:
            if char.isupper():
                cursor.insertText(char, bold_format)
            else:
                cursor.insertText(char, default_format)

        return document.toHtml()

    def update_logo(self):
        # 根据窗口大小更新图标
        size = int(min(self.width(), self.height()) * 0.3)  # 转换为整数
        self.logo_label.setPixmap(self.logo_pixmap.scaled(size, size,
                                                          Qt.KeepAspectRatio,
                                                          Qt.SmoothTransformation))

    def resizeEvent(self, event):
        # 窗口大小变化时更新图标大小
        self.update_logo()
        super().resizeEvent(event)

    def styleSheet(self):
        return """
            QWidget {
                background-color: #f0f0f0;
                font-family: 'Segoe UI';
            }
            QLabel {
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #007BFF;
                color: #ffffff;
                border-radius: 5px;
                font-size: 20px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QGroupBox {
                border: 1px solid #ccc;
                margin-top: 10px;
                padding-top: 10px;
                font-size: 18px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """

    def on_UV_clicked(self):
        # close the window and open ASPIRE_UV from UV_home
        self.close()
        self.uv_window = UV_HOME.ASPIRE_UV()
        self.uv_window.show()

    def on_IR_clicked(self):
        self.close()
        self.uv_window = IR_HOME.ASPIRE_IR()
        self.uv_window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        ex = ASPIRE_home()
        ex.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"An error occurred: {e}")


