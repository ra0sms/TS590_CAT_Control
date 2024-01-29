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
is_att_on = False
count = 0


serial = QSerialPort()
timer = QTimer()
serial.setBaudRate(9600)
portList = []
ports = QSerialPortInfo().availablePorts()
for port in ports:
    portList.append(port.portName())
ui.comL.addItems(portList)


def grey_all_power_buttons():
    ui.powerB_15.setStyleSheet(grey_button_style)
    ui.powerB_14.setStyleSheet(grey_button_style)
    ui.powerB_13.setStyleSheet(grey_button_style)
    ui.powerB_12.setStyleSheet(grey_button_style)
    ui.powerB_11.setStyleSheet(grey_button_style)
    ui.powerB_10.setStyleSheet(grey_button_style)
    ui.powerB_9.setStyleSheet(grey_button_style)
    ui.powerB_8.setStyleSheet(grey_button_style)
    ui.powerB_7.setStyleSheet(grey_button_style)
    ui.powerB_6.setStyleSheet(grey_button_style)
    ui.powerB_5.setStyleSheet(grey_button_style)
    ui.powerB_4.setStyleSheet(grey_button_style)
    ui.powerB_3.setStyleSheet(grey_button_style)


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
        

def parse_power(power_data:str):
    if power_data[2:5]=="100":
        grey_all_power_buttons()
        ui.powerB_15.setStyleSheet(red_button_style)
    if power_data[2:5]=="065":
        grey_all_power_buttons()
        ui.powerB_14.setStyleSheet(red_button_style)
    if power_data[2:5]=="060":
        grey_all_power_buttons()
        ui.powerB_13.setStyleSheet(red_button_style)
    if power_data[2:5]=="055":
        grey_all_power_buttons()
        ui.powerB_12.setStyleSheet(red_button_style)
    if power_data[2:5]=="050":
        grey_all_power_buttons()
        ui.powerB_11.setStyleSheet(red_button_style)
    if power_data[2:5]=="045":
        grey_all_power_buttons()
        ui.powerB_10.setStyleSheet(red_button_style)
    if power_data[2:5]=="040":
        grey_all_power_buttons()
        ui.powerB_9.setStyleSheet(red_button_style)
    if power_data[2:5]=="035":
        grey_all_power_buttons()
        ui.powerB_8.setStyleSheet(red_button_style)
    if power_data[2:5]=="030":
        grey_all_power_buttons()
        ui.powerB_7.setStyleSheet(red_button_style)
    if power_data[2:5]=="025":
        grey_all_power_buttons()
        ui.powerB_6.setStyleSheet(red_button_style)
    if power_data[2:5]=="020":
        grey_all_power_buttons()
        ui.powerB_5.setStyleSheet(red_button_style)
    if power_data[2:5]=="015":
        grey_all_power_buttons()
        ui.powerB_4.setStyleSheet(red_button_style)
    if power_data[2:5]=="010":
        grey_all_power_buttons()
        ui.powerB_3.setStyleSheet(red_button_style)


def parse_trx_data():
    global is_rx_on, is_power_on, is_att_on
    if trx_data[0:2]=="IF":
        ui.lcdNumber.display(trx_data[5:16])
    if trx_data[0:2]=="PC":
        parse_power(trx_data)
    if trx_data[0:2]=="AN":
        if trx_data[3]=="1":
            ui.rxantB.setStyleSheet(red_button_style)
            is_rx_on = True
        if trx_data[3]=="0":
            is_rx_on = False
            ui.rxantB.setStyleSheet(grey_button_style)
    if trx_data[0:2]=="RA":
        if trx_data[3]=="1":
            is_att_on = True
            ui.attB.setStyleSheet(red_button_style)
        if trx_data[3]=="0":
            is_att_on = False
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
        ui.onlineL.setStyleSheet(red_button_style)
    else:
        ui.onlineL.setStyleSheet(grey_button_style)
   


def on_open():
    if serial.isOpen():
        ui.openB.setText("OPEN")
        ui.labelCOM.setText("Port closed")
        serial.close()
        grey_all_power_buttons()
        ui.powerB.setStyleSheet(grey_button_style)
        ui.rxantB.setStyleSheet(grey_button_style)
        ui.attB.setStyleSheet(grey_button_style)
        ui.onlineL.setStyleSheet(grey_button_style)
    else:
        serial.setFlowControl(True)     # comment it if you use RS232 port
        serial.setPortName(ui.comL.currentText())
        serial.open(QIODevice.ReadWrite)
        ui.labelCOM.setText("Port opened")
        ui.openB.setText("CLOSE")
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
    global is_att_on
    if serial.isOpen():
        if is_att_on:
            serial.write("RA00;".encode())
        else:
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


def on_10w():
    if serial.isOpen():
        serial.write("PC010;".encode())
    else:
        show_warning_messagebox()


def on_15w():
    if serial.isOpen():
        serial.write("PC015;".encode())
    else:
        show_warning_messagebox()


def on_20w():
    if serial.isOpen():
        serial.write("PC020;".encode())
    else:
        show_warning_messagebox()


def on_25w():
    if serial.isOpen():
        serial.write("PC025;".encode())
    else:
        show_warning_messagebox()


def on_30w():
    if serial.isOpen():
        serial.write("PC030;".encode())
    else:
        show_warning_messagebox()


def on_35w():
    if serial.isOpen():
        serial.write("PC035;".encode())
    else:
        show_warning_messagebox()


def on_40w():
    if serial.isOpen():
        serial.write("PC040;".encode())
    else:
        show_warning_messagebox()


def on_45w():
    if serial.isOpen():
        serial.write("PC045;".encode())
    else:
        show_warning_messagebox()


def on_50w():
    if serial.isOpen():
        serial.write("PC050;".encode())
    else:
        show_warning_messagebox()


def on_55w():
    if serial.isOpen():
        serial.write("PC055;".encode())
    else:
        show_warning_messagebox()


def on_60w():
    if serial.isOpen():
        serial.write("PC060;".encode())
    else:
        show_warning_messagebox()


def on_65w():
    if serial.isOpen():
        serial.write("PC065;".encode())
    else:
        show_warning_messagebox()


def on_100w():
    if serial.isOpen():
        serial.write("PC100;".encode())
    else:
        show_warning_messagebox()


serial.readyRead.connect(on_read)
ui.openB.clicked.connect(on_open)
ui.rxantB.clicked.connect(on_rxant)
ui.attB.clicked.connect(on_att)
ui.powerB.clicked.connect(on_power)
ui.powerB_3.clicked.connect(on_10w)
ui.powerB_4.clicked.connect(on_15w)
ui.powerB_5.clicked.connect(on_20w)
ui.powerB_6.clicked.connect(on_25w)
ui.powerB_7.clicked.connect(on_30w)
ui.powerB_8.clicked.connect(on_35w)
ui.powerB_9.clicked.connect(on_40w)
ui.powerB_10.clicked.connect(on_45w)
ui.powerB_11.clicked.connect(on_50w)
ui.powerB_12.clicked.connect(on_55w)
ui.powerB_13.clicked.connect(on_60w)
ui.powerB_14.clicked.connect(on_65w)
ui.powerB_15.clicked.connect(on_100w)



ui.show()
app.exec()