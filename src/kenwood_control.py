import sys
import time
from base64 import b64decode
from pathlib import Path

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt5.QtCore import QIODevice, QTimer, Qt, QEvent, QSettings, QSize
from PyQt5.QtWidgets import QMessageBox

# Опрос на приёме - всё состояние, на передаче - частота/TX и измерители
# IF повторяется через каждые две команды, чтобы частота обновлялась быстро
POLL_COMMANDS_RX = ["IF", "PC", "AN", "IF", "RA", "PS", "IF", "FR", "AC",
                    "IF", "DA", "AG0", "IF", "RG", "MG"]
POLL_COMMANDS_TX = ["IF", "SM0", "RM"]
POLL_INTERVAL_MS = 50
# Состояние связи: ответ старше LINK_SLOW_S - "SLOW", старше LINK_LOST_S - "NO ANSWER"
LINK_CHECK_MS = 200
LINK_SLOW_S = 0.6
LINK_LOST_S = 1.5
# После перестройки из программы частота из IF какое-то время игнорируется,
# чтобы старый ответ не откатил её назад
FREQ_HOLD_S = 0.3
# То же для ползунков AF/RF/MIC; изменения ползунка отправляются не чаще LEVEL_SEND_MS
LEVEL_HOLD_S = 0.5
LEVEL_SEND_MS = 60

# Минимальная длина ответа (без ';') для каждой команды
MIN_ANSWER_LEN = {"IF": 30, "PC": 5, "AN": 5, "RA": 4, "PS": 3, "FR": 3, "AC": 5, "RM": 7, "DA": 3,
                  "SM": 7, "AG": 6, "RG": 5, "MG": 5}

MODES = {"1": "LSB", "2": "USB", "3": "CW", "4": "FM", "5": "AM",
         "6": "FSK", "7": "CW-R", "9": "FSK-R"}
VFOS = {"0": "VFO A", "1": "VFO B", "2": "MEM"}
# Кнопки режимов (код команды MD) и режимы, в которых доступен DATA (LSB, USB, FM, AM)
MODE_BUTTONS = {"1": "LSB", "2": "USB", "3": "CW", "4": "FM"}
DATA_MODES = "1245"
# Регуляторы: ответ -> (надпись, команда установки, позиция значения в ответе, максимум)
LEVELS = {"AG": ("AF", "AG0", 3, 255), "RG": ("RF", "RG", 2, 255), "MG": ("MIC", "MG", 2, 100)}

# Файл настроек лежит рядом с программой (или с exe)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = str(APP_DIR / "kenwood_control.ini")

VERSION = "1.2.0"

DEFAULT_SETTINGS = {
    "power/steps": [str(w) for w in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 100)],
    "serial/port": "",
    "serial/baud": 9600,
    "serial/flow_control": True,    # false, если используется RS232 без RTS/CTS
    "window/on_top": False,
}

OFF_STYLE = ""
ON_STYLE = "background-color: rgb(60, 170, 70); color: white"
TX_STYLE = "background-color: red; color: white"
LINK_COLORS = {"ok": "rgb(60, 170, 70)", "slow": "rgb(230, 140, 0)",
               "lost": "red", "closed": "gray"}
POWER_COLUMNS = 7


def mono_font(size):
    """Моноширинный шрифт: Consolas, а если его нет - любой моноширинный"""
    font = QtGui.QFont("Consolas", size)
    font.setStyleHint(QtGui.QFont.TypeWriter)
    return font


class CompactButton(QtWidgets.QPushButton):
    """Кнопка шириной по надписи (у QPushButton минимум около 80 px)"""
    def sizeHint(self):
        width = self.fontMetrics().horizontalAdvance(self.text()) + 14
        return QSize(width, super().sizeHint().height())

    def minimumSizeHint(self):
        return self.sizeHint()


def format_freq(freq):
    """'00014175000' -> '14.175.000'"""
    return f"{int(freq):,}".replace(",", ".")


class KenwoodControl(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.load_settings()
        self.build_ui()
        self.setWindowTitle(f"Kenwood remote control {VERSION}")
        logo = QtGui.QPixmap()
        logo.loadFromData(b64decode(LOGO_PNG))
        self.setWindowIcon(QtGui.QIcon(logo))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.on_topC.isChecked())

        # Инициализация переменных состояния
        self.rx_buffer = ""
        self.is_power_on = False
        self.is_rx_on = False
        self.is_att_on = False
        self.is_active_vfoa = False
        self.is_active_vfob = False
        self.is_tuner_on = False
        self.is_tx_on = False
        self.is_data_on = False
        self.mode = ""
        self.count = 0
        self.current_freq = ""
        self.freq_hold_until = 0
        self.level_hold_until = {}
        self.pending_levels = {}
        self.last_answer_time = 0
        self.got_answer = False
        self.heartbeat = False
        self.ptt_active = False

        # Настройка последовательного порта
        self.serial = QSerialPort()
        self.serial.setBaudRate(self.baud)
        self.serial.readyRead.connect(self.on_read)
        self.serial.errorOccurred.connect(self.on_serial_error)
        self.serial.setFlowControl(
            QSerialPort.HardwareControl if self.flow_control else QSerialPort.NoFlowControl)

        # Циклический опрос трансивера
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.send_all_commands)

        # Отправка значений ползунков пачкой, а не на каждый шаг
        self.level_timer = QTimer(self)
        self.level_timer.setSingleShot(True)
        self.level_timer.setInterval(LEVEL_SEND_MS)
        self.level_timer.timeout.connect(self.send_levels)

        # Проверка связи с трансивером
        self.link_timer = QTimer(self)
        self.link_timer.setInterval(LINK_CHECK_MS)
        self.link_timer.timeout.connect(self.update_link_status)

        # Заполнение списка COM-портов
        self.refresh_ports()

        # Подключение сигналов кнопок
        self.connect_buttons()

        # Инициализация UI
        self.reset_ui_state()

        # Пробел (PTT) перехватывается на уровне приложения, чтобы он
        # не нажимал кнопку, на которой стоит фокус
        QtWidgets.QApplication.instance().installEventFilter(self)

        # Автоподключение к порту, с которым работали в прошлый раз
        if self.saved_port and self.comL.currentText() == self.saved_port:
            QTimer.singleShot(0, self.on_open)

    def load_settings(self):
        """Чтение kenwood_control.ini; недостающие параметры записываются со значениями по умолчанию"""
        self.settings = QSettings(SETTINGS_FILE, QSettings.IniFormat)
        for key, value in DEFAULT_SETTINGS.items():
            if not self.settings.contains(key):
                self.settings.setValue(key, value)

        steps = self.settings.value("power/steps")
        if isinstance(steps, str):
            steps = [steps]
        watts = set()
        for step in steps or []:
            if step.strip().isdigit() and 5 <= int(step) <= 100:
                watts.add(int(step))
            else:
                print(f"Bad power step in settings: {step!r}")
        watts = sorted(watts)
        if not watts:
            print("Bad power/steps in settings, using defaults")
            watts = [int(w) for w in DEFAULT_SETTINGS["power/steps"]]
        self.power_steps = watts

        self.saved_port = self.settings.value("serial/port", "", type=str)
        self.baud = self.settings.value("serial/baud", 9600, type=int)
        self.flow_control = self.settings.value("serial/flow_control", True, type=bool)

    def build_ui(self):
        """Создание виджетов окна"""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        main = QtWidgets.QVBoxLayout(central)
        main.setContentsMargins(6, 6, 6, 2)
        main.setSpacing(4)

        def button(text):
            btn = CompactButton(text)
            btn.setFont(mono_font(12))
            btn.setMinimumHeight(30)
            return btn

        def label(text, size=10):
            item = QtWidgets.QLabel(text)
            item.setFont(mono_font(size))
            return item

        # Частота, VFO и вид модуляции, кнопка питания
        top = QtWidgets.QHBoxLayout()
        self.lcdNumber = QtWidgets.QLCDNumber()
        self.lcdNumber.setMinimumHeight(44)
        self.lcdNumber.setAutoFillBackground(True)
        self.lcdNumber.setStyleSheet("color: rgb(255, 0, 0);")
        self.lcdNumber.setSmallDecimalPoint(True)
        self.lcdNumber.setDigitCount(8)
        self.lcdNumber.setSegmentStyle(QtWidgets.QLCDNumber.Flat)
        self.lcdNumber.setToolTip("Mouse wheel: 100 Hz step, Ctrl + wheel: 1 kHz step")
        top.addWidget(self.lcdNumber, 1)
        info = QtWidgets.QVBoxLayout()
        self.vfoL = label("")
        self.modeL = label("")
        for item, longest in ((self.vfoL, "VFO B"), (self.modeL, "FSK-R")):
            item.setMinimumWidth(item.fontMetrics().horizontalAdvance(longest))
        info.addWidget(self.vfoL)
        info.addWidget(self.modeL)
        top.addLayout(info)
        self.powerB = button("POWER")
        self.powerB.setMinimumHeight(44)
        top.addWidget(self.powerB)
        main.addLayout(top)

        # Измерители и текущая мощность
        meters = QtWidgets.QHBoxLayout()
        self.pwrP = QtWidgets.QProgressBar()
        self.swrP = QtWidgets.QProgressBar()
        for name, bar, tooltip in (("PWR", self.pwrP, "RF power meter (TX only)"),
                                   ("SWR", self.swrP, "SWR meter (TX only)")):
            bar.setRange(0, 30)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            bar.setToolTip(tooltip)
            meters.addWidget(label(name))
            meters.addWidget(bar, 1)
        self.driveL = label("", 12)
        self.driveL.setToolTip("Current TX power (PC)")
        meters.addWidget(self.driveL)
        main.addLayout(meters)

        # Регуляторы AF, RF и усиления микрофона
        levels = QtWidgets.QHBoxLayout()
        self.level_sliders = {}
        self.level_labels = {}
        for cmd, (name, _, _, maximum) in LEVELS.items():
            slider = QtWidgets.QSlider(Qt.Horizontal)
            slider.setRange(0, maximum)
            value = label("0")
            value.setMinimumWidth(value.fontMetrics().horizontalAdvance("255"))
            levels.addWidget(label(name))
            levels.addWidget(slider, 1)
            levels.addWidget(value)
            self.level_sliders[cmd] = slider
            self.level_labels[cmd] = value
        main.addLayout(levels)

        # Кнопки управления и выбор порта
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(4)
        self.rxantB = button("RX ant")
        self.attB = button("ATT")
        self.tuningB = button("Tuning")
        self.tuner_onB = button("AT on")
        self.up1B = button("+1kHz")
        self.down1B = button("-1kHz")
        self.up100B = button("+100Hz")
        self.down100B = button("-100Hz")
        for col, (top_btn, bottom_btn) in enumerate([
                (self.rxantB, self.attB), (self.tuningB, self.tuner_onB),
                (self.up1B, self.down1B), (self.up100B, self.down100B)]):
            grid.addWidget(top_btn, 0, col)
            grid.addWidget(bottom_btn, 1, col)
        port = QtWidgets.QHBoxLayout()
        self.comL = QtWidgets.QComboBox()
        self.refreshB = QtWidgets.QToolButton()
        self.refreshB.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.refreshB.setToolTip("Refresh port list")
        port.addWidget(self.comL, 1)
        port.addWidget(self.refreshB)
        grid.addLayout(port, 0, 4)
        self.openB = button("OPEN")
        grid.addWidget(self.openB, 1, 4)
        main.addLayout(grid)

        # Режимы модуляции и DATA
        modes = QtWidgets.QHBoxLayout()
        modes.setSpacing(4)
        self.mode_buttons = {}
        for code, name in MODE_BUTTONS.items():
            self.mode_buttons[code] = button(name)
            modes.addWidget(self.mode_buttons[code])
        self.dataB = button("DATA")
        self.dataB.setToolTip("DATA mode (LSB, USB, FM, AM)")
        modes.addWidget(self.dataB)
        main.addLayout(modes)

        # Кнопки мощности (ступени задаются в kenwood_control.ini)
        power_grid = QtWidgets.QGridLayout()
        power_grid.setSpacing(4)
        self.power_buttons = {}
        for i, watts in enumerate(self.power_steps):
            btn = button(f"{watts}W")
            power_grid.addWidget(btn, i // POWER_COLUMNS, i % POWER_COLUMNS)
            self.power_buttons[f"{watts:03d}"] = btn
        main.addLayout(power_grid)

        self.tx_onB = button("TX (SPACE)")
        self.tx_onB.setMinimumHeight(34)
        main.addWidget(self.tx_onB)

        # Строка состояния: связь, порт, "поверх всех окон"
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.onlineL = label("")
        self.onlineL.setMinimumWidth(self.onlineL.fontMetrics().horizontalAdvance("● NO ANSWER"))
        self.labelCOM = label("")
        self.on_topC = QtWidgets.QCheckBox("On top")
        self.on_topC.setChecked(self.settings.value("window/on_top", False, type=bool))
        status.addWidget(self.onlineL)
        status.addWidget(self.labelCOM, 1)
        status.addPermanentWidget(self.on_topC)

        self.setFixedSize(self.sizeHint())

    def connect_buttons(self):
        """Подключение всех обработчиков кнопок"""
        # Основные кнопки управления
        self.openB.clicked.connect(self.on_open)
        self.refreshB.clicked.connect(self.refresh_ports)
        self.rxantB.clicked.connect(self.on_rxant)
        self.attB.clicked.connect(self.on_att)
        self.powerB.clicked.connect(self.on_power)
        self.tuningB.clicked.connect(self.tuning)
        self.tuner_onB.clicked.connect(self.tuner_on)
        self.tx_onB.clicked.connect(self.on_tx_button)
        self.on_topC.toggled.connect(self.on_top)
        self.dataB.clicked.connect(self.on_data)
        for cmd, slider in self.level_sliders.items():
            slider.valueChanged.connect(lambda value, c=cmd: self.on_level(c, value))
        for code, btn in self.mode_buttons.items():
            btn.clicked.connect(lambda _, c=code: self.set_mode(c))

        # Кнопки управления мощностью
        for power, btn in self.power_buttons.items():
            btn.clicked.connect(lambda _, p=power: self.set_power(p))

        # Кнопки управления частотой
        self.up1B.clicked.connect(lambda: self.adjust_frequency(step=1000, direction=1))
        self.down1B.clicked.connect(lambda: self.adjust_frequency(step=1000, direction=-1))
        self.up100B.clicked.connect(lambda: self.adjust_frequency(step=100, direction=1))
        self.down100B.clicked.connect(lambda: self.adjust_frequency(step=100, direction=-1))

    def grey_all_power_buttons(self):
        """Сброс стиля всех кнопок мощности"""
        for btn in self.power_buttons.values():
            btn.setStyleSheet(OFF_STYLE)

    def set_state(self, widget, is_on):
        """Подсветка включённой функции"""
        widget.setStyleSheet(ON_STYLE if is_on else OFF_STYLE)

    def set_link(self, state, text, tooltip=""):
        self.onlineL.setText(text)
        self.onlineL.setToolTip(tooltip)
        self.onlineL.setStyleSheet(f"color: {LINK_COLORS[state]}")

    def update_link_status(self):
        """Индикатор связи: ответы идут, трансивер не завис, CTS в порядке"""
        if not self.serial.isOpen():
            self.set_link("closed", "● OFFLINE", "Port closed")
            return
        age = time.monotonic() - self.last_answer_time
        cts = bool(self.serial.pinoutSignals() & QSerialPort.ClearToSendSignal)
        if self.flow_control and not cts:
            self.set_link("lost", "● CTS LOW",
                          "TRX does not accept commands (CTS is low): check cable and TRX")
        elif age > LINK_LOST_S:
            self.set_link("lost", "● NO ANSWER", "No answers from TRX")
        elif not self.got_answer:
            self.set_link("slow", "● WAIT", "Waiting for the first answer from TRX")
        elif age > LINK_SLOW_S:
            self.set_link("slow", "● SLOW", f"Last answer {age * 1000:.0f} ms ago")
        else:
            # Точка мигает с каждым ответом на IF - видно, что трансивер отвечает
            dot = "●" if self.heartbeat else "○"
            self.set_link("ok", f"{dot} ONLINE", f"Last answer {age * 1000:.0f} ms ago")

    def set_meters(self, pwr=0, swr=0):
        self.pwrP.setValue(pwr)
        self.swrP.setValue(swr)

    def set_level(self, cmd, value):
        """Положение ползунка по данным трансивера (без отправки команды обратно)"""
        slider = self.level_sliders[cmd]
        slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(False)
        self.level_labels[cmd].setText(str(value))

    def set_levels_enabled(self, enabled):
        for slider in self.level_sliders.values():
            slider.setEnabled(enabled)

    def refresh_ports(self):
        """Обновление списка COM-портов с сохранением выбранного"""
        selected = self.comL.currentText() or self.saved_port
        self.comL.clear()
        self.comL.addItems([port.portName() for port in QSerialPortInfo().availablePorts()])
        index = self.comL.findText(selected)
        if index >= 0:
            self.comL.setCurrentIndex(index)

    def on_top(self, checked):
        """Окно поверх всех окон"""
        self.settings.setValue("window/on_top", checked)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    # Обработчики событий клавиатуры, мыши и окна
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease) and event.key() == Qt.Key_Space:
            if event.isAutoRepeat():
                return True
            if event.type() == QEvent.KeyPress:
                if self.isActiveWindow() and not self.ptt_active:
                    self.ptt_active = self.ptt_on()
                    return True
            elif self.ptt_active:
                self.release_ptt()
                return True
            if self.isActiveWindow():
                return True
        # Перестройка колесом мыши над индикатором частоты
        if obj is self.lcdNumber and event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta:
                step = 1000 if event.modifiers() & Qt.ControlModifier else 100
                self.adjust_frequency(step=step, direction=1 if delta > 0 else -1)
            return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        # При потере фокуса отпускание пробела не придёт - выключаем передачу
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.release_ptt()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.close_port()
        super().closeEvent(event)

    # Основные функции управления
    def send_command(self, command):
        """Отправка команды на радио"""
        if self.serial.isOpen():
            self.serial.write(f"{command};".encode())
            return True
        self.show_warning("Com port is closed!")
        return False

    def show_warning(self, text):
        """Показать предупреждение"""
        QMessageBox.warning(self, "Warning", text, QMessageBox.Ok)

    def send_all_commands(self):
        """Циклическая отправка команд запроса состояния"""
        if not self.serial.isOpen():
            self.timer.stop()
            return

        # Трансивер не забирает данные (CTS снят) - не копим запросы в буфере
        if self.serial.bytesToWrite() > 0:
            return

        commands = POLL_COMMANDS_TX if self.is_tx_on else POLL_COMMANDS_RX
        command = commands[self.count % len(commands)]
        self.count += 1
        # В CW и FSK команда DA возвращает ошибку
        if command == "DA" and self.mode not in DATA_MODES:
            return
        self.send_command(command)

    def parse_trx_data(self, data):
        """Анализ одного ответа трансивера (без ';')"""
        cmd = data[0:2]
        if len(data) < MIN_ANSWER_LEN.get(cmd, 2):
            print(f"Unexpected answer: {data!r}")
            return

        self.last_answer_time = time.monotonic()
        self.got_answer = True

        if cmd == "IF":
            self.heartbeat = not self.heartbeat
            freq = data[2:13]
            if freq.isdigit() and time.monotonic() > self.freq_hold_until:
                self.current_freq = freq
                self.lcdNumber.display(format_freq(freq))
            self.mode = data[29]
            self.update_mode_ui()
            was_tx = self.is_tx_on
            self.is_tx_on = data[28] == "1"
            self.tx_onB.setStyleSheet(TX_STYLE if self.is_tx_on else OFF_STYLE)
            if was_tx and not self.is_tx_on:
                self.set_meters()

        elif cmd == "PC":
            power = data[2:5]
            self.grey_all_power_buttons()
            btn = self.power_buttons.get(power)
            if btn:
                btn.setStyleSheet(ON_STYLE)
            if power.isdigit():
                self.driveL.setText(f"{int(power):3d} W")

        elif cmd == "SM":
            value = data[3:7]
            if value.isdigit() and self.is_tx_on:
                self.pwrP.setValue(int(value))

        elif cmd == "RM":
            value = data[3:7]
            if value.isdigit() and data[2] == "1":
                self.swrP.setValue(int(value))

        elif cmd in LEVELS:
            offset = LEVELS[cmd][2]
            value = data[offset:offset + 3]
            # Пока ползунок двигают, ответы трансивера его не трогают
            if (value.isdigit() and not self.level_sliders[cmd].isSliderDown()
                    and time.monotonic() > self.level_hold_until.get(cmd, 0)):
                self.set_level(cmd, int(value))

        elif cmd == "AN":
            self.is_rx_on = data[3] == "1"
            self.set_state(self.rxantB, self.is_rx_on)

        elif cmd == "RA":
            self.is_att_on = data[3] == "1"
            self.set_state(self.attB, self.is_att_on)

        elif cmd == "PS":
            self.is_power_on = data[2] == "1"
            self.set_state(self.powerB, self.is_power_on)

        elif cmd == "FR":
            self.is_active_vfoa = data[2] == "0"
            self.is_active_vfob = data[2] == "1"
            self.vfoL.setText(VFOS.get(data[2], ""))

        elif cmd == "DA":
            self.is_data_on = data[2] == "1"
            self.update_mode_ui()

        elif cmd == "AC":
            self.is_tuner_on = data[3] == "1"
            self.set_state(self.tuner_onB, self.is_tuner_on)

    def on_read(self):
        """Чтение данных из последовательного порта"""
        self.rx_buffer += bytes(self.serial.readAll()).decode("ascii", "ignore")

        # Последний кусок может быть неполным ответом - оставляем его в буфере
        *answers, self.rx_buffer = self.rx_buffer.split(";")
        for answer in answers:
            answer = answer.strip()
            if answer:
                print(answer)
                self.parse_trx_data(answer)

    def on_serial_error(self, error):
        """Порт пропал (например, отключили USB)"""
        if error == QSerialPort.ResourceError:
            self.close_port()
            self.show_warning("Connection to the port was lost!")

    # Обработчики кнопок
    def on_open(self):
        """Открытие/закрытие COM-порта"""
        if self.serial.isOpen():
            self.close_port()
        else:
            port = self.comL.currentText()
            self.serial.setPortName(port)
            if self.serial.open(QIODevice.ReadWrite):
                self.openB.setText("CLOSE")
                self.set_levels_enabled(True)
                self.labelCOM.setText(f"{port} · {self.baud}")
                self.settings.setValue("serial/port", port)
                self.rx_buffer = ""
                self.count = 0
                self.last_answer_time = time.monotonic()
                self.got_answer = False
                self.timer.start()
                self.link_timer.start()
            else:
                self.show_warning("Failed to open port!")

    def close_port(self):
        """Закрытие порта с выключением передачи"""
        self.release_ptt()
        self.timer.stop()
        if self.serial.isOpen():
            self.serial.waitForBytesWritten(200)
            self.serial.close()
        self.openB.setText("OPEN")
        self.reset_ui_state()

    def reset_ui_state(self):
        """Сброс состояния UI при закрытии порта"""
        self.count = 0
        self.current_freq = ""
        self.is_tx_on = False
        self.ptt_active = False
        self.link_timer.stop()
        self.set_link("closed", "● OFFLINE", "Port closed")
        self.set_meters()
        self.set_levels_enabled(False)
        self.pending_levels.clear()
        self.labelCOM.setText("Port closed")
        self.driveL.setText("  - W")
        self.vfoL.setText("")
        self.mode = ""
        self.is_data_on = False
        self.update_mode_ui()
        self.grey_all_power_buttons()
        for btn in [self.powerB, self.rxantB, self.attB, self.tuner_onB, self.tx_onB]:
            btn.setStyleSheet(OFF_STYLE)

    def on_rxant(self):
        """Переключение RX антенны"""
        if self.send_command("AN9" + ("1" if not self.is_rx_on else "0") + "9"):
            self.is_rx_on = not self.is_rx_on

    def on_att(self):
        """Переключение аттенюатора"""
        if self.send_command("RA0" + ("1" if not self.is_att_on else "0")):
            self.is_att_on = not self.is_att_on

    def on_power(self):
        """Включение/выключение питания"""
        if self.send_command("PS" + ("1" if not self.is_power_on else "0")):
            self.is_power_on = not self.is_power_on

    def set_power(self, power):
        """Установка мощности"""
        self.send_command(f"PC{power}")

    def adjust_frequency(self, step, direction):
        if len(self.current_freq) != 11:
            self.show_warning("No valid frequency data from TRX!")
            return
        if not (self.is_active_vfoa or self.is_active_vfob):
            self.show_warning("Select VFO A or VFO B on TRX!")
            return
        freq_hz = int(self.current_freq) + direction * step
        if freq_hz < 0 or freq_hz > 99999999999:
            self.show_warning("Frequency out of range!")
            return
        new_freq = f"{freq_hz:011d}"
        prefix = "FA" if self.is_active_vfoa else "FB"
        if self.send_command(f"{prefix}{new_freq}"):
            # Не ждём следующего IF, чтобы быстрые нажатия не терялись
            self.current_freq = new_freq
            self.freq_hold_until = time.monotonic() + FREQ_HOLD_S
            self.lcdNumber.display(format_freq(new_freq))
            print(f"{prefix}{new_freq}")

    def update_mode_ui(self):
        """Подсветка режима и DATA, надпись режима рядом с частотой"""
        data_available = self.mode in DATA_MODES
        if not data_available:
            self.is_data_on = False
        for code, btn in self.mode_buttons.items():
            self.set_state(btn, code == self.mode)
        self.dataB.setEnabled(data_available or not self.mode)
        self.set_state(self.dataB, self.is_data_on)
        self.modeL.setText(MODES.get(self.mode, "") + ("-D" if self.is_data_on else ""))

    def on_level(self, cmd, value):
        """Ползунок AF/RF/MIC сдвинут пользователем"""
        self.level_labels[cmd].setText(str(value))
        self.level_hold_until[cmd] = time.monotonic() + LEVEL_HOLD_S
        self.pending_levels[cmd] = value
        if not self.level_timer.isActive():
            self.level_timer.start()

    def send_levels(self):
        """Отправка последних значений ползунков"""
        for cmd, value in self.pending_levels.items():
            if self.serial.isOpen():
                self.serial.write(f"{LEVELS[cmd][1]}{value:03d};".encode())
        self.pending_levels.clear()

    def set_mode(self, code):
        """Выбор режима модуляции"""
        if self.send_command(f"MD{code}"):
            self.mode = code
            self.update_mode_ui()

    def on_data(self):
        """Включение/выключение режима DATA"""
        if self.send_command("DA" + ("1" if not self.is_data_on else "0")):
            self.is_data_on = not self.is_data_on
            self.update_mode_ui()

    def tuning(self):
        """Запуск настройки антенны"""
        self.send_command("AC111")

    def tuner_on(self):
        """Включение/выключение тюнера"""
        if self.send_command("AC" + ("110" if not self.is_tuner_on else "000")):
            self.is_tuner_on = not self.is_tuner_on

    def on_tx_button(self):
        """Переключение режима передачи"""
        if self.ptt_active:
            self.release_ptt()
        else:
            self.ptt_active = self.ptt_on()

    def release_ptt(self):
        """Выключение передачи, если она была включена из программы"""
        if self.ptt_active:
            self.ptt_active = False
            self.ptt_off()

    def ptt_on(self):
        """Включение передачи"""
        if self.send_command("TX"):
            self.tx_onB.setStyleSheet(TX_STYLE)
            print("Передача включена")
            return True
        return False

    def ptt_off(self):
        """Выключение передачи"""
        if self.serial.isOpen():
            self.serial.write(b"RX;")
        self.tx_onB.setStyleSheet(OFF_STYLE)
        print("Передача выключена")

# Иконка окна: logo.png, уменьшенный до 64x64
LOGO_PNG = (
    "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"
)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = KenwoodControl()
    window.show()
    sys.exit(app.exec())
