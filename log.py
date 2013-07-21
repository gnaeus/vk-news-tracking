# -*- coding: utf-8 -*-
'''Copyright (c) 2012 Dmitry Panyushkin'''
from time import ctime

def write(message='', filename='log.txt'):
    f = open(filename, 'a')
    try:
        f.write('[' + ctime() + '] ' + message + '\n')
    finally:
        f.close()