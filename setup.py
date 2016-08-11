#!/usr/bin/env python2.7

try:
	from setuptools import setup
except ImportError:
	print "Cannot find setuptools; dependencies will not be installed."
	from distutils.core import setup

setup(
	name		=	"WorktimeLogger",
	version		=	"1.0.0",
	description	=	"Work time logger",
	author		=	"daneos",
	author_email=	"daneos@daneos.com",
	url			=	"https://github.com/daneos/WorktimeLogger",
	packages	=	["WorktimeLogger"],
	package_dir	=	{"WorktimeLogger": "."},
	package_data=	{"WorktimeLogger" : [ "ui/*.ui", "icons/*.png", "*.sqlite" ]},
	scripts		=	["WorktimeLogger"],
	zip_safe	=	False
)