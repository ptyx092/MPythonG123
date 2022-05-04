import os
import string
import subprocess
import sys
import threading
import time
from enum import Enum

import gi
from mpg123 import Mpg123, Out123

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository.Gtk import License, Widget, ListBox, ListBoxRow
from gi.repository import Gio
from gi.repository import GObject


class ItemMusic(GObject.GObject):
    musicName = GObject.Property(type=str, default="")
    musicPath = GObject.Property(type=str, default="")
    musicIndex = GObject.Property(type=int, default=0)

    def __init__(self, musicName, musicPath='', musicIndex=0):
        super().__init__()
        self.props.musicName = musicName
        self.props.musicPath = musicPath
        self.props.musicIndex = musicIndex

    def __repr__(self):
        return f'music name: {self.musicName}, path: {self.musicPath}, index: {self.musicIndex}'

    def __cmp__(self, other):
        if self.musicPath == other.musicPath:
            return 0
        else:
            return 1

    def getMusicName(self):
        return self.props.musicName

    def getMusicPath(self):
        return self.props.musicPath

    def getMusicIndex(self):
        return self.props.musicIndex


class VM:
    """MVVM之VM"""

    def __init__(self):
        self.view = None
        self.model = None

    def setVandM(self, view, model):
        self.view = view
        self.model = model

    def onViewDirsChanged(self, newDirs: list):
        if self.model is not None:
            newFiles = self.model.fetchMusicFiles(newDirs)
            self.model.storeSettings()

    def onModelDataChanged(self, newFiles: list):
        if self.view is not None:
            self.view.dataChanged(newFiles)

    def onViewMusicActivated(self, music: ItemMusic):
        if self.model is not None:
            self.model.play(music)

    def onViewMusicSelected(self, music: ItemMusic):
        if self.model is not None:
            self.model.selected(music)

    def onViewTogglePlayClicked(self):
        if self.model is not None:
            self.model.togglePlay()

    def onModelPlayStateChanged(self, playState: bool):
        if self.view is not None:
            self.view.playStateChanged(playState)

    def onViewVol(self, up: bool):
        if self.model is not None:
            self.model.adjustVol(up)

    def whichIsPlaying(self):
        if self.model is not None:
            return self.model.musicCurrent
        else:
            return None

    def onModelAutoNext(self, music):
        if self.view is not None:
            self.view.updateSelection(music)

    def onViewPrevNext(self, isDirectionNext):
        if self.model is not None:
            self.model.playPrevNext(isDirectionNext)


class MPythonG123Window(Gtk.Window):
    """主窗口"""

    def __init__(self, vm: VM):
        super().__init__(title="MPythonG123")

        # VM对象
        self.vm = vm

        self.programName = 'MPythonG123 Player'

        # liststore和filter
        self.listBox = None
        self.ListStoreMusic = None

        # play button, 需要控制其状态
        self.buttonPlay = None

        # headbar
        self.hb = None

        # 窗口基础属性
        self.set_border_width(10)
        self.set_default_size(680, 480)

        # titlebar
        self.customTitlebar()

        # 主区域，显示歌曲文件列表，并显示歌词
        self.mainArea()

    def customTitlebar(self):
        # 自定义titlebar
        self.hb = Gtk.HeaderBar()
        self.hb.set_show_close_button(True)
        self.hb.props.title = self.programName

        # 左侧的操控按钮
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        Gtk.StyleContext.add_class(box.get_style_context(), "linked")

        # 左侧的关于按钮
        button = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        box.add(button)
        button.connect("clicked", self.onClickAbout)

        # 打开目录
        button = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        box.add(button)
        button.connect("clicked", self.onClickOpen)

        # 音量加减
        # button = Gtk.Button.new_with_label('-')
        # box.add(button)
        # button.connect("clicked", self.onClickVolMinus)
        #
        # button = Gtk.Button.new_with_label('+')
        # box.add(button)
        # button.connect("clicked", self.onClickVolPlus)

        # 加入headbar
        self.hb.pack_start(box)

        # 右侧的操控按钮
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        Gtk.StyleContext.add_class(box.get_style_context(), "linked")

        # 上一首按钮
        button = Gtk.Button.new_from_icon_name("media-seek-backward-symbolic", Gtk.IconSize.BUTTON)
        box.add(button)
        button.connect("clicked", self.onClickPrev)

        # 下一首按钮
        button = Gtk.Button.new_from_icon_name("media-seek-forward-symbolic", Gtk.IconSize.BUTTON)
        box.add(button)
        button.connect("clicked", self.onClickNext)

        # 播放按钮
        self.buttonPlay = Gtk.Button.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.buttonPlay.connect('clicked', self.onClickPlayPause)
        box.add(self.buttonPlay)

        # 随机按钮
        # button = Gtk.Button.new_from_icon_name("go-jump-symbolic", Gtk.IconSize.BUTTON)
        # box.add(button)

        # 歌词按钮
        # button = Gtk.Button.new_from_icon_name("format-justify-fill-symbolic", Gtk.IconSize.BUTTON)
        # box.add(button)

        # 加入headbar
        self.hb.pack_end(box)

        # 设定自定义的titlebar
        self.set_titlebar(self.hb)

    def mainArea(self):
        # 一个VBOX
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        hbox1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(hbox1, expand=True, fill=True, padding=10)
        vbox.pack_end(hbox2, False, True, 0)

        self.listBox = Gtk.ListBox()
        self.listBox.connect('row-activated', self.onRowActived)
        self.listBox.connect('row-selected', self.onRowSelected)
        self.listBox.set_activate_on_single_click(False)
        self.ListStoreMusic = Gio.ListStore.new(ItemMusic)
        self.listBox.bind_model(model=self.ListStoreMusic, create_widget_func=self.createListRow)

        buttonHolder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        buttonHolder.connect('clicked', self.onClickOpen)
        self.listBox.set_placeholder(placeholder=buttonHolder)
        # for music in self._musicList:
        #     item = ItemMusic(music)
        #     self._musicListModel.append(item)

        scrollWindow = Gtk.ScrolledWindow()
        scrollWindow.set_vexpand(True)

        scrollWindow.add(self.listBox)

        hbox1.pack_start(scrollWindow, True, True, 0)

        self.add(vbox)

    def onRowActived(self, lb: ListBox, lbr: ListBoxRow):
        index = lbr.get_index()
        print(f"Row {index} activated")
        im = self.ListStoreMusic.get_item(index)
        self.vm.onViewMusicActivated(im)

    def onRowSelected(self, lb: ListBox, lbr: ListBoxRow):
        if lbr is not None:
            index = lbr.get_index()
            print(f"Row {index} selected")
            im = self.ListStoreMusic.get_item(index)
            self.vm.onViewMusicSelected(im)

    def createListRow(self, item: ItemMusic):
        label = Gtk.Label(label=item.getMusicName())
        return label

    def dialogDir(self):
        openD = Gtk.FileChooserDialog(title="请选择歌曲文件目录", parent=self)
        openD.set_destroy_with_parent(True)
        openD.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        openD.set_select_multiple(True)
        openD.add_button('打开', Gtk.ResponseType.OK)
        openD.add_button('取消', Gtk.ResponseType.CANCEL)
        return openD

    def dialogAbout(self):
        about = Gtk.AboutDialog(transient_for=self)
        about.set_logo_icon_name('help-about-symbolic')
        about.set_license_type(License.MIT_X11)
        about.set_authors(['PTYX'])
        about.set_program_name('Python Player based on MPG123')
        about.set_website('https://github.com/ptyx092/mpythong123')
        about.set_website_label('访问Github项目主页')
        about.set_destroy_with_parent(True)
        about.set_copyright("(c) PTYX/ptyx")
        about.set_sensitive(True)
        return about

    def onClickOpen(self, widget: Widget):
        openD = self.dialogDir()
        response = openD.run()
        if response == Gtk.ResponseType.OK:
            dirs = openD.get_filenames()
            openD.destroy()
            print(dirs)
            self.vm.onViewDirsChanged(dirs)
            self.hb.props.title = self.programName
        else:
            openD.destroy()

    def onClickAbout(self, widget: Widget):
        about = self.dialogAbout()
        response = about.run()
        about.destroy()

    def onClickPlayPause(self, widget: Widget):
        self.vm.onViewTogglePlayClicked()

    def onClickPrev(self, widget):
        print("previous")
        self.vm.onViewPrevNext(False)

    def onClickNext(self, widget):
        print("next")
        self.vm.onViewPrevNext(True)

    def playStateChanged(self, playState: bool):
        icon_name = 'media-playback-pause-symbolic' if playState == Player.PlayerState.playing else 'media-playback-start-symbolic'
        icon = Gio.ThemedIcon(name=icon_name)
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON)
        self.buttonPlay.set_image(image=image)

        play = self.vm.whichIsPlaying()
        if play is not None:
            self.hb.props.title = play.getMusicName()

    def updateSelection(self, music):
        self.listBox.select_row(self.listBox.get_row_at_index(music.getMusicIndex()))

    def dataChanged(self, files: list):
        if self.ListStoreMusic is not None:
            self.ListStoreMusic.remove_all()
            for ff in files:
                self.ListStoreMusic.append(ff)

            if self.ListStoreMusic.get_n_items() > 0:
                self.listBox.select_row(self.listBox.get_row_at_index(0))

    def onClickVolMinus(self, widget):
        self.vm.onViewVol(False)

    def onClickVolPlus(self, widget):
        self.vm.onViewVol(True)


class Model:
    """MVVM之M"""

    def __init__(self, vm: VM):

        self.vm = vm

        self.player = Player(self.callbackFromPlayer)

        # 配置文件路径
        self.settingFilePath = os.path.abspath(os.path.expanduser('~/.MPythonG123/dirs.txt'))

        # comand = ['mpg123', '--remote', '--keep-open', '--remote-err']
        # self.mpg123 = subprocess.Popen(comand, stdin=subprocess.PIPE, universal_newlines=True, bufsize=1)
        self.isPlaying = False
        self.musicCurrent = None
        self.musicSelected = None
        self.musicList = None
        self.musicFileList = None
        self.musicDirs = None
        self.volume = 30
        self.volumeStep = 5

        self.firstRun = True

    def callbackFromPlayer(self, isNormalDone):
        print(f"callback from player: {isNormalDone}")
        if isNormalDone:
            index = self.musicCurrent.getMusicIndex()
            size = len(self.musicFileList)
            nextS = index + 1 if index < size - 1 else 0
            music = self.musicFileList[nextS]
            self.play(music)
            self.vm.onModelAutoNext(music)

    def reset(self):
        if self.isPlaying:
            self.stop()
        self.musicCurrent = None
        self.musicSelected = None
        self.musicList = None
        self.musicDirs = None

    def play(self, music: ItemMusic):
        if music is not None:
            # cmd = [f'l {music.getMusicPath()}\n']
            # self.mpg123.stdin.writelines(cmd)

            self.player.play(music.getMusicPath())

            self.musicCurrent = music
            self.vm.onModelPlayStateChanged(self.player.state)

    def playList(self):
        if self.musicFileList is not None:
            pass

    def stop(self):
        # cmd = ['s\n']
        # self.mpg123.stdin.writelines(cmd)
        self.player.stop()
        self.vm.onModelPlayStateChanged(self.player.state)

    def pause(self):
        # cmd = ['p\n']
        # self.mpg123.stdin.writelines(cmd)

        self.player.pause()
        self.vm.onModelPlayStateChanged(self.player.state)

    def selected(self, music: ItemMusic):
        if music is not None:
            self.musicSelected = music

    def togglePlay(self):
        if self.player.state == self.player.PlayerState.playing:  # 正在播放，则暂停
            self.pause()
        else:  # 没有在播放
            if self.musicCurrent is not None:  # 正在播放的音乐记录不为空
                self.play(self.musicCurrent)  # 播放选中的音乐
            else:  # 无正在播放的记录
                if self.musicSelected is not None:  # 有选择的音乐
                    self.play(self.musicSelected)

    def randomPlay(self):
        pass

    def showLyrics(self, show: bool):
        pass

    def openDirs(self):
        pass

    def playPrevNext(self, isDirectionNext):
        if self.musicCurrent is None:
            index = self.musicSelected.getMusicIndex()
        else:
            index = self.musicCurrent.getMusicIndex()
        size = len(self.musicFileList)
        if isDirectionNext:
            nextS = index + 1 if index < size - 1 else 0
        else:
            nextS = index - 1 if index > 0 else size - 1
        music = self.musicFileList[nextS]
        self.play(music)
        self.vm.onModelAutoNext(music)

    def fetchMusicFiles(self, dirs: list):
        self.reset()
        self.musicList = []
        self.musicFileList = []
        self.musicDirs = dirs
        print(dirs)
        index = 0
        for dd in dirs:
            ddresult = []
            try:
                files = os.listdir(dd)
                for ff in files:
                    if (not ff.startswith('.')) and ff.endswith('.mp3'):
                        ddresult.append(ff)
                        name, _ = os.path.splitext(ff)
                        item = ItemMusic(musicName=name, musicPath=os.path.join(dd, ff), musicIndex=index)
                        index += 1
                        self.musicFileList.append(item)
                self.musicList.append((dd, ddresult))
            except PermissionError as error:
                print(error)
        print(self.musicFileList)
        self.vm.onModelDataChanged(self.musicFileList)
        return self.musicFileList

    def adjustVol(self, up: bool):
        if up:
            if self.volume + self.volumeStep > 100:
                self.volume = 100
            else:
                self.volume += self.volumeStep
        else:
            if self.volume - self.volumeStep < 0:
                self.volume = 0
            else:
                self.volume -= self.volumeStep

        # cmd = [f'v {self.volume}\n']
        # self.mpg123.stdin.writelines(cmd)

    def storeSettings(self):

        print(self.settingFilePath)
        if self.musicDirs is not None:
            try:
                fp = open(self.settingFilePath, 'w+')
            except FileNotFoundError:
                os.mkdir(os.path.dirname(self.settingFilePath))  # 创建目录
                fp = open(self.settingFilePath, 'w+')
            finally:
                settings = [f'{x}\n' for x in self.musicDirs]
                fp.writelines(settings)
                fp.close()

    def readSettings(self):
        try:
            fp = open(self.settingFilePath, 'r')
            lines = fp.readlines()
            print(f'settings {lines}')
            if len(lines) > 0:
                dirs = [x.strip('\n') for x in lines]
                self.firstRun = False
                self.fetchMusicFiles(dirs)
        except FileNotFoundError:
            self.firstRun = True
        finally:
            if fp:
                fp.close()


class Player:
    """使用mpg123的python wrapper包封装一个播放器"""

    class PlayerState(Enum):
        playing = 0
        stop = 1
        pause = 2

    class MyThread(threading.Thread):
        def __init__(self, out123, callback, event):
            threading.Thread.__init__(self)
            self.mpg123 = None
            self.out123 = out123
            self.length = 0
            self.count = 0
            self.callback = callback
            self.event = event

        def update(self, mpg123, length):
            self.mpg123 = mpg123
            self.length = length
            self.count = 0

        def run(self):
            while True:
                self.event.wait()
                print("开始线程")
                for frame in self.mpg123.iter_frames():
                    # if _gState != self.PlayerState.playing:
                    #     break
                    if not self.event.isSet():
                        break
                    self.out123.play(frame)
                    self.count += 1
                    # print(f'total: {self.length}, current: {self.count}')

                self.callback(self.count >= self.length)
                print("结束线程")

    def __init__(self, callback):
        self.playedFrame = 0
        self.frameLength = 0
        self.out123 = Out123()
        self.state = self.PlayerState.stop
        self.mpg = None
        self.ThreadPlay = None
        self.callback = callback  # 当状态变化时调用callback

        self.event = threading.Event()
        self.ThreadPlay = self.MyThread(self.out123, self.playDone, self.event)
        self.ThreadPlay.setDaemon(True)
        self.ThreadPlay.start()

    def play(self, filePath: string):

        self.stop()
        self.mpg = Mpg123(filePath)
        self.frameLength = self.mpg.frame_length()
        self.playedFrame = 0
        self.ThreadPlay.update(self.mpg, self.frameLength)
        rate, channels, encoding = self.mpg.get_format()
        self.out123.start(rate=rate, channels=channels, encoding=encoding)
        self.playInternal()

    def playInternal(self):
        if self.mpg is not None:
            self.state = self.PlayerState.playing
            self.event.set()

    def playDone(self, isNormalDone):
        print("播放完成")
        self.stop()
        self.callback(isNormalDone)

    def pause(self):
        if self.state == self.PlayerState.playing:
            self.event.clear()
            self.state = self.PlayerState.pause
        elif self.state == self.PlayerState.pause:
            self.playInternal()

    def stop(self):
        if self.state != self.PlayerState.stop:
            self.event.clear()
            self.state = self.PlayerState.stop


def main(args: list):
    vm = VM()
    m = Model(vm)
    v = MPythonG123Window(vm)

    vm.setVandM(v, m)

    def appQuit(win: MPythonG123Window):
        print(win)
        # if m.mpg123 is not None:
        #     m.mpg123.terminate()

        Gtk.main_quit()

    v.connect("destroy", appQuit)
    v.show_all()
    m.readSettings()
    Gtk.main()


if __name__ == '__main__':
    main(sys.argv)
