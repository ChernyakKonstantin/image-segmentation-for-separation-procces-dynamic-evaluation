# TODO Добавить темную тему
# TODO Добавить печать тренда

import datetime as dt
import pickle
import socket
import sys
from typing import Any
import os
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QActionGroup, QMenu, QPushButton, QLabel
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt5.QtWidgets import QHBoxLayout, QMenuBar, QStatusBar, QVBoxLayout
from PyQt5.QtWidgets import QApplication, QCalendarWidget, QCheckBox, QFileDialog, QLabel, QMainWindow, QTimeEdit
import matplotlib.pyplot as plt
from interactive_chart import TimeSeriesChart
from interactive_mask_display import InteractiveMaskDisplay
import csv

class Client:
    """Класс TCP-клиента, опрашивающего сервер для получения результатов сегментации."""

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port

    def receive(self):
        """Метод получения данных от сервера."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.ip, self.port))
            request = []
            while True:
                packet = s.recv(4096)
                if not packet:
                    break
                request.append(packet)
            package = pickle.loads(b"".join(request))
            # image, mask, values = package
            image, values = package

        cur_datetime = dt.datetime.now()
        # return image, mask, cur_datetime, values
        return image, cur_datetime, values


class CentralWidget(QWidget):
    """Обязательный виджет Qt-приложения. Используется в QMainWindow."""

    empty_message = 'Unknown'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.chart = TimeSeriesChart()
        self.img = InteractiveMaskDisplay()
        self.segmented_img = InteractiveMaskDisplay()

        self.oil_label = QLabel(f'Oil fraction: {self.empty_message}')
        self.emulsion_label = QLabel(f'Emulsion fraction: {self.empty_message}')
        self.water_label = QLabel(f'Water fraction: {self.empty_message}')

        label_layout = QVBoxLayout()
        label_layout.addWidget(self.oil_label)
        label_layout.addWidget(self.emulsion_label)
        label_layout.addWidget(self.water_label)

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.img)
        h_layout.addWidget(self.segmented_img)
        h_layout.addLayout(label_layout)
        h_layout.setAlignment(Qt.AlignLeft)

        v_layout = QVBoxLayout()
        v_layout.addWidget(self.chart)
        v_layout.addLayout(h_layout)

        self.setLayout(v_layout)

    def set_text(self, values: tuple):
        self.oil_label.setText(f'Oil fraction: {round(values[0], 1)}%')
        self.emulsion_label.setText(f'Emulsion fraction: {round(values[1], 1)}%')
        self.water_label.setText(f'Water fraction: {round(values[2], 1)}%')


class MainWindow(QMainWindow):
    """Обязательный виджет Qt-приложения. Используется в QApplication."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('Separator Dynamics Estimator')

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Server is disconnected')

        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)
        self.menu_bar.addAction('Quit', self.close)
        self.menu_bar.addSeparator()

        self.central_widget = CentralWidget()
        self.setCentralWidget(self.central_widget)

        self.showFullScreen()

    def add_menubar_action(self, action_name, callback):
        self.menu_bar.addAction(action_name, callback)
        self.menu_bar.addSeparator()


class Application(QApplication):
    LOG_DIRECTORY = 'logs'
    FIELD_NAMES = ('oil', 'emulsion', 'water')

    file_path = None
    call_period = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_logger()
        self.main_window = MainWindow()
        self.main_window.add_menubar_action('Connect to server', self._tcp_client_setup)
        self.main_window.add_menubar_action('Save chart', self._handle_image_save)

    def _setup_logger(self):
        """Инициализация файла лога текущего эксперимента"""
        if not os.path.exists(self.LOG_DIRECTORY):
            os.mkdir(self.LOG_DIRECTORY)
        current_date = dt.datetime.now().strftime('%d-%m-%y-%H-%M')
        filename = f'{current_date}_experiment_log.csv'
        self.file_path = os.path.join(self.LOG_DIRECTORY, filename)
        log_file = open(self.file_path, 'w')
        log_file.close()

    def _handle_log_write(self, values: dict):
        with open(self.file_path, 'a+', newline='') as log_file:
            writer = csv.DictWriter(log_file, fieldnames=self.FIELD_NAMES)
            writer.writerow(values)

    def _tcp_client_setup(self):
        """Инициализация TCP-клиента"""
        self._tcp_client = Client('localhost', 80)
        self._tcp_client_timer = QTimer()
        self._tcp_client_timer.setInterval(self.call_period)
        self._tcp_client_timer.timeout.connect(self._handle_tcp_client_request)
        self._tcp_client_timer.start()

    def _handle_tcp_client_request(self):
        """Обработчик TCP-клиента"""
        try:
            image, cur_time, values = self._tcp_client.receive()
            self.main_window.central_widget.chart.add_new_values((cur_time, values))
            self.main_window.central_widget.set_text(values)
            self.main_window.central_widget.segmented_img.draw(image)
            self.main_window.status_bar.showMessage('Server is connected')
        except ConnectionRefusedError:
            self._tcp_client_timer.stop()
            self.main_window.status_bar.showMessage('Server is disconnected')

    def _handle_image_save(self):
        filename = QFileDialog.getSaveFileName(None, 'Open File', './', "Image (*.png *.jpg *jpeg)")[0]

        with open(self.file_path, 'r') as log_file:
            reader = csv.DictReader(log_file, fieldnames=self.FIELD_NAMES)
            data_to_plot = {name: [] for name in self.FIELD_NAMES}
            for row in reader:
                for key, value in row.items():
                    data_to_plot[key].append(value)

        fig, ax = plt.subplots(1)
        for key, value in data_to_plot.items():
            ax.plot(value, label=key)
        ax.set_xlabel('Time, minutes')
        ax.set_ylabel('Fraction, %')
        ax.grid(True)
        ax.legend()

        fig.savefig(filename)


app = Application(sys.argv)
sys.exit(app.exec_())
