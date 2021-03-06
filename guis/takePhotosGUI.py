#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Sun Sep  2 20:43:32 2018

@author: robertahunt
"""
import os
import cv2
import time
import rawpy
import serial
import pysftp
import paramiko
import threading
import numpy as np
import pandas as pd


from pyzbar import pyzbar
from base64 import b64decode
from functools import partial
from PyQt5 import QtWidgets, QtCore, QtGui
from guis.basicGUI import basicGUI, ClickableIMG, Arduino
from guis.settings.local_settings import (SFTP_PUBLIC_KEY, ERDA_USERNAME, 
                                     ERDA_SFTP_PASSWORD, ERDA_HOST,
                                     ERDA_PORT, ERDA_FOLDER, DUMP_FOLDER, 
                                     CACHE_FOLDER, STORAGE_FOLDER)
from guis.progressDialog import progressDialog


global start_time

def start_timer():
    global start_time
    start_time = pd.Timestamp.now()

def tick(msg = ''):
    global start_time
    print(msg + ', Time Taken: %s'%(pd.Timestamp.now()-start_time))
    

class takePhotosGUI(basicGUI):
    def __init__(self):
        super(takePhotosGUI, self).__init__()
        
        self.arduino = Arduino()
        self.PREVIEW_WIDTH = 1024//4
        self.PREVIEW_HEIGHT = 680//4
        
        self.newImgName = ''
        self.imgSuffix = '0'
        
        self.previewPath = os.path.join(DUMP_FOLDER,'thumb_preview.jpg')
        self.initUI()
        self.displayLatestImg()
        
    
    def initUI(self):
        self.imgView = ClickableIMG(self)
        self.imgView.setMinimumSize(self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT)
        self.imgView.clicked.connect(self.openLatestIMG)
        
        header = self.headerLabel('Latest image')
        self.imgDesc = QtWidgets.QLabel('Latest image in folder: %s'% DUMP_FOLDER)
		
		
        self.moveCameraUpMm = QtWidgets.QPushButton('Up 0.1 cm')
        self.moveCameraUpCm = QtWidgets.QPushButton('Up 1 cm')
        self.moveCameraDownMm = QtWidgets.QPushButton('Down 0.1 cm')
        self.moveCameraDownCm = QtWidgets.QPushButton('Down 1 cm')
        
        self.moveCameraUpMm.clicked.connect(self.arduino.cameraUpMm)
        self.moveCameraUpCm.clicked.connect(self.arduino.cameraUpCm)
        self.moveCameraDownMm.clicked.connect(self.arduino.cameraDownMm)
        self.moveCameraDownCm.clicked.connect(self.arduino.cameraDownCm)
        
        self.undersideCheckBox = QtWidgets.QCheckBox('Underside?')
        self.autoUndersideCheckBox = QtWidgets.QCheckBox('Auto Switch Underside?')
        #self.takePhotoButton = QtWidgets.QPushButton('Take New Photo')
        #self.takePhotoButton.clicked.connect(self.takeSinglePhoto)
        
        self.takeStackedPhotoButton = QtWidgets.QPushButton('Take New Stacked Photo')
        self.takeStackedPhotoButton.clicked.connect(self.takeStackedPhotos)
        
        self.grid.addWidget(self.undersideCheckBox, 0, 0)
        self.grid.addWidget(self.autoUndersideCheckBox, 0, 1)
        self.grid.addWidget(self.moveCameraUpMm, 1, 0)
        self.grid.addWidget(self.moveCameraDownMm, 1, 1)
        self.grid.addWidget(self.moveCameraUpCm, 2, 0)
        self.grid.addWidget(self.moveCameraDownCm, 2, 1)
        #self.grid.addWidget(self.takePhotoButton, 2, 0, 1, 2)
        self.grid.addWidget(self.takeStackedPhotoButton, 3, 0, 1, 2)
        self.grid.addWidget(self.imgDesc, 0, 2)
        self.grid.addWidget(self.imgView, 1, 2, 7, 1)
        
        self.setLayout(self.grid)
    
    
    def readQRCode(self, imgPath):
        _format = imgPath.split('.')[-1]
        if _format == 'arw':
            with rawpy.imread(imgPath) as raw:
                img =  raw.postprocess()
        elif _format == 'jpg':
            img = cv2.imread(imgPath)
        else:
            self.warn('Image format at %s not understood. Got %s, should be arw or jpg.'%(imgPath,_format))
    
        decoded_list = pyzbar.decode(cv2.resize(img,(1024,680)))
        for decoded in decoded_list:
            if decoded.type == 'QRCODE':
                return decoded.data
        else:
            return ''
        
    def takePhoto(self, imgName):   
        os.chdir(DUMP_FOLDER)

        self.commandLine(['gphoto2', '--capture-image-and-download',
                          '--force-overwrite', '--filename', imgName])
        
    def takeSinglePhoto(self):
        progress = progressDialog('Taking Single Photo')
        progress._open()
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
        imgName = 'singlePhoto.arw'
        
        progress.update(20, 'Taking Single Photo..')
        self.takePhoto(imgName)
        
        dumpPath = os.path.join(DUMP_FOLDER, imgName)
        QRCode = self.readQRCode(self.previewPath)
        QRCode = self.checkQRCode(QRCode)
        
        underside = self.toggleAndCheckUnderside()
        
        if len(QRCode):
            newImgName = 'NHMD-' + QRCode + underside + '_' + timestamp + '.arw'
            progress.update(90, 'Copying file to cache as %s '%newImgName)
            cachePath = os.path.join(CACHE_FOLDER, newImgName)
            
            self.commandLine(['cp',dumpPath,cachePath])
            self.warn('Done Taking Photo')
        progress._close()

    def checkQRCode(self, QRCode):
        try:
            _len = len(str(int(QRCode)))
        except:
            _len = 0
        
        if _len == 6:
            return str(QRCode)
            
        else:
            QRCode, okPressed = QtWidgets.QInputDialog.getInt(self, "QR Code not found","QR Code not found in image, please manually input 6-digit Catalog Number:")
            if okPressed:
                try:
                    _len = len(str(int(QRCode)))
                    if _len == 6:
                        return str(QRCode)
                except:
                    pass
                return self.checkQRCode(QRCode)
            else:
                self.warn('No Photo Taken')
                return ''
            
    def toggleAndCheckUnderside(self):
        if self.autoUndersideCheckBox.isChecked():
            if self.undersideCheckBox.isChecked():
                self.undersideCheckBox.setChecked(False)
            else:
                self.undersideCheckBox.setChecked(True)
                
        if self.undersideCheckBox.isChecked():
            underside = '_V'
        else:
            underside = '_D'
	
        return underside
	
    def copyToLocalStorage(self, currentPath, newPath):
        self.commandLine(['cp', currentPath, newPath])
    
    def takeStackedPhotos(self):
        n_photos = 6
        progress = progressDialog('Taking %s Stacked Photos'%n_photos)
        progress._open()
        
        
        progress.update(5,'Checking QR Code..')
        QRCode = self.readQRCode(self.previewPath)
        QRCode = self.checkQRCode(QRCode)
        
        underside = self.toggleAndCheckUnderside()
        
        if len(QRCode):    
            timestamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
        
            for i in range(0,n_photos):
                progress.update(100*i/n_photos, 'Taking Photo %s of %s'%(i+1,n_photos))
                tempName = 'Stacked_'+str(i)+'.arw'
                self.takePhoto(imgName=tempName)
                time.sleep(0.1)
                self.arduino.moveCamera('d','0.2')
                time.sleep(1)
                
                newImgName = 'NHMD-' + QRCode + underside + '_' + timestamp + '_Stacked_' + str(i) + '.arw'
                progress.update(100*i/n_photos + 5)
                
                dumpPath = os.path.join(DUMP_FOLDER, tempName)
                cachePath = os.path.join(CACHE_FOLDER, newImgName)
                storagePath = os.path.join(STORAGE_FOLDER, newImgName)
            
                self.copyToLocalStorage(dumpPath, cachePath)
                self.copyToLocalStorage(dumpPath, storagePath)
                
                if i == 0:
                    self.openIMG(dumpPath)
                if i == 5:
                    self.openIMG(dumpPath)
                
            progress.update(99, 'Moving Camera Back Into Place')

            self.arduino.moveCamera('u',str(n_photos*0.2))
            self.warn('Done Taking Photos')

        progress._close()
        self.displayLatestImg()
     
    def displayLatestImg(self):
        path, name = self.getLatestImageName(STORAGE_FOLDER)
        self.imgDesc.setText('Latest image in folder: %s'% path)
        img = self.getIMG(path)
        
        imgResized = QtGui.QImage(img.data, img.shape[1], img.shape[0],
                               img.shape[1]*3, QtGui.QImage.Format_RGB888)
        imgResized = QtGui.QPixmap.fromImage(imgResized).scaled(self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT, 
                                                   QtCore.Qt.KeepAspectRatio)

        self.imgView.setPixmap(imgResized)


    def getLatestImageName(self, folder):
        images = [image for image in os.listdir(folder) if image.split('.')[-1] in ['arw']]
        if len(images):
            latest_image_path = max([os.path.join(folder, image) for image in images], key=os.path.getctime)
            return latest_image_path, latest_image_path.split('/')[-1]
        else:
            return '', ''

    def getIMG(self, path):
        _format = path.split('.')[-1]
        if _format == 'arw':
            with rawpy.imread(path) as raw:
                return raw.postprocess()
        else:
            self.warn('Image format in folder not understood.%s'%_format)
	 
    def openIMG(self, path):
        self.commandLine(['open', path])
        
        
    def openLatestIMG(self):
        path, name = self.getLatestImageName(STORAGE_FOLDER)
        self.commandLine(['open', path])
        
    def closeEvent(self, event):
        #reply = QtGui.QMessageBox.question(self, 'Message',
        #    "Are you sure to quit?", QtGui.QMessageBox.Yes | 
        #    QtGui.QMessageBox.No, QtGui.QMessageBox.No)

        #if reply == QtGui.QMessageBox.Yes:
        #    event.accept()
        #else:
        #    event.ignore()
        self.arduino.close()
    
