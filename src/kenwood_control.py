import PyQt5.QtWidgets, time, sched
from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt5.QtCore import QIODevice, QTimer, QEvent
from PyQt5.QtWidgets import QMessageBox, QWidget


app = QtWidgets.QApplication([])
ui = uic.loadUi("src/form_design.ui")
ui.setWindowTitle("Kenwood remote control")
ui.setWindowIcon(QtGui.QIcon("src/logo.png"))

SERVER_IP_ADDRESS = ""
trx_data = ""
grey_button_style = "background-color : gray window"
red_button_style = "background-color : red; border-color: black; border: none"
is_power_on = False
is_rx_on = False
count = 0


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
    global count
    count+=1
    if serial.isOpen():
        if count == 1:
            serial.write("IF;".encode())
        if count == 2:
            serial.write("PC;".encode())
        if count == 3:
            serial.write("AN;".encode())
        if count == 4:
            serial.write("RA;".encode())
        if count == 5:
            serial.write("PS;".encode())
            count = 0
        timer.singleShot(1000, send_all_commands)
        


def parse_trx_data():
    global is_rx_on, is_power_on
    if trx_data[0:2]=="IF":
        ui.lcdNumber.display(trx_data[5:16])
    if trx_data[0:2]=="PC":
        if trx_data[2:5]=="100":
            ui.powerB_15.setStyleSheet(red_button_style)
    if trx_data[0:2]=="AN":
        if trx_data[3]=="1":
            ui.rxantB.setStyleSheet(red_button_style)
            is_rx_on = True
        if trx_data[3]=="0":
            is_rx_on = False
            ui.rxantB.setStyleSheet(grey_button_style)
    if trx_data[0:2]=="RA":
        if trx_data[3]=="1":
            ui.attB.setStyleSheet(red_button_style)
        if trx_data[3]=="0":
            ui.attB.setStyleSheet(grey_button_style)
    if trx_data[0:2]=="PS":
        if trx_data[2]=="1":
            ui.powerB.setStyleSheet(red_button_style)
            is_power_on = True
        if trx_data[2]=="0":
            ui.powerB.setStyleSheet(grey_button_style)
            is_power_on = False

    

def on_read():
    global trx_data
    rx = serial.read(100)
    rxs = str(rx, 'utf-8')
    trx_data=trx_data+rxs
    #print(rxs)
    if rxs.find(';')!=-1:
        print(trx_data)
        parse_trx_data()
        trx_data=""
    #else:
        #trx_data=trx_data+rxs
        #print(trx_data)
    


def on_open():
    if serial.isOpen():
        ui.openB.setText("OPEN")
        ui.labelCOM.setText("COM port closed")
        serial.close()
    else:
        serial.setFlowControl(True)
        serial.setPortName(ui.comL.currentText())
        serial.open(QIODevice.ReadWrite)
        ui.labelCOM.setText("COM port opened")
        ui.openB.setText("CLOSE")
        serial.write("IF;".encode())
        send_all_commands()
        timer.singleShot(200, send_all_commands)


def on_rxant():
    global is_rx_on
    if serial.isOpen():
        if is_rx_on:
            print("rx off")
            serial.write("AN909;".encode())
        else:
            print("rx on")
            serial.write("AN919;".encode())
    else:
        show_warning_messagebox()


def on_att():
    if serial.isOpen():
        serial.write("RA01;".encode())
    else:
        show_warning_messagebox()


def on_power():
    global is_power_on
    if serial.isOpen():
        if is_power_on:
            serial.write("PS0;".encode())
        else:
            serial.write("PS1;".encode())
    else:
        show_warning_messagebox()


def on_if():
    if serial.isOpen():
        serial.write("IF;".encode())
    else:
        show_warning_messagebox()



serial.readyRead.connect(on_read)
ui.openB.clicked.connect(on_open)
ui.rxantB.clicked.connect(on_rxant)
ui.attB.clicked.connect(on_att)
ui.powerB.clicked.connect(on_power)
ui.powerB_3.clicked.connect(on_if)


ui.show()
app.exec()