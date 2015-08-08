#!/usr/bin/env python
# -*- coding: utf-8 -*-

#########################################################################
# Copyright/License Notice (BSD License)                                #
#########################################################################
#########################################################################
# Copyright (c) 2011, Daniel Knaggs                                     #
# All rights reserved.                                                  #
#                                                                       #
# Redistribution and use in source and binary forms, with or without    #
# modification, are permitted provided that the following conditions    #
# are met: -                                                            #
#                                                                       #
#   * Redistributions of source code must retain the above copyright    #
#     notice, this list of conditions and the following disclaimer.     #
#                                                                       #
#   * Redistributions in binary form must reproduce the above copyright #
#     notice, this list of conditions and the following disclaimer in   #
#     the documentation and/or other materials provided with the        #
#     distribution.                                                     #
#                                                                       #
#   * Neither the name of the author nor the names of its contributors  #
#     may be used to endorse or promote products derived from this      #
#     software without specific prior written permission.               #
#                                                                       #
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS   #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT     #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR #
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT  #
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, #
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT      #
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, #
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY #
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT   #
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE #
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.  #
#########################################################################


###################################################
# Boltek EFM-100 Emulator                         #
###################################################
# Version:     v0.1.2                             #
###################################################


from datetime import *
import os
import random
import sys
import threading
import time
from xml.dom import minidom


###########
# Globals #
###########
efmunit = None


#############
# Constants #
#############
DEBUG_MODE = False

EFM100_BITS = 8
EFM100_PARITY = "N"
EFM100_PORT = "/dev/ttyu0"
EFM100_SQUELCH = 0
EFM100_SPEED = 9600
EFM100_STOPBITS = 1

XML_SETTINGS_FILE = "efm100emu-settings.xml"


###########
# Classes #
###########
class EFM100Emu():
	# $<p><ee.ee>,<f>*<cs><cr><lf>
	def __init__(self, port, speed, bits, parity, stopbits, debug_mode = False):
		self.efl = 0.
		self.fault = False
		self.serial = None
		self.txthread = None
		self.txthread_alive = False
		
		self.DEBUG_MODE = debug_mode
		self.EFM_NEGATIVE = "$-"
		self.EFM_POSITIVE = "$+"
		
		
		# Setup everything we need
		self.log("__init__", "Information", "Initialising EFM-100 emulator...")
		
		self.setupUnit(port, speed, bits, parity, stopbits)
		self.start()
	
	def adjustElectricFieldLevel(self, amount):
		self.efl += float(amount)
		
		if self.efl > 20.:
			self.efl = 20.
			
		elif self.efl < -20.:
			self.efl = -20.
	
	def checksum(self, data):
		s = 0
		
		for i in range(len(data)):
			if data[i] == "$":
				pass
			
			elif data[i] == "*":
				break
				
			else:
				s = s ^ ord(data[i])
			
		checksum = ""
		
		s = "%02X" % s
		checksum += s
		
		return checksum
	
	def dispose(self):
		if self.DEBUG_MODE:
			self.log("dispose", "Information", "Running...")
		
		
		self.txthread_alive = False
		
		if self.serial is not None:
			self.serial.close()
			self.serial = None
	
	def log(self, module, level, message):
		print "EFM100EMU/%s()/%s - %s" % (module, level, message)
	
	def setupUnit(self, port, speed, bits, parity, stopbits):
		if self.DEBUG_MODE:
			self.log("setupUnit", "Information", "Running...")
		
		
		import serial
		
		
		self.serial = serial.Serial()
		self.serial.baudrate = speed
		self.serial.bytesize = bits
		self.serial.parity = parity
		self.serial.port = port
		self.serial.stopbits = stopbits
		self.serial.timeout = 10.
		self.serial.writeTimeout = None
		self.serial.xonxoff = False
		
		self.serial.open()
	
	def start(self):
		if self.DEBUG_MODE:
			self.log("start", "Information", "Running...")
		
		
		self.txthread_alive = True
		
		self.txthread = threading.Thread(target = self.txThread)
		self.txthread.setDaemon(1)
		self.txthread.start()
	
	def toggleFault(self):
		self.fault = not self.fault
	
	def txThread(self):
		if self.DEBUG_MODE:
			self.log("txThread", "Information", "Running...")
		
		
		last_status = time.time()
		
		while self.txthread_alive:
			now = time.time()
			last_status_diff = (now - last_status)
			
			if last_status_diff >= 0.1:
				# Transmit the status straight away
				s = bytearray()
				
				if self.efl >= 0.:
					s.extend(self.EFM_POSITIVE) # <p>
					s.extend("%2.2f" % float(self.efl)) # <ee.ee>
					
				else:
					s.extend(self.EFM_NEGATIVE) # <p>
					s.extend("%2.2f" % -float(self.efl)) # <ee.ee>
				
				s.extend(",")
				
				s.extend("%d" % int(self.fault)) # <f>
				
				s.extend("*")
				
				c = self.checksum(str(s))
				s.extend(c) # <cs>
				
				s.extend("\r\n")
				
				
				lock = threading.Lock()
				
				with lock:
					self.serial.write(str(s))
					self.serial.flush()
				
				
				last_status = time.time()
			
			time.sleep(0.01)



###############
# Subroutines #
###############
def cBool(value):
	if DEBUG_MODE:
		log("cBool", "Information", "Starting...")
	
	
	if str(value).lower() == "false" or str(value) == "0":
		return False
		
	elif str(value).lower() == "true" or str(value) == "1":
		return True
		
	else:
		return False

def exitProgram():
	if DEBUG_MODE:
		log("exitProgram", "Information", "Starting...")
	
	
	global efmunit
	
	
	# EFM-100
	if efmunit is not None:
		efmunit.dispose()
		efmunit = None
	
	
	sys.exit(0)

def getch():
	plat = sys.platform.lower()
	
	if plat == "win32":
		import msvcrt
		
		
		return msvcrt.getch()
		
	else:
		import termios
		
		
		fd = sys.stdin.fileno()
		old = termios.tcgetattr(fd)
		new = termios.tcgetattr(fd)
		new[3] = new[3] & ~termios.ICANON & ~termios.ECHO
		new[6][termios.VMIN] = 1
		new[6][termios.VTIME] = 0
		termios.tcsetattr(fd, termios.TCSANOW, new)
		
		c = None
		
		try:
			c = os.read(fd, 1)
		
		finally:
			termios.tcsetattr(fd, termios.TCSAFLUSH, old)
		
		return c

def ifNoneReturnZero(strinput):
	if DEBUG_MODE:
		log("ifNoneReturnZero", "Information", "Starting...")
	
	
	if strinput is None:
		return 0
	
	else:
		return strinput

def iif(testval, trueval, falseval):
	if DEBUG_MODE:
		log("iif", "Information", "Starting...")
	
	
	if testval:
		return trueval
	
	else:
		return falseval

def log(module, level, message):
	t = datetime.now()
	
	print "%s | EMU/%s()/%s - %s" % (str(t.strftime("%d/%m/%Y %H:%M:%S")), module, level, message)

def main():
	if DEBUG_MODE:
		log("main", "Information", "Starting...")
	
	
	global cron_alive, cron_thread, efmunit
	
	
	print """
#########################################################################
# Copyright/License Notice (BSD License)                                #
#########################################################################
#########################################################################
# Copyright (c) 2011, Daniel Knaggs                                     #
# All rights reserved.                                                  #
#                                                                       #
# Redistribution and use in source and binary forms, with or without    #
# modification, are permitted provided that the following conditions    #
# are met: -                                                            #
#                                                                       #
#   * Redistributions of source code must retain the above copyright    #
#     notice, this list of conditions and the following disclaimer.     #
#                                                                       #
#   * Redistributions in binary form must reproduce the above copyright #
#     notice, this list of conditions and the following disclaimer in   #
#     the documentation and/or other materials provided with the        #
#     distribution.                                                     #
#                                                                       #
#   * Neither the name of the author nor the names of its contributors  #
#     may be used to endorse or promote products derived from this      #
#     software without specific prior written permission.               #
#                                                                       #
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS   #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT     #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR #
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT  #
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, #
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT      #
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, #
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY #
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT   #
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE #
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.  #
#########################################################################
"""
	log("main", "Information", "")
	log("main", "Information", "Boltek EFM-100 Emulator")
	log("main", "Information", "=======================")
	log("main", "Information", "Checking settings...")
	
	
	if not os.path.exists(XML_SETTINGS_FILE):
		log("main", "Warning", "The XML settings file doesn't exist, create one...")
		
		xmlEMUSettingsWrite()
		
		
		log("main", "Information", "The XML settings file has been created using the default settings.  Please edit it and restart the emulator once you're happy with the settings.")
		
		exitProgram()
		
	else:
		log("main", "Information", "Reading XML settings...")
		
		xmlEMUSettingsRead()
		
		# This will ensure it will have any new settings in
		if os.path.exists(XML_SETTINGS_FILE + ".bak"):
			os.unlink(XML_SETTINGS_FILE + ".bak")
			
		os.rename(XML_SETTINGS_FILE, XML_SETTINGS_FILE + ".bak")
		xmlEMUSettingsWrite()
	
	
	
	log("main", "Information", "Setting up...")
	
	efmunit = EFM100Emu(EFM100_PORT, EFM100_SPEED, EFM100_BITS, EFM100_PARITY, EFM100_STOPBITS, DEBUG_MODE)
	
	
	log("main", "Information", "Starting...")
	
	while True:
		try:
			print """

Help
====
a - Increase field level by 0.5KV
z - Decrease field level by 0.5KV
x - Toggle fault
q - Quit

Choice:""",
			
			i = getch()
			
			if len(i) == 1:
				if i == "a":
					efmunit.adjustElectricFieldLevel(0.5)
					
					print "Increase field level - now set to %2.2fKV" % efmunit.efl
				
				elif i == "z":
					efmunit.adjustElectricFieldLevel(-0.5)
					
					print "Decrease field level - now set to %2.2fKV" % efmunit.efl
					
				elif i == "x":
					efmunit.toggleFault()
					
					print "Fault is now %s" % iif(efmunit.fault, "active", "inactive")
					
				elif i == "q":
					print "Quit"
					
					break
				
		except KeyboardInterrupt:
			break
			
		except Exception, ex:
			log("main", "Exception", str(ex))
	
	
	log("main", "Information", "Exiting...")
	exitProgram()

def xmlEMUSettingsRead():
	if DEBUG_MODE:
		log("xmlEMUSettingsRead", "Information", "Starting...")
	
	
	global DEBUG_MODE, EFM100_PARITY, EFM100_PORT, EFM100_SPEED, EFM100_STOPBITS
	
	
	if os.path.exists(XML_SETTINGS_FILE):
		xmldoc = minidom.parse(XML_SETTINGS_FILE)
		
		myvars = xmldoc.getElementsByTagName("Setting")
		
		for var in myvars:
			for key in var.attributes.keys():
				val = str(var.attributes[key].value)
				
				# Now put the correct values to correct key
				if key == "EFM100Bits":
					EFM100_BITS = int(val)
					
				elif key == "EFM100Parity":
					EFM100_PARITY = val
					
				elif key == "EFM100Port":
					EFM100_PORT = val
					
				elif key == "EFM100Speed":
					EFM100_SPEED = int(val)
					
				elif key == "EFM100StopBits":
					EFM100_STOPBITS = int(val)
					
				elif key == "DebugMode":
					DEBUG_MODE = cBool(val)
					
				else:
					log("xmlEMUSettingsRead", "Warning", "XML setting attribute \"%s\" isn't known.  Ignoring..." % key)

def xmlEMUSettingsWrite():
	if DEBUG_MODE:
		log("xmlEMUSettingsWrite", "Information", "Starting...")
	
	
	if not os.path.exists(XML_SETTINGS_FILE):
		xmloutput = file(XML_SETTINGS_FILE, "w")
		
		
		xmldoc = minidom.Document()
		
		# Create header
		settings = xmldoc.createElement("SXRServer")
		xmldoc.appendChild(settings)
		
		# Write each of the details one at a time, makes it easier for someone to alter the file using a text editor
		var = xmldoc.createElement("Setting")
		var.setAttribute("EFM100Port", str(EFM100_PORT))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("EFM100Speed", str(EFM100_SPEED))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("EFM100Bits", str(EFM100_BITS))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("EFM100Parity", str(EFM100_PARITY))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("EFM100StopBits", str(EFM100_STOPBITS))
		settings.appendChild(var)
		
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("DebugMode", str(DEBUG_MODE))
		settings.appendChild(var)
		
		
		# Finally, save to the file
		xmloutput.write(xmldoc.toprettyxml())
		xmloutput.close()


########
# Main #
########
if __name__ == "__main__":
	main()
