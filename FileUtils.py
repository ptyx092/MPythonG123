#!/usr/bin/python2
#coding:utf-8

import os
import sys

MEDIA_FILES = '.mp3'
LRC_FILES = '.lrc'

#得到一个目录所有的mp3文件
def getMediaFiles(mediaDir=os.getcwd()):
    mediaFiles = []
    if os.path.isdir(mediaDir):
        for root,dirs,files in os.walk(mediaDir): #用os.walk函数遍历目录
            for media in files:
                name,ext = os.path.splitext(media) #分割文件名为去后缀和后缀
                if ext == MEDIA_FILES:
                    path = os.path.join(root,media) #组合成路径形式
                    expectLrc = path[:-len(MEDIA_FILES)] + LRC_FILES #尝试找歌词文件
                    if not os.path.exists(expectLrc):
                        expectLrc = ''
                    mediaFiles.append([name, path, expectLrc])
        else:
            return mediaFiles
    else:
        print 'the param is not a directory.'

def usage():
    print 'Usage: ' + sys.argv[0] + ' dir'
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) > 2:
        usage()
    else:
        mediaFiles = []
        if len(sys.argv) == 1:
            mediaFiles = getMediaFiles()
        else:
            mediaFiles = getMediaFiles(sys.argv[1])
        for name,path,lrc in mediaFiles:
            print name + ' ' + path + ' ' + lrc

