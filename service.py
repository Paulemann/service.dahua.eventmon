#!/usr/bin/python
# -*- coding: utf-8 -*-

import pycurl
import os, time, json, random, string
import xbmc, xbmcaddon, xbmcgui, xbmcvfs
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from threading import Thread

__addon__        = xbmcaddon.Addon()
__addon_id__     = __addon__.getAddonInfo('id')
__addon_path__   = __addon__.getAddonInfo('path')
__profile__      = __addon__.getAddonInfo('profile')

__getSetting__   = __addon__.getSetting
__setSetting__   = __addon__.setSetting
__localize__     = __addon__.getLocalizedString

__loading__      = os.path.join(__addon_path__, 'loading.gif')
__settings__     = os.path.join(__profile__, 'settings.xml')

# Constants
ACTION_PREVIOUS_MENU = 10
ACTION_STOP = 13
ACTION_NAV_BACK = 92
ACTION_BACKSPACE = 110

posIndex = 0
MAXCAMS = 4


def log(message,loglevel=xbmc.LOGNOTICE):
    xbmc.log(msg='[{}] {}'.format(__addon_id__, message), level=loglevel)


class CamLifeview(xbmcgui.WindowDialog):
    def __init__(self, url, username, password, position):
        self.cam = {
            'url': url,
            'username': username,
            'password': password,
            }
        self.session = None
        self.control = None
        self.position = position

        # Dahua cams use Digest Authentication scheme
        self.auth = 'digest'

        # Defaults:
        #self.width       = 320
        #self.height      = 180
        #self.padding     = 20
        #self.alignment   = 0
        #self.autoClose   = True
        #self.duration    = 15000
        #self.interval    = 500
        #self.aspectRatio = 1
        #self.fixPosition = True
        self.loadSettings()


    def loadSettings(self):
        self.width       = int(float(__getSetting__('width')))
        self.height      = int(float(__getSetting__('height')))
        self.padding     = int(float(__getSetting__('padding')))
        self.alignment   = int(float(__getSetting__('alignment')))
        self.autoClose   = bool(__getSetting__('autoClose') == 'true')
        self.duration    = int(float(__getSetting__('duration')) * 1000)
        self.interval    = int(float(__getSetting__('interval')))
        self.aspectRatio = int(float(__getSetting__('aspectRatio')))
        self.fixPosition = bool(__getSetting__('fixPosition') == 'true')


    def coordinates(self, position):
        WIDTH  = 1280
        HEIGHT = 720

        w = self.width
        h = self.height
        p = self.padding

        if self.alignment == 0: # vertical right, top to bottom
            x = WIDTH - (w + p)
            y = p + position * (h + p)
        if self.alignment == 1: # vertical left, top to bottom
            x = p
            y = p + position * (h + p)
        if self.alignment == 2: # horizontal top, left to right
            x = p + position * (w + p)
            y = p
        if self.alignment == 3: # horizontal bottom, left to right
            x = p + position * (w + p)
            y = HEIGHT - (h + p)
        if self.alignment == 4: # square right
            x = WIDTH - (2 - position%2) * (w + p)
            y = p + position/2 * (h + p)
        if self.alignment == 5: # square left
            x = p + position%2 * (w + p)
            y = p + position/2 * (h + p)
        if self.alignment == 6: # vertical right, bottom to top
            x = WIDTH - (w + p)
            y = HEIGHT - (position + 1) * (h + p)
        if self.alignment == 7: # vertical left, bottom to top
            x = p
            y = HEIGHT - (position + 1) * (h + p)
        if self.alignment == 8: # horizontal top, right to left
            x = WIDTH - (position + 1) * (w + p)
            y = p
        if self.alignment == 9: # horizontal bottom, right to left
            x = WIDTH - (position + 1) * (w + p)
            y = HEIGHT - (h + p)

        return x, y, w, h


    def auth_get(self, url, *args, **kwargs):
        if not self.session:
            self.session = requests.Session()

            if self.auth == 'digest':
                self.session.auth = HTTPDigestAuth(*args)
            else:
                self.session.auth = HTTPBasicAuth(*args)

        try:
            r = self.session.get(url, **kwargs)
        #except requests.exceptions.ConnectionError as e:
        except requests.exceptions.RequestException as e:
            r = None
            self.session = None
            log(e)

        return r
        #return requests.get(url, auth=HTTPDigestAuth(*args), **kwargs)


    def start(self):
        Thread(target=self._start).start()


    def _start(self):
        global posIndex

        if self.fixPosition:
            position = self.position
        else:
            position = posIndex

        if self.control:
            self.removeControl(self.control)

        x, y, w, h = self.coordinates(position)
        self.control = xbmcgui.ControlImage(x, y, w, h, __loading__, aspectRatio=self.aspectRatio)
        self.addControl(self.control)

        posIndex = (posIndex + 1) % MAXCAMS

        self.tmpdir = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(16)])
        self.tmpdir = os.path.join(__profile__, self.tmpdir)
        if not xbmcvfs.exists(self.tmpdir):
            xbmcvfs.mkdir(self.tmpdir)

        self.show()
        self.isRunning = True

        self.update()

        self.isRunning = False
        self.close()

        if posIndex:
            posIndex -= 1

        for file in xbmcvfs.listdir(self.tmpdir)[1]:
            xbmcvfs.delete(os.path.join(self.tmpdir, file))
        xbmcvfs.rmdir(self.tmpdir)

        self.session = None


    def update(self):
        index = 1
        old_snapshot = None
        startTime = time.time()

        while(not self.autoClose or (time.time() - startTime) * 1000 <= self.duration):
            if not self.isRunning:
                 break

            if index > 1:
                old_snapshot = snapshot

            snapshot = os.path.join(self.tmpdir, 'snapshot_{:06d}.jpg'.format(index))
            index += 1

            try:
                r = self.auth_get(self.cam['url'], self.cam['username'], self.cam['password'], verify=False, stream=True)
                if r.status_code == 200:
                    image = r.content

                    out = xbmcvfs.File(snapshot, 'wb')
                    out.write(bytearray(image))
                    out.close()
                else:
                    log('update(): Failed retrieving data from camera')
                    try:
                        r.raise_for_status()
                    except requests.exceptions.HTTPError as e:
                        log('update(): HTTP error {}'.format(str(e)))
                    snapshot = None

            except Exception as e:
                log('update(): Exception {}'.format(str(e)))
                snapshot = None
                #break

            if snapshot and xbmcvfs.exists(snapshot):
                self.control.setImage(snapshot, False)

            if old_snapshot and xbmcvfs.exists(old_snapshot):
                xbmcvfs.delete(old_snapshot)

            xbmc.sleep(self.interval)


    def onAction(self, action):
        if action in (ACTION_PREVIOUS_MENU, ACTION_STOP, ACTION_BACKSPACE, ACTION_NAV_BACK):
            self.stop()


    def stop(self):
        self.isRunning = False


class CamEventMgr():
    SNAPSHOT_URL = 'http://{}:{}/cgi-bin/snapshot.cgi?1'

    def __init__(self, master, index, camera):
        self.Master = master
        self.Index = index
        self.Camera = camera
        self.CurlObj = None
        self.Connected = None
        self.Reconnect = None
        self.Lifeview  = None
        self.RPCcmd = {
            'jsonrpc': '2.0',
            'method': 'Addons.ExecuteAddon',
            'params': {
                'addonid': 'script.securitycam',
                'params': {
                    'wait': 'false',
                    'streamid': '1',
                    'url': self.SNAPSHOT_URL.format(self.Camera['host'], self.Camera['port']),
                    'user': self.Camera['user'],
                    'password': self.Camera['pass']
                    }
                },
            'id': '1'
            }

        self.UseCamAddon = self.LoadSettings()


    def LoadSettings(self):
        return bool(__getSetting__('useAddon') == 'true')


    def OnConnect(self):
        log('Connected to event manager on {}'.format(self.Camera['host']))
        if self.UseCamAddon:
            self.Lifeview = None
        elif not self.Lifeview:
            self.Lifeview = CamLifeview(self.SNAPSHOT_URL.format(self.Camera['host'], self.Camera['port']),
                self.Camera['user'], self.Camera['pass'], self.Index)
        self.Connected = True


    def OnDisconnect(self, reason):
        log('Disconnected from event manager on {}. Resaon: {}'.format(self.Camera['host'], reason))
        if self.Lifeview:
            self.Lifeview.stop()
            self.Lifeview = None
        self.Connected = False


    def OnEvent(self, event, action):
        log('{} reported event {}: {}'.format(self.Camera['host'], event, action))
        if action == 'Start':
            if self.Lifeview: # and not self.UseCamAddon:
                self.Lifeview.start()
                log('{} Lifeview started'.format(self.Camera['host']))
            else:
                rpccmd = json.dumps(self.RPCcmd)
                log('Calling \'script.securitycam\' addon ...')
                log('JSON RPC command: {}'.format(rpccmd), loglevel=xbmc.LOGDEBUG)
                Ret = xbmc.executeJSONRPC(rpccmd)
                Ret = json.loads(Ret)
                if 'error' in Ret and 'message' in Ret['error']:
                    log('Call failed with error {}'.format(Ret['error']['message']))
                elif 'result' in Ret and Ret['result'] == 'OK':
                    log('Call successful', loglevel=xbmc.LOGDEBUG)
        elif action == 'Stop':
            if self.Lifeview:
                self.Lifeview.stop()


    def OnReceive(self, data):
        Data = data.decode('utf-8', errors='ignore')

        for Line in Data.split('\r\n'):
            #log('Debug: OnReceive(); Line={}'.format(Line))
            if Line == 'HTTP/1.1 200 OK':
                self.OnConnect()

            if not Line.startswith('Code='):
                continue

            log('{} sent raw event: {}'.format(self.Camera['host'], Line), loglevel=xbmc.LOGDEBUG)
            Event = dict()
            for KeyValue in Line.split(';'):
                Key, Value = KeyValue.split('=')
                Event[Key] = Value

            log('{} has parsed event {}'.format(self.Camera['host'], Event), loglevel=xbmc.LOGDEBUG)
            if Event['Code'] in [x.strip() for x in self.Camera['events'].split(',')]:
                self.OnEvent(Event['Code'], Event['action'])


class xbmcMonitor(xbmc.Monitor):
    def __init__ (self):
        xbmc.Monitor.__init__(self)
        self.settingsChanged = False


    def onSettingsChanged(self):
        self.settingsChanged = True


class DahuaCamMonitor():
    EVENTMGR_URL = 'http://{user}:{pass}@{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=[{events}]'

    def __init__(self):
        self.EventMgrs = []
        self.CurlMultiObj = pycurl.CurlMulti()
        self.NumCurlObjs = 0

        self.Cameras = self.LoadCams()

        for Index, Camera in enumerate(self.Cameras):
            EventMgr = CamEventMgr(self, Index, Camera)
            self.EventMgrs.append(EventMgr)

            url = self.EVENTMGR_URL.format(**Camera)

            CurlObj = pycurl.Curl()
            EventMgr.CurlObj = CurlObj

            CurlObj.setopt(pycurl.URL, url)
            CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
            CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
            CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
            CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
            CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
            CurlObj.setopt(pycurl.WRITEFUNCTION, EventMgr.OnReceive)

            self.CurlMultiObj.add_handle(CurlObj)
            self.NumCurlObjs += 1


    def LoadCams(self):
        Cameras = []

        for i in range(1,5):
            if __getSetting__('active' + str(i)) == 'true':
                cam = {
                    'host': __getSetting__('hostname' + str(i)),
                    'port': int(float(__getSetting__('port' + str(i)))),
                    'user': __getSetting__('username' + str(i)),
                    'pass': __getSetting__('password' + str(i)),
                    'events': 'VideoMotion' # 'VideoMotion, AlarmLocal'
                    }
                Cameras.append(cam)

        return Cameras


    def Run(self, timeout = 0.1):
        Reload = False
        NumHandles = self.NumCurlObjs

        if not NumHandles:
            return False

        #Monitor = xbmc.Monitor()
        Monitor = xbmcMonitor()

        while not Monitor.abortRequested() and not Reload: # and NumHandles:
            Ret = self.CurlMultiObj.select(timeout)
            if Ret == -1:
                continue

            while True:
                Ret, NumHandles = self.CurlMultiObj.perform()

                if NumHandles != self.NumCurlObjs:
                    _, Success, Error = self.CurlMultiObj.info_read()

                    for CurlObj in Success:
                        EventMgr = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.EventMgrs)))
                        if EventMgr.Reconnect:
                            continue

                        EventMgr.OnDisconnect('Success')
                        EventMgr.Reconnect = time.time() + 5

                    for CurlObj, ErrorNo, ErrorStr in Error:
                        EventMgr = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.EventMgrs)))
                        if EventMgr.Reconnect:
                            continue

                        EventMgr.OnDisconnect('{} ({})'.format(ErrorStr, ErrorNo))
                        EventMgr.Reconnect = time.time() + 5

                    for EventMgr in self.EventMgrs:
                        if EventMgr.Reconnect and EventMgr.Reconnect < time.time():
                            self.CurlMultiObj.remove_handle(EventMgr.CurlObj)
                            self.CurlMultiObj.add_handle(EventMgr.CurlObj)
                            EventMgr.Reconnect = None

                if Monitor.waitForAbort(1):
                    for EventMgr in self.EventMgrs:
                        EventMgr.OnDisconnect('Exit')
                    break

                if Monitor.settingsChanged:
                    for EventMgr in self.EventMgrs:
                        EventMgr.OnDisconnect('Settings changed')
                        del EventMgr
                        Reload = True
                    break

                if Ret != pycurl.E_CALL_MULTI_PERFORM:
                    break

        del Monitor

        return Reload


if __name__ == '__main__':
    log('Addon started')

    #if not xbmcvfs.exists(__settings__):
    #    xbmc.executebuiltin('Addon.OpenSettings(' + __addon_id__ + ')')
    Reload = True

    while Reload:
        log('Connecting ...')

        CamMonitor = DahuaCamMonitor()
        Reload = CamMonitor.Run()

        log('Disconnected with Reload Status: {}'.format(Reload))

        del CamMonitor
