import json
import os
import random
import string
import sys
import threading
from enum import Enum
from json import JSONDecodeError
import gi
from mpg123 import Mpg123, Out123
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk
from gi.repository.Gtk import License, Widget, ListBox, ListBoxRow
from gi.repository import Gio, GLib, GObject


class ItemMusic(GObject.GObject):
    musicName = GObject.Property(type=str, default="")
    musicPath = GObject.Property(type=str, default="")
    musicIndex = GObject.Property(type=int, default=0)

    def __init__(self, name, path='', index=0):
        super().__init__()
        self.props.musicName = name
        self.props.musicPath = path
        self.props.musicIndex = index

    def __repr__(self):
        return f'music name: {self.musicName}, path: {self.musicPath}, index: {self.musicIndex}'

    def __eq__(self, other):
        return True if self.path == other.path else False

    @property
    def name(self):
        return self.props.musicName

    @property
    def path(self):
        return self.props.musicPath

    @property
    def index(self):
        return self.props.musicIndex


class PlayMode(Enum):
    loop = 0
    random = 1
    singleLoop = 2
    sequence = 3

    def next(self):
        return PlayMode.__new__(PlayMode, (self.value + 1) % 4)


class Player:
    """使用mpg123的python wrapper包封装一个播放器"""

    class PlayState(Enum):
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
        self.state = self.PlayState.stop
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
            self.state = self.PlayState.playing
            self.event.set()

    def playDone(self, isNormalDone):
        print("播放完成")
        self.stop()
        self.callback(isNormalDone)

    def pause(self):
        if self.state == self.PlayState.playing:
            self.event.clear()
            self.state = self.PlayState.pause
        elif self.state == self.PlayState.pause:
            self.playInternal()

    def stop(self):
        if self.state != self.PlayState.stop:
            self.event.clear()
            self.state = self.PlayState.stop


class MPGSettings:
    """设置管理"""

    def __init__(self):
        self.__dirs = 'dirs'
        self.__mode = 'mode'

        self.defaultDirs = [os.path.expanduser('~/Music')]
        self.defaultMode = PlayMode.sequence

        # 配置文件路径
        self.__settingFile = os.path.join(GLib.get_user_config_dir(), 'MPythonG123', 'mpg_config.json')
        self.__settings = self.readSettings()

    def __str__(self):
        return json.dumps(self.__settings)

    @property
    def keyDirs(self):
        return self.__dirs

    @property
    def keyMode(self):
        return self.__mode

    def storeSettings(self):
        try:
            fp = open(self.__settingFile, 'w+')
            fp.write(json.dumps(self.__settings))
        except FileNotFoundError:
            os.mkdir(os.path.dirname(self.__settingFile))  # 创建目录
            with open(self.__settingFile, 'w+') as newfp:
                newfp.write(json.dumps(self.__settings))

    def readSettings(self):
        try:
            settings = open(self.__settingFile, 'r').read()
            print(f'settings {settings}')
            return json.loads(settings)
        except (FileNotFoundError, JSONDecodeError) as error:
            print(f'read settings from {self.__settingFile} failed, error: {error}')
            return {}

    def getSetting(self, key: str):
        try:
            if key == self.keyMode:
                return PlayMode(self.__settings[key])
            else:
                return self.__settings[key]
        except (KeyError, TypeError) as error:
            if key == self.keyMode:
                return self.defaultMode
            elif key == self.keyDirs:
                return self.defaultDirs

    def updateSetting(self, key: str, value):
        if key == self.keyMode:
            newValue = value.value
        else:
            newValue = value

        try:
            if self.__settings[key] != newValue:
                self.__settings[key] = newValue
                self.storeSettings()
                return True
        except (KeyError, TypeError) as error:  # 为空的时候取不到值
            self.__settings[key] = newValue
            self.storeSettings()
            return True

        return False

    def dumpSettings(self):
        print(self.settings)


class Model:
    """MVVM之M"""

    def __init__(self):
        self.callbackVol = None
        self.callbackMode = None
        self.callbackState = None
        self.callbackData = None
        self.player = Player(self.callbackFromPlayer)
        self.settings = MPGSettings()

        self.musicCurrent = None
        self.musicSelected = None
        self.musicFileList = list()
        self.randomList = list()

    def registerCallbacks(self, **kwargs):
        print(kwargs)
        self.callbackData = kwargs.get('data')
        self.callbackState = kwargs.get('state')
        self.callbackMode = kwargs.get('mode')
        self.callbackVol = kwargs.get('vol')

    def updateDirs(self, newDirs: list):
        self.stop()
        if self.settings.updateSetting(self.settings.keyDirs, newDirs):
            self.loadMusicData()
        else:  # 文件夹配置项变了，不一定里面的内容没变，所以还是需要载入
            self.loadMusicData()

    def updateMode(self):
        oldMode = self.settings.getSetting(self.settings.keyMode)

        if oldMode == PlayMode.random:
            self.randomList.clear()

        newMode = oldMode.next()
        if newMode == PlayMode.random and self.musicCurrent is not None:
            self.randomList.append(self.musicCurrent.index)

        self.settings.updateSetting(self.settings.keyMode, newMode)
        self.callbackMode(newMode)

    def callbackFromPlayer(self, isNormalDone):
        print(f"callback from player: {isNormalDone}")
        if isNormalDone:
            GLib.idle_add(self.playPrevNext, True)  # call from another thread

    def reset(self):
        self.musicCurrent = None
        self.musicSelected = None
        self.musicFileList.clear()

    def play(self, music: ItemMusic, randomAdd=True):
        if music is not None:
            self.player.play(music.path)
            self.musicCurrent = music
            self.callbackState(self.player.state, self.musicCurrent)

            mode = self.settings.getSetting(self.settings.keyMode)
            if randomAdd and (mode == PlayMode.random):
                index = music.index
                if index not in self.randomList:
                    self.randomList.append(index)

    def stop(self):
        self.player.stop()
        self.callbackState(self.player.state, self.musicCurrent)

    def pause(self):
        self.player.pause()
        self.callbackState(self.player.state, self.musicCurrent)

    def togglePlay(self):
        if self.player.state == self.player.PlayState.playing:  # 正在播放，则暂停
            self.pause()
        else:  # 没有在播放
            if self.musicSelected is not None:  # 选择的音乐记录不为空
                self.play(self.musicSelected)  # 播放选中的音乐
            else:  # 无正在播放的记录
                if self.musicCurrent is not None:  # 有选择的音乐
                    self.play(self.musicCurrent)

    def showLyrics(self, show: bool):
        pass

    def playPrevNext(self, isDirectionNext):
        if self.musicCurrent is None:
            index = 0
        else:
            index = self.musicCurrent.index

        size = len(self.musicFileList)

        mode = self.settings.getSetting(self.settings.keyMode)
        if mode == PlayMode.loop:
            if isDirectionNext:
                nextS = index + 1 if index < size - 1 else 0
            else:
                nextS = index - 1 if index > 0 else size - 1
        elif mode == PlayMode.sequence:
            if isDirectionNext:
                nextS = index + 1 if index < size - 1 else - 1
            else:
                nextS = index - 1 if index > 0 else - 1
        elif mode == PlayMode.singleLoop:
            nextS = index
        elif mode == PlayMode.random:
            print(f'random list {self.randomList}')
            if isDirectionNext:
                if len(self.randomList) >= size:
                    self.randomList.clear()

                while True:
                    nextS = random.randint(0, size - 1)
                    if (nextS != index) and (nextS not in self.randomList):
                        break

                self.randomList.append(nextS)
                print(f'random next {nextS}')
            else:
                if len(self.randomList) >= 2:
                    nextS = self.randomList.pop(-2)
                else:
                    return

        if nextS < 0:
            self.pause()
        else:
            music = self.musicFileList[nextS]
            self.play(music, randomAdd=False)
        self.callbackState(self.player.state, self.musicCurrent)

    def loadMusicData(self):
        self.reset()

        # 从设置的目录中获取数据
        dirs = self.settings.getSetting(self.settings.keyDirs)
        print(dirs)

        index = 0
        for dd in dirs:
            try:
                files = os.listdir(dd)
                for ff in files:
                    if (not ff.startswith('.')) and ff.endswith('.mp3'):
                        name, _ = os.path.splitext(ff)
                        item = ItemMusic(name=name, path=os.path.join(dd, ff), index=index)
                        index += 1
                        self.musicFileList.append(item)
            except PermissionError as error:
                print(error)
        print(self.musicFileList)

        # 获取播放模式设置
        playMode = self.settings.getSetting(self.settings.keyMode)

        self.callbackData(self.musicFileList, playMode)

    def adjustVol(self, up: bool):
        pass


class MPythonG123Window(Gtk.Window):
    """主窗口"""

    def __init__(self, model: Model):
        super().__init__(title="MPythonG123")

        # VM对象
        self.floatWindow = False
        self.model = model

        self.programName = 'MPythonG123 Player'

        # liststore和filter
        self.listBox = Gtk.ListBox()
        self.ListStoreMusic = Gio.ListStore.new(ItemMusic)

        # 一个VBOX
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # play button, 需要控制其状态
        self.buttonPlay = None
        self.buttonMode = None

        # headbar
        self.hb = None

        # 窗口基础属性
        self.set_border_width(10)
        self.set_default_size(640, 480)
        self.preSize = (640, 480)

        # titlebar
        self.customTitlebar()

        # 主区域，显示歌曲文件列表，并显示歌词
        self.mainArea()

        self.model.registerCallbacks(data=self.changedData, state=self.changedPlayState, mode=self.changedMode,
                                     vol=self.changedVol)

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

        # 播放模式按钮
        self.buttonMode = Gtk.Button.new_from_icon_name("go-jump-symbolic", Gtk.IconSize.BUTTON)
        box.add(self.buttonMode)
        self.buttonMode.connect("clicked", self.onClickMode)

        # 悬浮模式按钮
        buttonFloat = Gtk.Button.new_from_icon_name("orientation-landscape-symbolic", Gtk.IconSize.BUTTON)
        box.add(buttonFloat)
        buttonFloat.connect("clicked", self.onClickFloat)

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

        # 歌词按钮
        # button = Gtk.Button.new_from_icon_name("format-justify-fill-symbolic", Gtk.IconSize.BUTTON)
        # box.add(button)

        # 加入headbar
        self.hb.pack_end(box)

        # 设定自定义的titlebar
        self.set_titlebar(self.hb)

    def mainArea(self):
        hbox1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(hbox1, True, True, 0)
        self.vbox.pack_end(hbox2, False, True, 0)

        self.listBox.connect('row-activated', self.onRowActived)
        self.listBox.connect('row-selected', self.onRowSelected)
        self.listBox.set_activate_on_single_click(False)
        self.listBox.bind_model(model=self.ListStoreMusic, create_widget_func=self.createListRow)

        buttonHolder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        buttonHolder.connect('clicked', self.onClickOpen)
        self.listBox.set_placeholder(placeholder=buttonHolder)

        scrollWindow = Gtk.ScrolledWindow()
        scrollWindow.set_vexpand(True)

        scrollWindow.add(self.listBox)

        hbox1.pack_start(scrollWindow, True, True, 0)

        self.add(self.vbox)

    def onRowActived(self, lb: ListBox, lbr: ListBoxRow):
        index = lbr.get_index()
        im = self.ListStoreMusic.get_item(index)
        print(f"Row {index} activated, music {im}")
        self.model.play(im)

    def onRowSelected(self, lb: ListBox, lbr: ListBoxRow):
        if lbr is not None:
            index = lbr.get_index()
            im = self.ListStoreMusic.get_item(index)
            print(f"Row {index} selected, {im}")
            self.model.musicSelected = im

    def createListRow(self, item: ItemMusic):
        return Gtk.Label(label=item.name)

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
            self.model.updateDirs(dirs)
            self.hb.props.title = self.programName
        else:
            openD.destroy()

    def onClickAbout(self, widget: Widget):
        about = self.dialogAbout()
        response = about.run()
        about.destroy()

    def onClickPlayPause(self, widget: Widget):
        self.model.togglePlay()

    def onClickPrev(self, widget):
        print("previous")
        self.model.playPrevNext(False)

    def onClickNext(self, widget):
        print("next")
        self.model.playPrevNext(True)

    def onClickMode(self, widget):
        self.model.updateMode()

    def onClickFloat(self, _):
        if self.floatWindow:
            self.set_keep_above(False)
            self.vbox.show()
            self.set_resizable(True)
            self.resize(self.preSize[0], self.preSize[1])
            self.floatWindow = False
        else:
            self.preSize = self.get_size()
            self.set_keep_above(True)
            self.vbox.hide()
            rect = self.get_titlebar().get_allocated_size().allocation
            # print(dir(rect))
            # print(f'title_bar: {rect.x, rect.y, rect.width, rect.height}')
            # self.set_modal(True)
            self.set_size_request(rect.width, 1)
            self.resize(rect.width, 1)
            self.set_resizable(False)
            self.floatWindow = True

    def changedMode(self, newMode):
        if newMode == PlayMode.sequence:
            icon = 'media-playlist-consecutive-symbolic'
        elif newMode == PlayMode.singleLoop:
            icon = 'media-playlist-repeat-song-symbolic'
        elif newMode == PlayMode.loop:
            icon = 'media-playlist-repeat-symbolic'
        elif newMode == PlayMode.random:
            icon = 'media-playlist-shuffle-symbolic'

        icon = Gio.ThemedIcon(name=icon)
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON)
        self.buttonMode.set_image(image=image)

    def changedPlayState(self, playState: Player.PlayState, music: ItemMusic):
        if playState == Player.PlayState.playing:
            icon_name = 'media-playback-pause-symbolic'
            if music is not None:
                self.hb.props.title = music.name
                self.listBox.select_row(self.listBox.get_row_at_index(music.index))
        elif playState == Player.PlayState.pause:
            icon_name = 'media-playback-start-symbolic'
        elif playState == Player.PlayState.stop:
            icon_name = 'media-playback-start-symbolic'
            self.hb.props.title = self.programName

        icon = Gio.ThemedIcon(name=icon_name)
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON)
        self.buttonPlay.set_image(image=image)

    def changedData(self, files: list, mode: PlayMode):
        if self.ListStoreMusic is not None:
            self.ListStoreMusic.remove_all()
            for ff in files:
                self.ListStoreMusic.append(ff)

            if self.ListStoreMusic.get_n_items() > 0:
                self.listBox.select_row(self.listBox.get_row_at_index(0))

        self.changedMode(mode)

    def onClickVolMinus(self, widget):
        self.model.onViewVol(False)

    def onClickVolPlus(self, widget):
        self.model.onViewVol(True)

    def changedVol(self, newVol: int):
        pass


def main(args: list):
    model = Model()
    view = MPythonG123Window(model)

    view.connect("destroy", Gtk.main_quit)
    view.show_all()

    model.loadMusicData()

    Gtk.main()


if __name__ == '__main__':
    main(sys.argv)
