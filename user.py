# -*- coding: utf-8 -*-
'''Copyright (c) 2012 Dmitry Panyushkin'''

class User(object):
    __slots__ = ['id', 'requestTime', 'friends', 'followers', 'posts', 'reposts']
    def __init__(self, id, requestTime=None):
        self.id = id
        self.requestTime = requestTime
        self.friends = []
        self.followers = []
        self.posts = []
        self.reposts = []

#    def __repr__(self):  # for debug
#        return str(dict([(n, self.__getattribute__(n)) for n in self.__slots__]))