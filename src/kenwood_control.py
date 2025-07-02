from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt5.QtCore import QIODevice, QTimer, Qt
from PyQt5.QtWidgets import QMessageBox

class KenwoodControl(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("src/form_design.ui", self)
        self.setWindowTitle("Kenwood remote control")
        self.setWindowIcon(QtGui.QIcon("logo.png"))
        
        # Инициализация переменных состояния
        self.trx_data = ""
        self.grey_button_style = "background-color: gray window"
        self.red_button_style = "background-color: red; border-color: black; border: none"
        self.is_power_on = False
        self.is_rx_on = False
        self.is_att_on = False
        self.is_active_vfoa = False
        self.is_active_vfob = False
        self.is_tuner_on = False
        self.is_tx_on = False
        self.count = 0
        self.current_freq = ""
        self.ptt_active = False
        
        # Настройка последовательного порта
        self.serial = QSerialPort()
        self.serial.setBaudRate(9600)
        self.serial.readyRead.connect(self.on_read)
        self.serial.setFlowControl(True)     # comment it if you use RS232 port
        
        self.timer = QTimer()
        
        # Заполнение списка COM-портов
        self.comL.addItems([port.portName() for port in QSerialPortInfo().availablePorts()])
        
        # Подключение сигналов кнопок
        self.connect_buttons()
        
        # Инициализация UI
        self.init_ui_state()

    def init_ui_state(self):
        """Инициализация начального состояния UI"""
        self.grey_all_power_buttons()
        self.onlineL.setStyleSheet(self.grey_button_style)
        self.tx_onB.setStyleSheet(self.grey_button_style)
        self.openB.setText("OPEN")
        self.labelCOM.setText("Port closed")

    def connect_buttons(self):
        """Подключение всех обработчиков кнопок"""
        # Основные кнопки управления
        self.openB.clicked.connect(self.on_open)
        self.rxantB.clicked.connect(self.on_rxant)
        self.attB.clicked.connect(self.on_att)
        self.powerB.clicked.connect(self.on_power)
        self.tuningB.clicked.connect(self.tuning)
        self.tuner_onB.clicked.connect(self.tuner_on)
        self.tx_onB.clicked.connect(self.on_tx_button)
        
        # Кнопки управления мощностью
        power_settings = {
            self.powerB_3: "010", self.powerB_4: "015", self.powerB_5: "020",
            self.powerB_6: "025", self.powerB_7: "030", self.powerB_8: "035",
            self.powerB_9: "040", self.powerB_10: "045", self.powerB_11: "050",
            self.powerB_12: "055", self.powerB_13: "060", self.powerB_14: "065",
            self.powerB_15: "100"
        }
        for btn, power in power_settings.items():
            btn.clicked.connect(lambda _, p=power: self.set_power(p))
            
        # Кнопки управления частотой
        self.up1B.clicked.connect(lambda: self.adjust_frequency(step=1000, direction=1))
        self.down1B.clicked.connect(lambda: self.adjust_frequency(step=1000, direction=-1))
        self.up100B.clicked.connect(lambda: self.adjust_frequency(step=100, direction=1))
        self.down100B.clicked.connect(lambda: self.adjust_frequency(step=100, direction=-1))

    def grey_all_power_buttons(self):
        """Сброс стиля всех кнопок мощности"""
        for btn in [
            self.powerB_3, self.powerB_4, self.powerB_5, self.powerB_6,
            self.powerB_7, self.powerB_8, self.powerB_9, self.powerB_10,
            self.powerB_11, self.powerB_12, self.powerB_13, self.powerB_14,
            self.powerB_15
        ]:
            btn.setStyleSheet(self.grey_button_style)

    # Обработчики событий клавиатуры
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not self.ptt_active:
            self.ptt_active = True
            self.ptt_on()
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and self.ptt_active:
            self.ptt_active = False
            self.ptt_off()
            event.accept()
        else:
            super().keyReleaseEvent(event)

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
            return
            
        commands = ["IF", "PC", "AN", "RA", "PS", "FR", "AC"]
        if self.count < len(commands):
            self.send_command(commands[self.count])
            self.count += 1
        else:
            self.count = 0
            
        self.timer.singleShot(50, self.send_all_commands)

    def parse_trx_data(self):
        """Анализ данных от трансивера"""
        if not self.trx_data:
            return
            
        cmd = self.trx_data[0:2]
        
        if cmd == "IF":
            self.current_freq = self.trx_data[5:16]
            self.lcdNumber.display(self.current_freq)
            
        elif cmd == "PC":
            power = self.trx_data[2:5]
            if power in ["010", "015", "020", "025", "030", "035", 
                        "040", "045", "050", "055", "060", "065", "100"]:
                self.grey_all_power_buttons()
                getattr(self, f"powerB_{int(power)//5 - 1}").setStyleSheet(self.red_button_style)
                
        elif cmd == "AN":
            self.is_rx_on = self.trx_data[3] == "1"
            self.rxantB.setStyleSheet(self.red_button_style if self.is_rx_on else self.grey_button_style)
            
        elif cmd == "RA":
            self.is_att_on = self.trx_data[3] == "1"
            self.attB.setStyleSheet(self.red_button_style if self.is_att_on else self.grey_button_style)
            
        elif cmd == "PS":
            self.is_power_on = self.trx_data[2] == "1"
            self.powerB.setStyleSheet(self.red_button_style if self.is_power_on else self.grey_button_style)
            
        elif cmd == "FR":
            self.is_active_vfoa = self.trx_data[2] == "0"
            self.is_active_vfob = self.trx_data[2] == "1"
            
        elif cmd == "AC":
            self.is_tuner_on = self.trx_data[3] == "1"
            self.tuner_onB.setStyleSheet(self.red_button_style if self.is_tuner_on else self.grey_button_style)
            
        self.onlineL.setStyleSheet(self.red_button_style if ";" in self.trx_data else self.grey_button_style)

    def on_read(self):
        """Чтение данных из последовательного порта"""
        rx = self.serial.read(100)
        self.trx_data += str(rx, 'utf-8')
        
        if ';' in self.trx_data:
            print(self.trx_data)
            self.parse_trx_data()
            self.trx_data = ""

    # Обработчики кнопок
    def on_open(self):
        """Открытие/закрытие COM-порта"""
        if self.serial.isOpen():
            self.serial.close()
            self.openB.setText("OPEN")
            self.labelCOM.setText("Port closed")
            self.reset_ui_state()
        else:
            self.serial.setPortName(self.comL.currentText())
            if self.serial.open(QIODevice.ReadWrite):
                self.openB.setText("CLOSE")
                self.labelCOM.setText("Port opened")
                self.send_all_commands()
            else:
                self.show_warning("Failed to open port!")

    def reset_ui_state(self):
        """Сброс состояния UI при закрытии порта"""
        self.count = 0
        self.grey_all_power_buttons()
        for btn in [self.powerB, self.rxantB, self.attB, self.onlineL]:
            btn.setStyleSheet(self.grey_button_style)

    def on_rxant(self):
        """Переключение RX антенны"""
        if self.send_command("AN90" + ("9" if not self.is_rx_on else "0")):
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
        """Изменение частоты с заданным шагом"""
        if not self.current_freq:
            self.show_warning("No data from TRX!")
            return
            
        try:
            pos = 4 if step == 1000 else 5  # Позиция изменяемой цифры
            value = int(self.current_freq[pos]) + direction
            if value < 0 or value > 9:
                return
                
            new_freq = self.current_freq[:pos] + str(value) + self.current_freq[pos+1:]
            prefix = "FA" if self.is_active_vfoa else "FB"
            self.send_command(f"{prefix}000{new_freq}")
        except Exception as e:
            print(f"Frequency adjustment error: {e}")
            self.show_warning("Frequency adjustment error!")

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
            self.ptt_off()
            self.ptt_active = False
        else:
            self.ptt_on()
            self.ptt_active = True

    def ptt_on(self):
        """Включение передачи"""
        if self.send_command("TX"):
            self.tx_onB.setStyleSheet(self.red_button_style)
            print("Передача включена")

    def ptt_off(self):
        """Выключение передачи"""
        if self.send_command("RX"):
            self.tx_onB.setStyleSheet(self.grey_button_style)
            print("Передача выключена")

if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    window = KenwoodControl()
    window.show()
    app.exec()