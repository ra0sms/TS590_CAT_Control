import PyQt5.QtWidgets, time, sched
from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt5.QtCore import QIODevice, QTimer, QEvent
from PyQt5.QtWidgets import QMessageBox, QWidget


app = QtWidgets.QApplication([])
ui = uic.loadUi("form_design.ui")
ui.setWindowTitle("Kenwood remote control")
ui.setWindowIcon(QtGui.QIcon("logo.png"))

SERVER_IP_ADDRESS = ""
trx_data = ""
grey_button_style = "background-color : gray window"
red_button_style = "background-color : red; border-color: black; border: none"


serial = QSerialPort()
timer = QTimer()
serial.setBaudRate(9600)
portList = []
ports = QSerialPortInfo().availablePorts()
for port in ports:
    portList.append(port.portName())
ui.comL.addItems(portList)


def show_warning_messagebox():
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setText("Com port is closed!")
    msg.setWindowTitle("Warning")
    msg.setStandardButtons(QMessageBox.Ok)
    retval = msg.exec_()


def send_all_commands():
    if serial.isOpen():
        serial.write("IF;".encode())
        time.sleep(0.05)
        serial.write("PC;".encode())
        time.sleep(0.05)
        serial.write("AN;".encode())
        time.sleep(0.05)
        serial.write("RA;".encode())
        time.sleep(0.05)
        serial.write("PS;".encode())
        time.sleep(0.05)
        timer.singleShot(1000, send_all_commands)
        


def parse_trx_data():
    if trx_data[0:2]=="IF":
        ui.lcdNumber.display(trx_data[5:16])
    if trx_data[0:2]=="PC":
        if trx_data[2:5]=="100":
            ui.powerB_15.setStyleSheet(red_button_style)
    if trx_data[0:2]=="AN":
        if trx_data[3]=="1":
            ui.rxantB.setStyleSheet(red_button_style)
        if trx_data[3]=="0":
            ui.rxantB.setStyleSheet(grey_button_style)
    if trx_data[0:2]=="RA":
        pass
    if trx_data[0:2]=="PS":
        pass

    

def on_read():
    global trx_data
    rx = serial.read(30)
    rxs = str(rx, 'utf-8')
    if not rxs.find(';'):
        print(trx_data)
        parse_trx_data()
        trx_data=""
    else:
        trx_data=trx_data+rxs
    


def on_open():
    if serial.isOpen():
        ui.openB.setText("OPEN")
        ui.labelCOM.setText("COM port closed")
        serial.close()
    else:
        serial.setPortName(ui.comL.currentText())
        serial.open(QIODevice.ReadWrite)
        ui.labelCOM.setText("COM port opened")
        ui.openB.setText("CLOSE")
        send_all_commands()
        timer.singleShot(1000, send_all_commands)


def on_rxant():
    if serial.isOpen():
        serial.write("AN919;".encode())
    else:
        show_warning_messagebox()




serial.readyRead.connect(on_read)
ui.openB.clicked.connect(on_open)
ui.rxantB.clicked.connect(on_rxant)


ui.show()
app.exec()