# -*- coding: utf-8 -*-
'''Copyright (c) 2012 Dmitry Panyushkin'''
import vktracking

def main():
    vk = vktracking.VkTracking(
        apiId=0,       # insert API ID here
        apiSecret='',  # insert API Secret Key here
        dbName='vk.db'
    )
    vk.RUN()

if __name__ == '__main__':
    main()
