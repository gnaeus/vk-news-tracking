# -*- coding: utf-8 -*-
'''Copyright (c) 2012 Dmitry Panyushkin'''
import sqlite3 as db
import os
import time
import csv
import vkontakte
import user
import log

QUEUE_SIZE = 5000
REQUESTS_PER_USER = 2
WAIT_TIMEOUT = 0.4
NEW_USER_TIME = 2**32
EXCLUDED_USER_TIME = 2**40
BIG_TIME = 2**40
MAX_ERRORS = 40
POST_LIMIT = 100
WANTED_POSTS = 60

def parseInt(data):
    try:
        res = int(data)
    except TypeError:
        res = 0
    return res

class VkTracking:

    def __init__(self, apiId, apiSecret, dbName, fileSuffix=''):
        log.write('application started')
        self.api = vkontakte.API(api_id=apiId, api_secret=apiSecret)
        self.connection = db.connect(database=dbName)
        self.connection.cursor().execute('PRAGMA cache_size = 20000').close()
        self.connection.cursor().execute('PRAGMA synchronous = OFF').close()
        self.connection.cursor().execute('PRAGMA journal_mode = OFF').close()
        self.connection.cursor().execute('PRAGMA temp_store = MEMORY').close()
        log.write('database connection established')
        self.fileSuffix = fileSuffix
        self.users = []
        self.errorTrace = ['[WRITE TRACE]']  # for debug in production

    def RUN(self):
        log.write('post tracking started')
        while True:
            self.testConnection()
            self.populateQueue()
            for user in self.users:
                self.getPostsAndFriends(user)
                self.calculateSurveyTime(user)
                self.getFollowers(user)
            self.storeData()

    def testConnection(self):
        try:
            self.requestTime = time.time()
            self.errorTrace.append(  # for debug in production
                '[%s] Test connection' % (time.ctime(self.requestTime))  # for debug in production
            )  # for debug in production
            self.api.getServerTime()
        except Exception, err:
            log.write('[FATAL ERROR] ' + str(err))
            self.storeData()
            log.write('[TERMINATED]')
            log.write('\n'.join(self.errorTrace), filename='trace.txt')  # for debug in production
            log.write('[TERMINATED]', filename='trace.txt')  # for debug in production
            exit()
        finally:
            print 'connection tested at', time.ctime(self.requestTime)
            self.wait()

    def wait(self):
        timeout = self.requestTime + WAIT_TIMEOUT - time.time()
        if timeout > 0:
            time.sleep(timeout)

    def populateQueue(self):
        timeBorder = time.time() + REQUESTS_PER_USER * QUEUE_SIZE * WAIT_TIMEOUT
        cursor = self.connection.cursor()
        cursor.execute('''
        SELECT id, request_time
        FROM users
        WHERE request_time < %s
        ORDER BY request_time ASC
        LIMIT %s
        ''' % (int(timeBorder), QUEUE_SIZE))
        self.users = [user.User(id, rTime) for id, rTime in cursor.fetchall()]
        oldUsersCount = len(self.users)
        if len(self.users) < QUEUE_SIZE:
            cursor.execute('''
            SELECT id, request_time
            FROM users
            WHERE request_time = %s
            ORDER BY id ASC
            LIMIT %s
            ''' % (NEW_USER_TIME, QUEUE_SIZE - oldUsersCount))
            self.users.extend((user.User(id, rTime) for id, rTime in cursor.fetchall()))
        newUsersCount = len(self.users) - oldUsersCount
        log.write('users queue populated with %s users and %s new users'
            % (oldUsersCount, newUsersCount))
        log.write('new users in queue: %s' % cursor.execute('''
        SELECT COUNT(*)
        FROM users
        WHERE request_time = %s
        ''' % NEW_USER_TIME).fetchone())
        cursor.close()

    def getPostsAndFriends(self, user):
        resp = self.get(owner_id=user.id, filter='owner')
        user.posts = [
            (post['id'], post['date'])
            for post in resp[1:]
            if not post.has_key('copy_owner_id')
        ]
        user.reposts = [
            (post['id'], post['date'], post['copy_owner_id'], post['copy_post_id'],
             parseInt(post['copy_post_date']))
            for post in resp[1:]
            if post.has_key('copy_post_date') and post.has_key('copy_post_id')
        ]
        user.friends = [post['copy_owner_id'] for post in resp[1:] if post.has_key('copy_owner_id')]
        self.wait()

    def getFollowers(self, user):
        resp = self.get(owner_id=user.id, filter='others')
        user.followers = [post['from_id'] for post in resp[1:] if post['from_id'] != post['to_id']]
        self.wait()

    def get(self, owner_id, filter='owner'):
        errorCount = 0
        self.errorTrace = ['[WRITE TRACE]']  # for debug in production
        while True:
            self.requestTime = time.time()
            try:
                return self.api.get('wall.get', owner_id=owner_id, count=POST_LIMIT, filter=filter)
            except vkontakte.VKError:
                print 'vk error at', time.ctime(self.requestTime)
                return []
            except Exception, err:
                errorCount += 1
                print 'network error at', time.ctime(self.requestTime)
                self.errorTrace.append(  # for debug in production
                    "[%s][%s]%s" % (errorCount, time.ctime(self.requestTime), err)  # for debug in production
                )  # for debug in production
                self.wait()
            if errorCount >= MAX_ERRORS:
                self.testConnection()

    def calculateSurveyTime(self, user):
        tBegin, tEnd = 0, BIG_TIME
        pLen, rpLen = 0, 0
        if user.posts:
            pLen = len(user.posts)
            tBegin, tEnd = user.posts[0][1], user.posts[-1][1]
        if user.reposts:
            rpLen = len(user.reposts)
            if tBegin < user.reposts[0][1]:
                tBegin = user.reposts[0][1]
            if tEnd > user.reposts[-1][1]:
                tEnd = user.reposts[-1][1]
        if pLen or rpLen:
            tEnd -= self.requestTime - tBegin
            addTime = WANTED_POSTS * (self.requestTime - tEnd) / (pLen + rpLen)
            user.requestTime = int(self.requestTime + addTime)
        else:
            user.requestTime = EXCLUDED_USER_TIME

    def storeData(self):
        log.write('backup database...')
        os.popen('cp vk.db vk.backup.db').close()
        self.saveUsers()
        self.saveToFiles()
        log.write('data stored')

    def saveUsers(self):
        log.write('storing users to database...')
        cursor = self.connection.cursor()
        # save user's request time
        cursor.executemany('''
        INSERT OR REPLACE INTO users VALUES (?,?)
        ''', [(user.id, user.requestTime) for user in self.users])
        # save friends and followers into users
        cursor.executemany('''
        INSERT OR IGNORE INTO users VALUES (?,?)
        ''', ((id, NEW_USER_TIME) for user in self.users for id in user.followers))
        cursor.executemany('''
        INSERT OR IGNORE INTO users VALUES (?,?)
        ''', ((id, NEW_USER_TIME) for user in self.users for id in user.friends if id > 0))
        cursor.executemany('''
        INSERT OR IGNORE INTO users VALUES (?,?)
        ''', ((id, EXCLUDED_USER_TIME) for user in self.users for id in user.friends if id < 0))
        self.connection.commit()
        cursor.close()

    def saveToDatabase(self):
        log.write('storing followers and posts to database...')
        cursor = self.connection.cursor()
        # save friends and followers into friends
        cursor.executemany('''
        INSERT OR IGNORE INTO followers VALUES (?,?)
        ''', ((user.id, id) for user in self.users for id in user.followers))
        cursor.executemany('''
        INSERT OR IGNORE INTO followers VALUES (?,?)
        ''', ((id, user.id) for user in self.users for id in user.friends))
        # save single posts
        cursor.executemany('''
        INSERT OR IGNORE INTO posts VALUES (?,?,?)
        ''', ((user.id, p[0], p[1]) for user in self.users for p in user.posts
            if p[0] != 0 and p[1] != 0))
        # save reposts
        cursor.executemany('''
        INSERT OR IGNORE INTO posts VALUES (?,?,?)
        ''', ((p[2], p[3], p[4]) for user in self.users for p in user.reposts
            if p[0] != 0 and p[1] != 0 and p[3] != 0 and p[4] != 0))
        cursor.executemany('''
        INSERT OR IGNORE INTO reposts VALUES (?,?,?,?,?)
        ''', ((user.id, p[0], p[1], p[2], p[3]) for user in self.users for p in user.reposts
            if p[0] != 0 and p[1] != 0 and p[3] != 0 and p[4] != 0))
        self.connection.commit()
        cursor.close()

    def saveToFiles(self):
        log.write('storing followers and posts to files...')
        # save friends and followers into friends
        f = open('followers' + self.fileSuffix + '.csv', 'ab')
        try:
            writer = csv.writer(f)
            writer.writerows(((user.id, id) for user in self.users for id in user.followers))
            writer.writerows(((id, user.id) for user in self.users for id in user.friends))
        finally:
            f.close()
        # save posts
        f = open('posts' + self.fileSuffix + '.csv', 'ab')
        try:
            writer = csv.writer(f)
            writer.writerows(((user.id, p[0], p[1]) for user in self.users for p in user.posts
                if p[0] != 0 and p[1] != 0))
            writer.writerows(((p[2], p[3], p[4]) for user in self.users for p in user.reposts
                if p[0] != 0 and p[1] != 0 and p[3] != 0 and p[4] != 0))
        finally:
            f.close()
        # save reposts
        f = open('reposts' + self.fileSuffix + '.csv', 'ab')
        try:
            writer = csv.writer(f)
            writer.writerows(((user.id, p[0], p[1], p[2], p[3]) for user in self.users
                for p in user.reposts if p[0] != 0 and p[1] != 0 and p[3] != 0 and p[4] != 0))
        finally:
            f.close()