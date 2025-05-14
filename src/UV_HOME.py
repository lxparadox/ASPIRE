from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QApplication, QMessageBox)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from UV_UPDATE import ASPIRE_UV_update
import csv
from pathlib import Path
from dash_flask import *
from subprocess import Popen


class ASPIRE_UV(QWidget):
    def __init__(self):
        super().__init__()
        self.project_root = Path(os.path.abspath(__file__)).parent.parent
        self.logo_pixmap = QPixmap(str(self.project_root/"pictures"/"logo.png"))
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ASPIRE")
        self.setGeometry(100, 100, 800, 600)
        self.setFixedSize(800, 600)

        self.setWindowIcon(QIcon(self.logo_pixmap))

        self.setStyleSheet("""
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
        """)

        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        return_button = QPushButton("Go back to the main interface")     #add the back button    位置挪到右上角
        return_button.clicked.connect(self.return_to_main)
        top_layout.addWidget(return_button)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.create_title())
        main_layout.addWidget(self.create_operation_group())
        main_layout.addWidget(self.create_knowledge_graph_group())
        main_layout.addWidget(self.create_display_button())
        main_layout.addWidget(self.create_update_group())
        self.setLayout(main_layout)

    def create_title(self):
        title_label = QLabel("Ultraviolet-related Gene Knowledge Graph")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        return title_label

    def create_operation_group(self):
        operation_group = QGroupBox("Operation Options")
        operation_layout = QVBoxLayout()
        operation_text = QLabel(
            "You can perform the following operations:\n"
            "  1. Display the current knowledge graph.\n"
            "    View the latest UV-related genes and their relationships.\n"
            "  2. Update the knowledge graph.\n"
            "    Obtain the latest research data and regenerate the knowledge graph."
        )
        operation_text.setWordWrap(True)

        operation_layout.addWidget(operation_text)
        operation_group.setLayout(operation_layout)
        return operation_group

    def create_knowledge_graph_group(self):
        """
        创建知识图谱介绍分组
        """
        knowledge_graph_group = QGroupBox("Data Overview")
        knowledge_graph_layout = QVBoxLayout()

        # 加载动态统计信息
        stats_text = self.get_knowledge_graph_statistics()
        knowledge_graph_info = QLabel(stats_text)
        knowledge_graph_info.setWordWrap(True)  # 支持换行
        knowledge_graph_layout.addWidget(knowledge_graph_info)

        knowledge_graph_group.setLayout(knowledge_graph_layout)
        return knowledge_graph_group

    def load_json(self, file_path):
        """
        加载 JSON 文件
        :param file_path: JSON 文件路径
        :return: JSON 数据（字典），加载失败返回空字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading JSON file {file_path}: {e}")
            return {}

    def get_knowledge_graph_statistics(self):
        """
        读取 CSV 和 JSON 文件，生成知识图谱统计信息
        """
        csv_file_path = self.project_root/"data"/"UV_all_data.csv"
        gene_info_path = self.project_root/"data"/"UV_gene_info_show.csv"
        json_file_path = self.project_root/"data"/"latest_period_UV.json"

        try:
            # 自动检测分隔符
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                dialect = csv.Sniffer().sniff(file.read(1024))
                file.seek(0)  # 重置文件指针
                df = pd.read_csv(file, delimiter=dialect.delimiter)  # 动态设置分隔符

            # 检查列名是否正确，否则抛出异常
            required_columns = ['PMID', 'Gene ID', 'answer']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")

            # 读取基因信息文件
                with open(gene_info_path, 'r', encoding='utf-8') as file:
                    dialect = csv.Sniffer().sniff(file.read(1024))
                    file.seek(0)
                    gene_info_df = pd.read_csv(file, delimiter=dialect.delimiter)

            # 获取所有有效基因ID（存在于UV_gene_info_show.csv中的基因）
            valid_gene_ids = set(gene_info_df['geneID'].unique())

            # 筛选出answer为T且Gene ID在有效基因中的记录
            valid_t_df = df[(df['answer'] == "T") & (df['Gene ID'].isin(valid_gene_ids))]
            # 统计信息
            unique_pmids = valid_t_df['PMID'].nunique()  # 唯一 PMID 个数
            count_t = len(valid_t_df)  # 'answer' 为 T 的行数
            unique_gene_ids_T = valid_t_df['Gene ID'].nunique()

            # 加载 JSON 文件获取时间信息
            json_data = self.load_json(json_file_path)
            time_info = json_data.get("end", "Unknown")  # 获取结束时间（end）

            # 返回统计文本
            return (f"Included literature: {unique_pmids} papers\n"
                    f"Included evidence: {count_t} sentences\n"
                    f"UV-related genes: {unique_gene_ids_T} genes")

        except Exception as e:
            # 错误处理
            print(f"Error processing files: {e}")
            return "Failed to load knowledge graph information, please check if the file exists and is formatted correctly."

    def create_display_button(self):
        """
        创建展示按钮，并绑定点击事件。
        """
        display_button = QPushButton("Display Current Knowledge Graph")
        display_button.clicked.connect(self.update_and_display)
        return display_button

    def update_and_display(self):
        # 定义新的文件路径
        new_gene_info_path = self.project_root/"data"/'UV_gene_info_show.csv'
        new_gene_pathway_path = self.project_root/"data"/'UV_gene_pathway_results.csv'
        new_all_data_path = self.project_root/"data"/'UV_all_data.csv'

        print("Passing the following paths to the backend:")
        print(f"Gene info path: {new_gene_info_path}")
        print(f"Gene pathway path: {new_gene_pathway_path}")
        print(f"All data path: {new_all_data_path}")

        # 使用非阻塞的方式启动脚本
        try:
            Popen([
                sys.executable,
                "dash_flask.py",
                new_gene_info_path,
                new_gene_pathway_path,
                new_all_data_path
            ])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to execute backend script: {e}")

    def load_last_update_info(self):
        file_path = self.project_root/"data"/"latest_period_UV.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                start = data.get("start", "Unknown Start Date")
                end = data.get("end", "Unknown End Date")
                return f"{start} to {end}"
        except Exception as e:
            return f"Failed to get the last update time: {str(e)}"

    def create_update_group(self):
        update_group = QGroupBox("Update Verification")
        update_layout = QVBoxLayout()
        update_info_label = QLabel("Do you need to update the Ultraviolet-related gene knowledge graph?")
        update_layout.addWidget(update_info_label)

        last_update_info = self.load_last_update_info()
        update_label = QLabel("Last retrieval range: " + last_update_info)
        update_layout.addWidget(update_label)

        yes_button = QPushButton("Update Knowledge Graph")
        yes_button.clicked.connect(self.show_new_window)
        update_layout.addWidget(yes_button)
        update_group.setLayout(update_layout)
        return update_group

    def show_new_window(self):
        try:
            self.new_window = ASPIRE_UV_update()
            self.new_window.show()
        except Exception as e:
            show_error_message(self, "Error", f"Error occurred while opening a new window: {e}")

    def return_to_main(self):
        self.close()
        from MAIN_HOME import ASPIRE_home
        self.main_window = ASPIRE_home()
        self.main_window.show()

def show_error_message(parent, title, message):
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ASPIRE_UV()
    ex.show()
    sys.exit(app.exec_())
