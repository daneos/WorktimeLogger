#!/usr/bin/env python

import time
import pynotify
from math import floor
from PyQt4 import uic, QtGui, QtCore


class Log:
	def __init__(self):
		pynotify.init("WorktimeLogger")
		self.t = time.time()
		self.logged_in = False

	def updateTime(self):
		self.t = time.time()

	def getTime(self):
		return self.t

	def logIn(self):
		self.updateTime()
		self.logged_in = True

		pynotify.Notification("Worktime Logger",
			"Logged in at %s" % time.strftime("%H:%M %Y-%m-%d", time.localtime(self.getTime()))
		).show()

	def logOut(self):
		self.updateTime()
		self.logged_in = False

		pynotify.Notification("Worktime Logger",
			"Logged out at %s" % time.strftime("%H:%M %Y-%m-%d", time.localtime(self.getTime()))
		).show()

	def isLoggedIn(self):
		return self.logged_in


class WLMain(QtGui.QMainWindow):

	def __init__(self, app):
		QtGui.QMainWindow.__init__(self)
		uic.loadUi("ui/WorktimeLogger.ui", self)

		self.traymenu = QtGui.QMenu()
		self.traymenu.timeAction = self.traymenu.addAction("Not logged in")
		self.traymenu.timeAction.setEnabled(False)
		self.traymenu.addSeparator()
		self.traymenu.openPanelAction = self.traymenu.addAction("Open panel")
		self.traymenu.logAction = self.traymenu.addAction("Log in")

		self.trayicon = QtGui.QSystemTrayIcon(QtGui.QIcon("icons/wl.png"), app)
		self.trayicon.setContextMenu(self.traymenu)
		self.trayicon.show()

		# workaround for not working "activated" signal in QSystemTrayIcon
		self.connect(self.traymenu, QtCore.SIGNAL("aboutToShow()"), self.updateMenu)
		self.connect(self.traymenu.openPanelAction, QtCore.SIGNAL("triggered()"), self.show)
		self.connect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logIn)

		self.connect(self.LogInButton, QtCore.SIGNAL("clicked()"), self.logIn)
		self.connect(self.LogOutButton, QtCore.SIGNAL("clicked()"), self.logOut)		

		self.log = Log()

	def logOut(self):
		self.log.logOut()

		self.LogInButton.setEnabled(True)
		self.LogOutButton.setEnabled(False)

		self.traymenu.timeAction.setText("Not logged in")
		self.traymenu.logAction.setText("Log in")
		self.disconnect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logOut)
		self.connect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logIn)

	def logIn(self):
		self.log.logIn()

		self.LogInButton.setEnabled(False)
		self.LogOutButton.setEnabled(True)

		self.traymenu.timeAction.setText("Logged in since XXh XXmin")
		self.traymenu.logAction.setText("Log out")
		self.disconnect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logIn)
		self.connect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logOut)

	def updateMenu(self):
		if self.log.isLoggedIn():
			diff = time.time() - self.log.getTime()
			h = floor(diff / 3600)
			m = floor((diff - h*3600) / 60)
			self.traymenu.timeAction.setText("Logged in since %02dh %02dmin" % (h, m))

	def closeEvent(self, ev):
		self.hide()
		ev.ignore()


if __name__ == "__main__":
	import sys
	from signal import signal, SIGINT, SIG_DFL
	signal(SIGINT, SIG_DFL)

	Application = QtGui.QApplication(sys.argv)
	Main = WLMain(Application)
	sys.exit(Application.exec_())