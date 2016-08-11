#!/usr/bin/env python

import os
import sys
import time
import pynotify
import sqlite3
from datetime import datetime, timedelta
from calendar import monthrange
from math import floor
from PyQt4 import uic, QtGui, QtCore

base_dir = os.path.dirname(os.path.realpath(__file__))
month_name = ("--", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
GLOBAL_DB = None
GLOBAL_CONFIG = None

def sec_to_hm(secs):
	h = floor(secs / 3600)
	m = round((secs - h*3600) / 60)
	if m == 60:
		m = 0
		h += 1
	return (h, m)

def hm_to_sec(h, m):
	return int(round(float(h)*3600 + float(m)*60))

def ordinal(n):
	m = n % 10;
	if m == 1 and n != 11:
		return "st"
	elif m == 2 and n != 12:
		return "nd"
	elif m == 3 and n != 13:
		return "rd"
	else:
		return "th"


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
	def __init__(self, filename="~/.WorktimeLogger/wl.sqlite"):
		filename = os.path.realpath(os.path.expanduser(filename))
		if not os.path.exists(filename):
			db_dir = os.path.dirname(filename)
			if not os.path.exists(db_dir):
				os.system("mkdir -p %s" % db_dir)
			os.system("cp %s/wl.sqlite %s" % (base_dir, filename))
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

	def clearLogs(self):
		self.q("DELETE FROM logs")
		self.commit()

	def getAllLogs(self):
		return self.q("SELECT * FROM logs WHERE active = 0")

	def getLastInTime(self):
		return self.q("SELECT time_in FROM logs ORDER BY time_in DESC LIMIT 1")[0]

	def getLastOutTime(self):
		return self.q("SELECT time_out FROM logs ORDER BY time_out DESC LIMIT 1")[0]

	def getConfig(self):
		conf = self.q("SELECT * FROM config")
		conf_dict = {}
		for row in conf:
			conf_dict[row["option"]] = row["value"]
		return conf_dict

	def getOption(self, option):
		opt = self.q("SELECT * FROM config WHERE option = \"%s\"" % option)
		if not opt:
			raise OptionNotFoundError("No option '%s' in database." % option)
			return
		return opt[0]["value"]

	def setOption(self, option, value):
		self.q("UPDATE config SET value = \"%s\" WHERE option = \"%s\"" % (value, option))
		self.commit()

	def addOption(self, option, value):
		self.q("INSERT INTO config (option, value) VALUES (\"%s\", \"%s\")" % (option, value))
		self.commit()

	def removeOption(self, option):
		self.q("DELETE FROM config WHERE option = \"%s\"" % option)
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
		if option not in self.config:
			self.db.addOption(option, value)
		else:
			self.db.setOption(option, value)
		self.updateDB()

	def removeOption(self, option):
		self.db.removeOption(option)
		self.updateDB()

	def getAll(self):
		return self.config


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
			"Logged in at %s" % time.strftime(self.config.getOption("datetime_fmt"), time.localtime(self.getTime()))
		).show()

	def logOut(self):
		self.updateTime()
		self.db.setTimeOut(self.log["id"], self.getTime())
		self.db.deactivateLog(self.log["id"])
		self.updateDB()

		self.logged_in = False
		pynotify.Notification("Worktime Logger",
			"Logged out at %s" % time.strftime(self.config.getOption("datetime_fmt"), time.localtime(self.getTime()))
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

	def getTotalTime(self):
		res = self.db.getAllLogs()
		total = 0
		for row in res:
			total += row["time_out"] - row["time_in"]
		if self.isLoggedIn():
			total += time.time() - self.getTime()
		return total

	def getLastInTime(self):
		return self.db.getLastInTime()["time_in"]

	def getLastOutTime(self):
		return self.db.getLastOutTime()["time_out"]


class WLLoginDialog(QtGui.QDialog):
	def __init__(self, main):
		QtGui.QDialog.__init__(self)
		uic.loadUi("%s/ui/LogInDialog.ui" % base_dir, self)

		self.main = main
		self.config = GLOBAL_CONFIG

		self.TextLabel.setText("Log in at %s?" % time.strftime(self.config.getOption("datetime_fmt")))

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


class WLArchivalDataBrowser(QtGui.QWidget):
	def __init__(self):
		QtGui.QWidget.__init__(self)
		uic.loadUi("%s/ui/ArchivalData.ui" % base_dir, self)

		self.config = GLOBAL_CONFIG
		self.log = Log()

		self.connect(self.Calendar, QtCore.SIGNAL("clicked(QDate)"), self.dateChanged)
		self.connect(self.Calendar, QtCore.SIGNAL("currentPageChanged(int,int)"), self.pageChanged)

		self.date = self.Calendar.selectedDate()

		self.update()
		self.show()

	def dateChanged(self, date):
		self.date = date
		self.update()

	def pageChanged(self, year, month):
		self.date.setDate(year, month, self.date.day())
		if not self.date.isValid():
			self.date.setDate(year, month, 1)
		self.update()

	def update(self):
		self.DayLabel.setText("%d%s %s" % (self.date.day(), ordinal(self.date.day()), month_name[self.date.month()]))
		self.WeekLabel.setText("Week %02d of %d" % self.date.weekNumber())
		self.MonthLabel.setText("%s %d" % (month_name[self.date.month()], self.date.year()))

		timefmt = self.config.getOption("timeshort_fmt")

		d = datetime(self.date.year(), self.date.month(), self.date.day())
		mtarget = hm_to_sec(self.config.getOption("hours"), self.config.getOption("minutes"))	# time to work in a month
		wtarget = mtarget/4						# time to work in a week
		dtarget = wtarget/5						# time to work in a day

		# start time of selected day
		dstart = time.mktime(d.replace(hour=0, minute=0, second=0, microsecond=0).timetuple())
		# end time of selected month
		dend = time.mktime(d.replace(hour=23, minute=59, second=59, microsecond=999999).timetuple())
		dtime = self.log.getTimeBetween(dstart, dend)
		self.WorkedDayLabel.setText(timefmt % sec_to_hm(dtime))
		if dtime > dtarget:
			self.LeftDayLabel.setText("-"+timefmt % sec_to_hm(dtime - dtarget))
		else:
			self.LeftDayLabel.setText(timefmt % sec_to_hm(dtarget - dtime))

		# start time of selected week
		wstart_d = (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
		wstart = time.mktime(wstart_d.timetuple())
		# end time of selected week
		wend = time.mktime((wstart_d + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999).timetuple())
		wtime = self.log.getTimeBetween(wstart, wend)
		self.WorkedWeekLabel.setText(timefmt % sec_to_hm(wtime))
		if wtime > wtarget:
			self.LeftWeekLabel.setText("-"+timefmt % sec_to_hm(wtime - wtarget))
		else:
			self.LeftWeekLabel.setText(timefmt % sec_to_hm(wtarget - wtime))

		# start time of selected month
		mstart = time.mktime(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timetuple())
		# end time of selected month
		mend = time.mktime(d.replace(day=monthrange(d.year, d.month)[1], hour=23, minute=59, second=59, microsecond=999999).timetuple())
		mtime = self.log.getTimeBetween(mstart, mend)
		self.WorkedMonthLabel.setText(timefmt % sec_to_hm(mtime))
		if mtime > mtarget:
			self.LeftMonthLabel.setText("-%02d:%02d" % sec_to_hm(mtime - mtarget))
		else:
			self.LeftMonthLabel.setText(timefmt % sec_to_hm(mtarget - mtime))


class WLClearLogDialog(QtGui.QWidget):
	def __init__(self, parent, main):
		QtGui.QWidget.__init__(self)
		uic.loadUi("%s/ui/ClearLogDialog.ui" % base_dir, self)
		self.parent = parent
		self.main = main

		self.connect(self.ClearButton, QtCore.SIGNAL("clicked()"), self.clearLog)
		self.connect(self.CancelButton, QtCore.SIGNAL("clicked()"), self.hide)

		self.update()
		self.show()

	def clearLog(self):
		self.main.logOut()
		GLOBAL_DB.clearLogs()
		self.main.update()
		self.hide()
		self.parent.hide()


class WLConfigBrowser(QtGui.QWidget):
	def __init__(self, parent):
		QtGui.QWidget.__init__(self)
		uic.loadUi("%s/ui/ConfEditor.ui" % base_dir, self)
		self.config = GLOBAL_CONFIG
		self.parent = parent

		self.connect(self.AddButton, QtCore.SIGNAL("clicked()"), self.addOption)
		self.connect(self.RemoveButton, QtCore.SIGNAL("clicked()"), self.removeOption)
		self.connect(self.ApplyButton, QtCore.SIGNAL("clicked()"), self.apply)
		self.connect(self.CancelButton, QtCore.SIGNAL("clicked()"), self.hide)
		self.connect(self.ClearButton, QtCore.SIGNAL("clicked()"), self.clearLog)

		self.update()
		self.show()

	def update(self):
		opts = self.config.getAll()
		self.OptionsTable.setRowCount(0)
		row = 0
		for k,v in opts.iteritems():
			self.OptionsTable.setRowCount(row+1)
			self.OptionsTable.setItem(row, 0, QtGui.QTableWidgetItem(k))
			self.OptionsTable.setItem(row, 1, QtGui.QTableWidgetItem(v))
			row += 1

	def addOption(self):
		self.OptionsTable.setRowCount(self.OptionsTable.rowCount()+1)

	def removeOption(self):
		self.OptionsTable.removeRow(self.OptionsTable.currentRow())

	def apply(self):
		present_options = []
		for row in range(0, self.OptionsTable.rowCount()):
			k = str(self.OptionsTable.item(row, 0).text())
			v = str(self.OptionsTable.item(row, 1).text())
			self.config.setOption(k, v)
			present_options.append(k)
		for opt in [ k for k in self.config.getAll() if k not in present_options ]:
			self.config.removeOption(opt)
		self.parent.update()
		self.hide()

	def clearLog(self):
		self.ClearDialog = WLClearLogDialog(self, self.parent)


class WLMain(QtGui.QMainWindow):
	def __init__(self, app):
		QtGui.QMainWindow.__init__(self)
		uic.loadUi("%s/ui/WorktimeLogger.ui" % base_dir, self)

		self.traymenu = QtGui.QMenu()
		self.traymenu.timeAction = self.traymenu.addAction("Not logged in")
		self.traymenu.timeAction.setEnabled(False)
		self.traymenu.addSeparator()
		self.traymenu.openPanelAction = self.traymenu.addAction("Open panel")
		self.traymenu.logAction = self.traymenu.addAction("Log in")

		self.trayicon = QtGui.QSystemTrayIcon(QtGui.QIcon("%s/icons/wl.png" % base_dir), app)
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

		self.connect(self.ArchiveButton, QtCore.SIGNAL("clicked()"), self.openArchive)
		self.connect(self.ConfigureButton, QtCore.SIGNAL("clicked()"), self.openConfig)
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
			timefmt = self.config.getOption("timelong_fmt")
			diff = time.time() - self.log.getTime()
			self.traymenu.timeAction.setText("Logged in since "+timefmt % sec_to_hm(diff))

	def closeEvent(self, ev):
		self.hide()
		ev.ignore()

	def exit(self):
		GLOBAL_DB.close()
		sys.exit(0)

	def update(self):
		d = datetime.today()
		timefmt = self.config.getOption("timeshort_fmt")

		mtarget = hm_to_sec(self.config.getOption("hours"), self.config.getOption("minutes"))	# time to work in a month
		wtarget = mtarget/4						# time to work in a week

		# start time of current week
		wstart_d = (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
		wstart = time.mktime(wstart_d.timetuple())
		# end time of current week
		wend = time.mktime((wstart_d + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999).timetuple())
		wtime = self.log.getTimeBetween(wstart, wend)
		self.WorkedThisWeekLabel.setText(timefmt % sec_to_hm(wtime))
		if wtime > wtarget:
			self.LeftThisWeekLabel.setText("-"+timefmt % sec_to_hm(wtime - wtarget))
		else:
			self.LeftThisWeekLabel.setText(timefmt % sec_to_hm(wtarget - wtime))

		# start time of current month
		mstart = time.mktime(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timetuple())
		# end time of current month
		mend = time.mktime(d.replace(day=monthrange(d.year, d.month)[1], hour=23, minute=59, second=59, microsecond=999999).timetuple())
		mtime = self.log.getTimeBetween(mstart, mend)
		self.WorkedThisMonthLabel.setText(timefmt % sec_to_hm(mtime))
		if mtime > mtarget:
			self.LeftThisMonthLabel.setText("-"+timefmt % sec_to_hm(mtime - mtarget))
		else:
			self.LeftThisMonthLabel.setText(timefmt % sec_to_hm(mtarget - mtime))

		datefmt = self.config.getOption("datetime_fmt")
		longtimefmt = self.config.getOption("timelong_fmt")
		self.LastLogInLabel.setText(time.strftime(datefmt, time.localtime(self.log.getLastInTime())))
		self.LastLogOutLabel.setText(time.strftime(datefmt, time.localtime(self.log.getLastOutTime())))
		self.TotalTimeLabel.setText(longtimefmt % sec_to_hm(self.log.getTotalTime()))

	def openArchive(self):
		self.ArchiveBrowser = WLArchivalDataBrowser()

	def openConfig(self):
		self.ConfigBrowser = WLConfigBrowser(self)


def main():
	from signal import signal, SIGINT, SIG_DFL
	signal(SIGINT, SIG_DFL)

	global GLOBAL_DB, GLOBAL_CONFIG

	if len(sys.argv) > 1:
		GLOBAL_DB = Database(sys.argv[1])
	else:
		GLOBAL_DB = Database()
	GLOBAL_CONFIG = Config()

	Application = QtGui.QApplication([])
	Main = WLMain(Application)
	sys.exit(Application.exec_())