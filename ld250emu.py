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
# Boltek LD-250 Emulator                          #
###################################################
# Version:     v0.1.2                             #
###################################################


from Queue import Queue

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
ldunit = None


#############
# Constants #
#############
DEBUG_MODE = False

LD250_BITS = 8
LD250_PARITY = "N"
LD250_PORT = "/dev/ttyu0"
LD250_SQUELCH = 0
LD250_SPEED = 9600
LD250_STOPBITS = 1

XML_SETTINGS_FILE = "ld250emu-settings.xml"


###########
# Classes #
###########
class LD250Emu():
	#
	# LD sentence key:
	#
	# <bbb.b> = bearing to strike 0-359.9 degrees
	# <ccc>   = close strike rate 0-999 strikes/minute
	# <ca>    = close alarm status (0 = inactive, 1 = active)
	# <cs>    = checksum
	# <ddd>   = corrected strike distance (0-300 miles)
	# <hhh.h> = current heading from GPS/compass
	# <sa>    = severe alarm status (0 = inactive, 1 = active)
	# <sss>   = total strike rate 0-999 strikes/minute
	# <uuu>   = uncorrected strike distance (0-300 miles)
	def __init__(self, port, speed, bits, parity, stopbits, debug_mode = False):
		self.alarm_close = False
		self.alarm_severe = False
		self.serial = None
		self.rxthread = None
		self.rxthread_alive = False
		self.txqueue = Queue()
		self.txthread = None
		self.txthread_alive = False
		
		self.DEBUG_MODE = debug_mode
		self.LD_NOISE  = "$WIMLN" # $WIMLN*<cs>
		self.LD_STATUS = "$WIMST" # $WIMST,<ccc>,<sss>,<ca>,<sa>,<hhh.h>*<cs>
		self.LD_STRIKE = "$WIMLI" # $WIMLI,<ddd>,<uuu>,<bbb.b>*<cs>
		self.SENTENCE_END = "\r"
		self.SENTENCE_START = "SQ"
		
		
		# Setup everything we need
		self.log("__init__", "Information", "Initialising LD-250 emulator...")
		
		self.setupUnit(port, speed, bits, parity, stopbits)
		self.start()
	
	def addNoiseToQueue(self):
		s = bytearray()
		
		s.extend(self.LD_NOISE)
		
		s.extend("*")
		
		c = self.checksum(str(s))
		s.extend(c) # <cs>
		
		s.extend("\r\n")
		
		
		self.txqueue.put(str(s))
	
	def addStrikeToQueue(self, distance, bearing):
		if distance < 0 or distance > 300:
			distance = 0
		
		if bearing < 0. or bearing > 359.9:
			bearing = 0.
		
		
		s = bytearray()
		
		s.extend(self.LD_STRIKE)
		s.extend(",")
		
		s.extend("%d" % distance) # <ddd>
		s.extend(",")
		
		s.extend("%d" % distance) # <uuu>
		s.extend(",")
		
		s.extend("%.1f" % float(bearing)) # <bbb.b>
		
		s.extend("*")
		
		c = self.checksum(str(s))
		s.extend(c) # <cs>
		
		s.extend("\r\n")
		
		
		self.txqueue.put(str(s))
	
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
		
		
		self.rxthread_alive = False
		self.txthread_alive = False
		
		if self.serial is not None:
			self.serial.close()
			self.serial = None
	
	def log(self, module, level, message):
		print "LD250EMU/%s()/%s - %s" % (module, level, message)
	
	def rxThread(self):
		if self.DEBUG_MODE:
			self.log("rxThread", "Information", "Running...")
		
		
		buffer = bytearray()
		
		while self.rxthread_alive:
			extracted = None
			
			
			bytes = self.serial.inWaiting()
			
			if bytes > 0:
				if self.DEBUG_MODE:
					self.log("rxThread", "Information", "%d bytes are waiting in the serial buffer." % bytes)
				
				
				# Ensure we're thread-safe
				lock = threading.Lock()
				
				with lock:
					try:
						buffer.extend(self.serial.read(bytes))
						
					except Exception, ex:
						if self.DEBUG_MODE:
							self.log("rxThread", "Exception", str(ex))
			
			x = buffer.find(self.SENTENCE_START)
			
			if x <> -1:
				y = buffer.find(self.SENTENCE_END, x)
				
				if y <> -1:
					if self.DEBUG_MODE:
						self.log("rxThread", "Information", "A sentence has been found in the buffer.")
					
					
					y += len(self.SENTENCE_END)
					
					# There appears to be complete sentence in there, extract it
					extracted = str(buffer[x:y])
					
			
			
			if extracted is not None:
				# Remove it from the buffer first
				newbuf = str(buffer).replace(extracted, "", 1)
				
				buffer = bytearray()
				buffer.extend(newbuf)
				
				
				# Squelch command come in, send it back
				lock = threading.Lock()
				
				with lock:
					try:
						if self.DEBUG_MODE:
							self.log("rxThread", "Information", "Squelch command has come in, sending it back.")
						
						
						squelch = int(extracted.replace("SQ", "").replace("\r", "").replace("\n", ""))
						
						self.serial.write(":SQUELCH %d (0-15)\r\n" % squelch)
						self.serial.flush()
						
					except Exception, ex:
						if self.DEBUG_MODE:
							self.log("rxThread", "Exception", str(ex))
			
			time.sleep(0.01)
	
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
		
		
		self.rxthread_alive = True
		
		self.rxthread = threading.Thread(target = self.rxThread)
		self.rxthread.setDaemon(1)
		self.rxthread.start()
		
		
		self.txthread_alive = True
		
		self.txthread = threading.Thread(target = self.txThread)
		self.txthread.setDaemon(1)
		self.txthread.start()
	
	def toggleCloseAlarm(self):
		self.alarm_close = not self.alarm_close
	
	def toggleSevereAlarm(self):
		self.alarm_severe = not self.alarm_severe
	
	def txThread(self):
		if self.DEBUG_MODE:
			self.log("txThread", "Information", "Running...")
		
		
		last_status = time.time()
		
		while self.txthread_alive:
			now = time.time()
			last_status_diff = (now - last_status)
			
			if last_status_diff >= 1.:
				# Transmit the status straight away
				s = bytearray()
				
				s.extend(self.LD_STATUS)
				s.extend(",")
				
				s.extend("0") # <ccc>
				s.extend(",")
				
				s.extend("0") # <sss>
				s.extend(",")
				
				s.extend("%d" % int(self.alarm_close)) # <ca>
				s.extend(",")
				
				s.extend("%d" % int(self.alarm_severe)) # <sa>
				s.extend(",")
				
				s.extend("000.0") # <hhh.h>
				
				s.extend("*")
				
				c = self.checksum(str(s))
				s.extend(c) # <cs>
				
				s.extend("\r\n")
				
				
				lock = threading.Lock()
				
				with lock:
					self.serial.write(str(s))
					self.serial.flush()
				
				
				last_status = time.time()
			
			
			if not self.txqueue.empty():
				s = self.txqueue.get()
				
				
				# Now transmit the sentence
				lock = threading.Lock()
				
				with lock:
					self.serial.write(str(s))
					self.serial.flush()
			
			
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
	
	
	global ldunit
	
	
	# LD-250
	if ldunit is not None:
		ldunit.dispose()
		ldunit = None
	
	
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
	
	
	global cron_alive, cron_thread, ldunit
	
	
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
	log("main", "Information", "Boltek LD-250 Emulator")
	log("main", "Information", "======================")
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
	
	ldunit = LD250Emu(LD250_PORT, LD250_SPEED, LD250_BITS, LD250_PARITY, LD250_STOPBITS, DEBUG_MODE)
	
	
	log("main", "Information", "Starting...")
	
	while True:
		try:
			print """

Help
====
s - Generate a random strike
d - Generate noise
z - Toggle close alarm
x - Toggle severe alarm
q - Quit

Choice:""",
			
			i = getch()
			
			if len(i) == 1:
				if i == "s":
					# Random strike
					random.seed(datetime.now())
					
					distance = random.randint(0, 300)
					bearing = float(random.randint(0, 359))
					
					
					ldunit.addStrikeToQueue(distance, bearing)
					
					print "Random strike"
					
				elif i == "d":
					ldunit.addNoiseToQueue()
					
					print "Noise"
				
				elif i == "z":
					ldunit.toggleCloseAlarm()
					
					print "Close alarm is now %s" % iif(ldunit.alarm_close, "active", "inactive")
					
				elif i == "x":
					ldunit.toggleSevereAlarm()
					
					print "Severe alarm is now %s" % iif(ldunit.alarm_severe, "active", "inactive")
					
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
	
	
	global DEBUG_MODE, LD250_PARITY, LD250_PORT, LD250_SPEED, LD250_STOPBITS
	
	
	if os.path.exists(XML_SETTINGS_FILE):
		xmldoc = minidom.parse(XML_SETTINGS_FILE)
		
		myvars = xmldoc.getElementsByTagName("Setting")
		
		for var in myvars:
			for key in var.attributes.keys():
				val = str(var.attributes[key].value)
				
				# Now put the correct values to correct key
				if key == "LD250Bits":
					LD250_BITS = int(val)
					
				elif key == "LD250Parity":
					LD250_PARITY = val
					
				elif key == "LD250Port":
					LD250_PORT = val
					
				elif key == "LD250Speed":
					LD250_SPEED = int(val)
					
				elif key == "LD250StopBits":
					LD250_STOPBITS = int(val)
					
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
		var.setAttribute("LD250Port", str(LD250_PORT))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("LD250Speed", str(LD250_SPEED))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("LD250Bits", str(LD250_BITS))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("LD250Parity", str(LD250_PARITY))
		settings.appendChild(var)
		
		var = xmldoc.createElement("Setting")
		var.setAttribute("LD250StopBits", str(LD250_STOPBITS))
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
