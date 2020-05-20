#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Power Profiler

Requirement:

    ```
    pip install pyserial
    pip install PyQt5
    # or `pip install PySide2`. PySide 2 does't work with Python 3.8.0
    pip install https://github.com/pyqtgraph/pyqtgraph/archive/develop.zip
    ```
"""

import time
import traceback
import sys
import serial
from serial.tools import list_ports
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters


MAX_HISTORY = 1 << 20

# I = 1.3524 * ADC / Gain (mA)
# SEL=0, Gain=1.98, Rang: 0 - 690mA, Resolution: 5mA
# SEL=1, Gain=119.52, Rang: 0 - 11mA, Resolution: 50uA
GAIN_SELECT = 0
SAMPLE_RATE = 60000     # Hz
LOG2AVG     = 1

# using baud rate to configure voltmeter
BAUDRATE = 0x40000000 | (GAIN_SELECT << 29) | (7 << 26) | (LOG2AVG << 20) | int(SAMPLE_RATE)

BETA = (1.3524 / 1.98, 1.3524 / 119.52)
AVERAGE_N = (1 << LOG2AVG)


class Probe(pg.QtCore.QThread):
    error = pg.QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        self.done = False
        self.data = np.empty((4, 1 << 12))
        self.index = 0
        self.n = 0
        self._gain = GAIN_SELECT
        self.queue = []

    def run(self):
        for p in list_ports.comports():
            if p[2].upper().startswith('USB VID:PID=0D28:0204'):
                port = p[0]
                break
        else:
            print('No device found')
            self.error.emit(1)
            return

        print('Open {}'.format(port))
        device = serial.Serial(port=port,
                               baudrate=BAUDRATE,
                               bytesize=8,
                               parity='N',
                               stopbits=1,
                               timeout=1)

        device.write(b's')  # stop
        time.sleep(1)
        device.reset_input_buffer()
        device.write(str(self.gain).encode())
        device.write(b'g')  # go

        n = AVERAGE_N
        bytes_count = 0
        samples_count = 0
        t1 = time.time()

        # output = 'data.csv'
        # self.f = open(output, 'w')
        # self.f.write('t,I,U\n')
        
        current_gain = self.gain
        while not self.done:
            try:
                if self.queue:
                    command = self.queue.pop(0)
                    device.write(command)
                    # print('tx:{}'.format(command))
                    current_gain = self.gain
                raw = device.read(16)
                if not raw:
                    print('no data')
                    continue
                for i in range(0, 16, 2):
                    channel = raw[i] & 0x3F
                    if channel & 0x38:
                        print('bad data')
                        # device.read(1)
                        continue

                    current = (raw[i +1 ] << 2) | (raw[i] >> 6)
                    current = current * BETA[current_gain]
                    if current > 0:
                        current -= 0.0165
                    self.process(current, AVERAGE_N)
                    
            except IOError:
                traceback.print_exc()
                self.error.emit(2)
                break
            except ValueError:
                print(raw)
                traceback.print_exc()
                break

            bytes_count += 16
            samples_count += n*8
            t2 = time.time()
            dt = t2 - t1
            # if samples_count >= SAMPLE_RATE:
            if dt >= 1.:
                t1 = t2
                print('data rate: {} bytes/s, samples: {}, dt: {}'.format(bytes_count, samples_count, dt / 1000000))
                bytes_count = 0
                samples_count = 0

        device.write(b'e')
        device.close()
        # np.savetxt(self.f, self.data[1:,:self.index].T, ['%d', '%f', '%d'], ',')

    def process(self, current, n):
        if self.index & 0xFFF == 0:
            print(current)

        def index_inc():
            self.index += 1
            if self.index < self.data.shape[1]:
                return

            if self.index < MAX_HISTORY:
                buffer = np.concatenate(
                    (self.data, np.empty(self.data.shape)), axis=1)
                self.data = buffer
            else:
                half = MAX_HISTORY >> 1
                # np.savetxt(self.f, self.data[1:,:half].T, ['%d', '%f', '%d'], ',')
                self.data[:,:half] = self.data[:,half:]
                self.index -= half

        # when n > 1, `current` and `voltage` are the average of n samples
        if n > 1:
            self.data[0][self.index] = (self.n + 1) / SAMPLE_RATE
            self.data[1][self.index] = self.n + 1
            self.data[2][self.index] = current
            # self.data[3][self.index] = voltage
            index_inc()
        self.n += n
        self.data[0][self.index] = self.n / SAMPLE_RATE
        self.data[1][self.index] = self.n
        self.data[2][self.index] = current
        # self.data[3][self.index] = voltage
        index_inc()

    def get(self):
        return self.data, self.index

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, g):
        self._gain = g
        self.queue.append(str(g).encode())

    def start(self):
        self.done = False
        super().start()

    def stop(self):
        self.done = True
        self.wait(2)


class MainWindow(pg.QtGui.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_MediaPlay))
        self.setWindowTitle('Power Profiler')
        self.resize(1200, 720)
        self.widget = pg.PlotWidget()
        self.setCentralWidget(self.widget)

        self.widget.setLabel('left', 'I')
        self.widget.setLabel('bottom', 't/s')
        self.widget.showButtons()
        self.widget.setXRange(0, 10., padding=0)
        self.widget.setYRange(0, 10., padding=0)
        # self.widget.setLimits(minYRange=0, maxYRange=1024, yMin=0, yMax=1024)
        self.widget.setMouseEnabled(True, False)
        # self.widget.setAutoPan(x=True)
        # self.widget.enableAutoRange(x=True)
        # line = pg.InfiniteLine(
        #     pos=512, angle=0, movable=True, bounds=[0, 1024])
        # self.widget.addItem(line)
        self.widget.showGrid(x=True, y=True, alpha=0.5)
        self.plot = self.widget.plot()
        self.plot.setPen((0, 255, 0))

        self.toolbar = self.addToolBar('toolbar')
        self.toolbar.setMovable(False)

        startAction = pg.QtGui.QAction('▶️', self)
        startAction.setToolTip('Run')
        # startAction.setShortcut('@')
        startAction.setCheckable(True)
        startAction.setChecked(True)
        startAction.toggled.connect(self.start)
        self.toolbar.addAction(startAction)

        # ❆❄️
        freezeAction = pg.QtGui.QAction('❄️', self)
        freezeAction.setToolTip('Freeze (Space)')
        freezeAction.setShortcut(' ')
        freezeAction.setCheckable(True)
        freezeAction.setChecked(False)
        freezeAction.toggled.connect(self.freeze)
        self.toolbar.addAction(freezeAction)

        saveAction = pg.QtGui.QAction('💾', self)
        saveAction.setToolTip('Save (Ctrl+S)')
        saveAction.setShortcut('Ctrl+S')
        saveAction.triggered.connect(self.save)
        self.toolbar.addAction(saveAction)

        # 🍳β🧐
        gainAction = pg.QtGui.QAction('🧐', self)
        gainAction.setToolTip('Change Gain (.)')
        gainAction.setShortcut('.')
        gainAction.setCheckable(True)
        gainAction.setChecked(False)
        gainAction.toggled.connect(self.set_gain)
        self.toolbar.addAction(gainAction)

        autoAction = pg.QtGui.QAction('A', self)
        autoAction.setToolTip('Auto-Adjust (a)')
        autoAction.setShortcut('a')
        # autoAction.setCheckable(True)
        autoAction.setChecked(False)
        autoAction.triggered.connect(self.adjust)
        self.toolbar.addAction(autoAction)
    
        # # 🔍🔎
        # xZoomInAction = pg.QtGui.QAction('🔍⇆', self)
        # xZoomInAction.setToolTip('X Zoom In ([)')
        # xZoomInAction.setShortcut('[')
        # xZoomInAction.triggered.connect(self.zoomInX)
        # self.toolbar.addAction(xZoomInAction)

        xZoomInShortcut = pg.QtGui.QShortcut('[', self)
        xZoomInShortcut.activated.connect(self.zoomInX)

        # xZoomOutAction = pg.QtGui.QAction('🔍↔', self)
        # xZoomOutAction.setToolTip('X Zoom Out (])')
        # xZoomOutAction.setShortcut(']')
        # xZoomOutAction.triggered.connect(self.zoomOutX)
        # self.toolbar.addAction(xZoomOutAction)

        xZoomOutShortcut = pg.QtGui.QShortcut(']', self)
        xZoomOutShortcut.activated.connect(self.zoomOutX)

        yZoomInAction = pg.QtGui.QAction('🔍-', self)
        yZoomInAction.setToolTip('Y Zoom In (-)')
        yZoomInAction.setShortcut('-')
        yZoomInAction.triggered.connect(self.zoomInY)
        self.toolbar.addAction(yZoomInAction)

        yZoomOutAction = pg.QtGui.QAction('🔍+', self)
        yZoomOutAction.setToolTip('Y Zoom Out (+)')
        yZoomOutAction.setShortcut('=')
        yZoomOutAction.triggered.connect(self.zoomOutY)
        self.toolbar.addAction(yZoomOutAction)

        # 🠈🠉🠊🠋←↑→↓⇇⇈⇉⇊
        leftAction = pg.QtGui.QAction('←', self)
        # leftAction.setIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_ArrowLeft))
        # leftAction.setShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Left))
        leftAction.triggered.connect(self.moveLeft)
        self.toolbar.addAction(leftAction)
        leftAction.setVisible(False)

        leftShortcut = pg.QtGui.QShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Left), self)
        leftShortcut.activated.connect(self.moveLeft)

        rightAction = pg.QtGui.QAction('→', self)
        # rightAction.setIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_ArrowRight))
        rightAction.setShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Right))
        rightAction.triggered.connect(self.moveRight)
        self.toolbar.addAction(rightAction)
        rightAction.setVisible(False)

        rightShortcut = pg.QtGui.QShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Right), self)
        rightShortcut.activated.connect(self.moveRight)
    
        upAction = pg.QtGui.QAction('↑', self)
        # upAction.setIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_ArrowUp))
        upAction.setToolTip('Move Up (↑)')
        upAction.setShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Up))
        upAction.triggered.connect(self.moveUp)
        self.toolbar.addAction(upAction)

        downAction = pg.QtGui.QAction('↓', self)
        # downAction.setIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_ArrowDown))
        downAction.setToolTip('Move Down (↓)')
        downAction.setShortcut(pg.QtGui.QKeySequence(pg.QtCore.Qt.Key_Down))
        downAction.triggered.connect(self.moveDown)
        self.toolbar.addAction(downAction)

        pinAction = pg.QtGui.QAction('📌', self)
        pinAction.setToolTip('Always On Top (Ctrl+t)')
        pinAction.setShortcut('Ctrl+t')
        pinAction.setCheckable(True)
        pinAction.setChecked(False)
        pinAction.toggled.connect(self.pin)
        self.toolbar.addAction(pinAction)

        infoAction = pg.QtGui.QAction('💡', self)
        infoAction.setToolTip('How it work (?)')
        infoAction.setShortcut('Shift+/')
        infoAction.triggered.connect(self.showInfo)
        self.toolbar.addAction(infoAction)

        # spacer = pg.QtGui.QWidget()
        # spacer.setSizePolicy(pg.QtGui.QSizePolicy.Expanding, pg.QtGui.QSizePolicy.Expanding)
        # self.toolbar.addWidget(spacer)

        # comboBox = pg.QtGui.QComboBox()
        # self.toolbar.addWidget(comboBox)

        # self.toolbar.setStyleSheet(
        #     "QToolButton:!hover {color: rgb(0,255,0); background-color: transparent; font-size: 32px}"
        #     "QToolButton:checked {color: rgb(30,30,30); background-color: rgb(0,255,0)}"
        #     "QToolBar {background: rgb(30,30,30); border: none}")

        self.toolbar.setStyleSheet(
            "QToolButton {color: rgb(0,255,0)}"
            "QToolBar {background: rgb(30,30,30); border: none}")

        self.auto_range = True
        self.freezed = False
        self.probe = Probe()
        self.probe.error.connect(self.handle_error)
        self.probe.start()
        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(50)

        gainAction.setChecked(True)

    def update(self):
        if not (self.freezed or self.probe.done):
            data, size = self.probe.get()
            if size == 0:
                return
            r = self.widget.viewRange()
            n = data[0][size-1]
            if n >= r[0][1]:
                if self.auto_range:
                    start = np.max(size - int(SAMPLE_RATE * (n - r[0][0])), 0)
                    ymax = np.max(data[2][start:size])
                    ymin = np.min(data[2][start:size])

                    if ymax < r[1][1]:
                        ymax = r[1][1]
                    if ymin > r[1][0]:
                        ymin = r[1][0]
        
                    self.widget.setYRange(ymin, ymax, padding=0)

                self.widget.setXRange(n, n + r[0][1] - r[0][0], padding=0)
            self.plot.setData(data[0][:size], data[2][:size])

    def closeEvent(self, event):
        self.probe.stop()
        event.accept()
    
    def start(self, checked):
        if checked:
            self.probe.start()
            self.setWindowIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_MediaPlay))
        else:
            self.probe.stop()
            self.setWindowIcon(self.style().standardIcon(pg.QtGui.QStyle.SP_MediaStop))

    def freeze(self, checked):
        self.freezed = checked

    def set_gain(self, checked):
        self.probe.gain = 1 if checked else 0

    def adjust(self):
        r = self.widget.viewRange()
        data = self.plot.getData()
        # print((r, data))
        start = -int(SAMPLE_RATE * (data[0][-1] - r[0][0]))
        ymax = np.max(data[1][start:])
        ymin = np.min(data[1][start:])
        
        self.widget.setYRange(ymin, ymax, padding=0)

    def save(self):
        dialog = pg.widgets.FileDialog.FileDialog(self)
        dialog.setAcceptMode(pg.QtGui.QFileDialog.AcceptSave)
        dialog.setFileMode(pg.QtGui.QFileDialog.AnyFile)
        dialog.setDefaultSuffix('csv')
        dialog.setNameFilter('*.csv')
        # dialog.setWindowTitle('Export data to CSV')
        dialog.fileSelected.connect(self.export)
        dialog.show()

    def export(self, fileName):
        exporter = pg.exporters.CSVExporter(self.widget.getPlotItem())
        exporter.export(fileName)

    def zoomOutX(self):
        r = self.widget.viewRange()
        delta = (r[0][1] - r[0][0]) / 8
        self.widget.setXRange(r[0][0] + delta, r[0][1] - delta, padding=0)

    def zoomInX(self):
        r = self.widget.viewRange()
        delta = (r[0][1] - r[0][0]) / 6
        self.widget.setXRange(r[0][0] - delta, r[0][1] + delta, padding=0)

    def zoomOutY(self):
        r = self.widget.viewRange()
        delta = (r[1][1] - r[1][0]) / 8
        self.widget.setYRange(r[1][0], r[1][1] - delta, padding=0)

    def zoomInY(self):
        r = self.widget.viewRange()
        delta = (r[1][1] - r[1][0]) / 6
        self.widget.setYRange(r[1][0], r[1][1] + delta, padding=0)

    def moveLeft(self):
        r = self.widget.viewRange()
        delta = (r[0][1] - r[0][0]) / 16
        self.widget.setXRange(r[0][0] + delta, r[0][1] + delta, padding=0)

    def moveRight(self):
        r = self.widget.viewRange()
        delta = (r[0][1] - r[0][0]) / 16
        self.widget.setXRange(r[0][0] - delta, r[0][1] - delta, padding=0)

    def moveUp(self):
        r = self.widget.viewRange()
        delta = (r[1][1] - r[1][0]) / 16
        self.widget.setYRange(r[1][0] - delta, r[1][1] - delta, padding=0)

    def moveDown(self):
        r = self.widget.viewRange()
        delta = (r[1][1] - r[1][0]) / 16
        self.widget.setYRange(r[1][0] + delta, r[1][1] + delta, padding=0)

    def showInfo(self):
        pg.QtGui.QDesktopServices.openUrl(pg.QtCore.QUrl('https://github.com/makerdiary/power-profiler'))

    def pin(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() |
                                pg.QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~
                                pg.QtCore.Qt.WindowStaysOnTopHint)

        self.show()

    def handle_error(self, error):
        message = 'No device found' if error == 1 else 'Read failed'
        flags = pg.QtGui.QMessageBox.Abort | pg.QtGui.QMessageBox.Retry
        result = pg.QtGui.QMessageBox.critical(self, 'ERROR', message, flags)
        if result == pg.QtGui.QMessageBox.Retry:
            self.probe.start()
        else:
            self.close()


def main():
    app = pg.QtGui.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
    

if __name__ == '__main__':
    main()
