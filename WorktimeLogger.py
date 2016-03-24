#!/usr/bin/env python

import sys
import time
import pynotify
import sqlite3
from math import floor
from PyQt4 import uic, QtGui, QtCore

TIMEFMT = "%H:%M %Y-%m-%d"

def sec_to_hm(secs):
	h = floor(secs / 3600)
	m = floor((secs - h*3600) / 60)
	return (h, m)


class Database:
	def __init__(self, filename="wl.sqlite"):
		self.db = sqlite3.connect(filename)
		self.cur = self.db.cursor()

	def commit(self):
		self.db.commit()

	def close(self):
		self.db.close()

	def q(self, query):
		self.cur.execute(query)
		res = self.cur.fetchall()
		reslist = []
		for row in res:
			row_dict = {}
			for i, field in enumerate(row):
				row_dict[self.cur.description[i][0]] = field
			reslist.append(row_dict)
		return reslist

	def getLog(self, log_id):
		res = self.q("SELECT * FROM logs WHERE id == %d" % log_id)
		return res[0]

	def getActiveLog(self):
		res = self.q("SELECT * FROM logs WHERE active == 1 ORDER BY id DESC")
		if not res:			# no active log
			return self.createNewLog()
		elif len(res) > 1:	# multiple active logs
			pass
		else:
			return res[0]

	def createNewLog(self):
		self.q("INSERT INTO logs (active) values (1)")
		self.commit()
		return self.getActiveLog()

	def setTimeIn(self, log_id, time):
		self.q("UPDATE logs SET time_in = %d WHERE id = %d" % (time, log_id))
		self.commit()

	def setTimeOut(self, log_id, time):
		self.q("UPDATE logs SET time_out = %d WHERE id = %d" % (time, log_id))
		self.commit()

	def deactivateLog(self, log_id):
		self.q("UPDATE logs SET active = 0 WHERE id = %d" % log_id)
		self.commit()


class Log:
	def __init__(self):
		pynotify.init("WorktimeLogger")
		self.t = time.time()
		self.logged_in = False
		self.db = Database()
		self.log = self.db.getActiveLog()
		if self.log["time_in"]:
			self.t = self.log["time_in"]
			self.logged_in = True
		self.need_new_log = False

	def updateTime(self):
		self.t = time.time()

	def getTime(self):
		return self.t

	def logIn(self):
		self.updateTime()
		if self.need_new_log:
			self.log = self.db.getActiveLog()
		self.db.setTimeIn(self.log["id"], self.getTime())
		self.updateDB()

		self.logged_in = True
		pynotify.Notification("Worktime Logger",
			"Logged in at %s" % time.strftime(TIMEFMT, time.localtime(self.getTime()))
		).show()

	def logOut(self):
		self.updateTime()
		self.db.setTimeOut(self.log["id"], self.getTime())
		self.db.deactivateLog(self.log["id"])
		self.updateDB()

		self.logged_in = False
		pynotify.Notification("Worktime Logger",
			"Logged out at %s" % time.strftime(TIMEFMT, time.localtime(self.getTime()))
		).show()
		self.invalidate()

	def isLoggedIn(self):
		return self.logged_in

	def close(self):
		self.db.close()

	def updateDB(self):
		self.log = self.db.getLog(self.log["id"])

	def invalidate(self):
		self.need_new_log = True


class WLLoginDialog(QtGui.QDialog):

	def __init__(self, main):
		QtGui.QDialog.__init__(self)
		uic.loadUi("ui/LogInDialog.ui", self)

		self.main = main

		self.TextLabel.setText("Log in at %s?" % time.strftime(TIMEFMT))

		self.connect(self.YesButton, QtCore.SIGNAL("clicked()"), self.logIn)
		self.connect(self.NoButton, QtCore.SIGNAL("clicked()"), self.hide)
		self.connect(self.PanelButton, QtCore.SIGNAL("clicked()"), self.openPanel)

		self.show()

	def logIn(self):
		self.main.logIn()
		self.hide()

	def openPanel(self):
		self.main.show()
		self.hide()


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

		self.connect(self.QuitButton, QtCore.SIGNAL("clicked()"), self.exit)

		self.log = Log()
		if self.log.isLoggedIn():
			self.logInGUIAction()
		else:
			self.logInPrompt = WLLoginDialog(self)

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
		self.logInGUIAction()

	def logInGUIAction(self):
		self.LogInButton.setEnabled(False)
		self.LogOutButton.setEnabled(True)

		self.traymenu.timeAction.setText("Logged in since XXh XXmin")
		self.traymenu.logAction.setText("Log out")
		self.disconnect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logIn)
		self.connect(self.traymenu.logAction, QtCore.SIGNAL("triggered()"), self.logOut)

	def updateMenu(self):
		if self.log.isLoggedIn():
			diff = time.time() - self.log.getTime()
			self.traymenu.timeAction.setText("Logged in since %02dh %02dmin" % sec_to_hm(diff))

	def closeEvent(self, ev):
		self.hide()
		ev.ignore()

	def exit(self):
		self.log.close()
		sys.exit(0)


if __name__ == "__main__":
	from signal import signal, SIGINT, SIG_DFL
	signal(SIGINT, SIG_DFL)

	Application = QtGui.QApplication(sys.argv)
	Main = WLMain(Application)
	sys.exit(Application.exec_())