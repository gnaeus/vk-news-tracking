# coding: utf-8
# my own extension for fast json decoding
import cjson

def loads(string, *args, **kwargs):
    return cjson.decode(string)

def dumps(string, *args, **kwargs):
    return cjson.encode(string)