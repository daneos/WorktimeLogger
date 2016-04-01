#!/usr/bin/env python

import sys
import time
import pynotify
import sqlite3
from datetime import datetime, timedelta
from calendar import monthrange
from math import floor
from PyQt4 import uic, QtGui, QtCore

def sec_to_hm(secs):
	h = floor(secs / 3600)
	m = round((secs - h*3600) / 60)
	if m == 60:
		m = 0
		h += 1
	return (h, m)

def hm_to_sec(h, m):
	return int(round(float(h)*3600 + float(m)*60))


class __Error(Exception):
	def __init__(self, info):
		self.info = info
	def __str__(self):
		return "%s: %s" % (self.__class__.__name__, self.info)

class DatabaseInvalidError(__Error):
	pass
class OptionNotFoundError(__Error):
	pass


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
			raise DatabaseInvalidError("Multiple logs are active. Your database may be corrupted.")
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

	def getLogsFrom(self, time_start, time_end):
		return self.q("SELECT * FROM logs WHERE time_in >= %d AND time_out <= %d AND active = 0" % (time_start, time_end))

	def getConfig(self):
		conf = self.q("SELECT * FROM config")
		conf_dict = {}
		for row in conf:
			conf_dict[row["option"]] = row["value"]
		return conf_dict

	def getOption(self, option):
		opt = self.q("SELECT * FROM config WHERE option = %s" % option)
		if not opt:
			raise OptionNotFoundError("No option '%s' in database." % option)
			return
		return opt[0]["value"]

	def setOption(self, option, value):
		self.q("UPDATE config SET value = %s WHERE option = %s" % (value, option))
		self.commit()


class Config:
	def __init__(self):
		self.db = GLOBAL_DB
		self.config = None
		self.updateDB()

	def updateDB(self):
		self.config = self.db.getConfig()

	def getOption(self, option):
		return self.config[option]

	def setOption(self, option, value):
		self.db.setOption(option, value)
		self.updateDB()


class Log:
	def __init__(self):
		pynotify.init("WorktimeLogger")
		self.t = time.time()
		self.logged_in = False
		self.db = GLOBAL_DB
		self.log = self.db.getActiveLog()
		if self.log["time_in"]:
			self.t = self.log["time_in"]
			self.logged_in = True
		self.need_new_log = False
		self.config = GLOBAL_CONFIG

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
			"Logged in at %s" % time.strftime(self.config.getOption("timefmt"), time.localtime(self.getTime()))
		).show()

	def logOut(self):
		self.updateTime()
		self.db.setTimeOut(self.log["id"], self.getTime())
		self.db.deactivateLog(self.log["id"])
		self.updateDB()

		self.logged_in = False
		pynotify.Notification("Worktime Logger",
			"Logged out at %s" % time.strftime(self.config.getOption("timefmt"), time.localtime(self.getTime()))
		).show()
		self.invalidate()

	def isLoggedIn(self):
		return self.logged_in

	def updateDB(self):
		self.log = self.db.getLog(self.log["id"])

	def invalidate(self):
		self.need_new_log = True

	def getTimeBetween(self, time_start, time_end):
		res = self.db.getLogsFrom(time_start, time_end)
		total = 0
		for row in res:
			total += row["time_out"] - row["time_in"]
		if self.isLoggedIn() and self.getTime() >= time_start and self.getTime() <= time_end:
			total += time.time() - self.getTime()
		return total


class WLLoginDialog(QtGui.QDialog):
	def __init__(self, main):
		QtGui.QDialog.__init__(self)
		uic.loadUi("ui/LogInDialog.ui", self)

		self.main = main
		self.config = GLOBAL_CONFIG

		self.TextLabel.setText("Log in at %s?" % time.strftime(self.config.getOption("timefmt")))

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

		self.timer = QtCore.QTimer()
		self.connect(self.timer, QtCore.SIGNAL("timeout()"), self.update)
		self.timer.start(30000)		# 30s update time

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

		self.config = GLOBAL_CONFIG

		self.update()

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
		GLOBAL_DB.close()
		sys.exit(0)

	def update(self):
		d = datetime.today()
		mtarget = hm_to_sec(self.config.getOption("hours"), self.config.getOption("minutes"))	# time to work in a month
		wtarget = mtarget/4						# time to work in a week

		# start time of current week
		wstart_d = (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
		wstart = time.mktime(wstart_d.timetuple())
		# end time of current week
		wend = time.mktime((wstart_d + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999).timetuple())
		wtime = self.log.getTimeBetween(wstart, wend)
		self.WorkedThisWeekLabel.setText("%02d:%02d" % sec_to_hm(wtime))
		if wtime > wtarget:
			self.LeftThisWeekLabel.setText("-%02d:%02d" % sec_to_hm(wtime - wtarget))
		else:
			self.LeftThisWeekLabel.setText("%02d:%02d" % sec_to_hm(wtarget - wtime))

		# start time of current month
		mstart = time.mktime(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timetuple())
		# end time of current month
		mend = time.mktime(d.replace(day=monthrange(d.year, d.month)[1], hour=23, minute=59, second=59, microsecond=999999).timetuple())
		mtime = self.log.getTimeBetween(mstart, mend)
		self.WorkedThisMonthLabel.setText("%02d:%02d" % sec_to_hm(mtime))
		if mtime > mtarget:
			self.LeftThisMonthLabel.setText("-%02d:%02d" % sec_to_hm(mtime - mtarget))
		else:
			self.LeftThisMonthLabel.setText("%02d:%02d" % sec_to_hm(mtarget - mtime))


if __name__ == "__main__":
	from signal import signal, SIGINT, SIG_DFL
	signal(SIGINT, SIG_DFL)

	if len(sys.argv) > 1:
		GLOBAL_DB = Database(sys.argv[1])
	else:
		GLOBAL_DB = Database()
	GLOBAL_CONFIG = Config()

	Application = QtGui.QApplication([])
	Main = WLMain(Application)
	sys.exit(Application.exec_())