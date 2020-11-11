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

__setting__      = __addon__.getSetting
__setSetting__   = __addon__.setSetting
__localize__     = __addon__.getLocalizedString

__loading__      = os.path.join(__addon_path__, 'loading.gif')
__settings__     = os.path.join(__profile__, 'settings.xml')

# Constants
ACTION_PREVIOUS_MENU = 10
ACTION_STOP = 13
ACTION_NAV_BACK = 92
ACTION_BACKSPACE = 110

CAMERAS = None
SETTINGS = None

def log(message,loglevel=xbmc.LOGNOTICE):
    xbmc.log(msg='[{}] {}'.format(__addon_id__, message), level=loglevel)

def loadSettings():
    global CAMERAS, SETTINGS

    try:
        CAMERAS = []
        for i in range(1,5):
            if __setting__('active' + str(i)) == 'true':
                cam = {
                    'host': __setting__('hostname' + str(i)),
                    'port': int(float(__setting__('port' + str(i)))),
                    'user': __setting__('username' + str(i)),
                    'pass': __setting__('password' + str(i)),
                    'events': 'VideoMotion' # 'VideoMotion, AlarmLocal'
                    }
                CAMERAS.append(cam)

        SETTINGS = {
            'width':       int(float(__setting__('width'))),
            'height':      int(float(__setting__('height'))),
            'interval':    int(float(__setting__('interval'))),
            'duration':    int(float(__setting__('duration')) * 1000),
            'alignment':   int(float(__setting__('alignment'))),
            'padding':     int(float(__setting__('padding'))),
            'aspectRatio': int(float(__setting__('aspectRatio'))),
            'autoClose':   bool(__setting__('autoClose') == 'true'),
            'useAddon':    bool(__setting__('useAddon') == 'true')
            }
        if xbmc.getCondVisibility('System.HasAddon(script.securitycam)') == 0:
            log('Security Cam Overlay Addon is not installed.')
            SETTINGS['useAddon'] = False
            __setSetting__('useAddon', 'false')
        log('Addon settings: {}'.format(SETTINGS), loglevel=xbmc.LOGDEBUG)
    except Exception as e:
        log('Loading addon settings failed with exception {}'.format(str(e)))
        raise SystemExit

    if not CAMERAS:
        log('No cameras configured. Abort')
        raise SystemExit

    log('Addon settings loaded')


class CamLifeview(xbmcgui.WindowDialog):
    def __init__(self, url, username, password, position):
        self.cam = {
            'url': url,
            'username': username,
            'password': password,
            }
        self.session = None

        x, y, w, h = self.coordinates(position)
        self.control = xbmcgui.ControlImage(x, y, w, h, __loading__, aspectRatio=SETTINGS['aspectRatio'])
        self.addControl(self.control)

    def coordinates(self, position):
        WIDTH  = 1280
        HEIGHT = 720

        w = SETTINGS['width']
        h = SETTINGS['height']
        p = SETTINGS['padding']

        alignment = SETTINGS['alignment']

        if alignment == 0: # vertical right, top to bottom
            x = WIDTH - (w + p)
            y = p + position * (h + p)
        if alignment == 1: # vertical left, top to bottom
            x = p
            y = p + position * (h + p)
        if alignment == 2: # horizontal top, left to right
            x = p + position * (w + p)
            y = p
        if alignment == 3: # horizontal bottom, left to right
            x = p + position * (w + p)
            y = HEIGHT - (h + p)
        if alignment == 4: # square right
            x = WIDTH - (2 - position%2) * (w + p)
            y = p + position/2 * (h + p)
        if alignment == 5: # square left
            x = p + position%2 * (w + p)
            y = p + position/2 * (h + p)
        if alignment == 6: # vertical right, bottom to top
            x = WIDTH - (w + p)
            y = HEIGHT - (position + 1) * (h + p)
        if alignment == 7: # vertical left, bottom to top
            x = p
            y = HEIGHT - (position + 1) * (h + p)
        if alignment == 8: # horizontal top, right to left
            x = WIDTH - (position + 1) * (w + p)
            y = p
        if alignment == 9: # horizontal bottom, right to left
            x = WIDTH - (position + 1) * (w + p)
            y = HEIGHT - (h + p)

        return x, y, w, h


    def auth_get(self, url, *args, **kwargs):
        if not self.session:
            self.session = requests.Session()
            # Dahua cams use Digest Authentication scheme
            self.session.auth = HTTPDigestAuth(*args)

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
        self.tmpdir = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(16)])
        self.tmpdir = os.path.join(__profile__, self.tmpdir)
        if not xbmcvfs.exists(self.tmpdir):
            xbmcvfs.mkdir(self.tmpdir)

        self.show()
        self.isRunning = True

        self.update()

        self.isRunning = False
        self.close()

        for file in xbmcvfs.listdir(self.tmpdir)[1]:
            xbmcvfs.delete(os.path.join(self.tmpdir, file))
        xbmcvfs.rmdir(self.tmpdir)

        self.session = None


    def update(self):
        index = 1
        startTime = time.time()

        while(not SETTINGS['autoClose'] or (time.time() - startTime) * 1000 <= SETTINGS['duration']):
            if not self.isRunning:
                 break

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

            xbmc.sleep(SETTINGS['interval'])


    def onAction(self, action):
        if action in (ACTION_PREVIOUS_MENU, ACTION_STOP, ACTION_BACKSPACE, ACTION_NAV_BACK):
            self.stop()


    def stop(self):
        self.isRunning = False


class DahuaCamera():
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


    def OnConnect(self):
        log('Connected to event manager on {}'.format(self.Camera['host']))
        if SETTINGS['useAddon']:
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
            if self.Lifeview:
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
                #log('{} Lifeview stopped'.format(self.Camera['host']))


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


class DahuaEventMgr():
    EVENTMGR_URL = 'http://{user}:{pass}@{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=[{events}]'

    def __init__(self):
        self.Cameras = []
        self.CurlMultiObj = pycurl.CurlMulti()
        self.NumCurlObjs = 0

        for Index, Camera in enumerate(CAMERAS):
            DahuaCam = DahuaCamera(self, Index, Camera)
            self.Cameras.append(DahuaCam)

            url = self.EVENTMGR_URL.format(**Camera)

            CurlObj = pycurl.Curl()
            DahuaCam.CurlObj = CurlObj

            CurlObj.setopt(pycurl.URL, url)
            CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
            CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
            CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
            CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
            CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
            CurlObj.setopt(pycurl.WRITEFUNCTION, DahuaCam.OnReceive)

            self.CurlMultiObj.add_handle(CurlObj)
            self.NumCurlObjs += 1


    def Run(self, timeout = 0.1):
        monitor = xbmc.Monitor()

        NumHandles = self.NumCurlObjs

        while not monitor.abortRequested() and NumHandles:
            Ret = self.CurlMultiObj.select(timeout)
            if Ret == -1:
                continue

            while True:
                Ret, NumHandles = self.CurlMultiObj.perform()

                if NumHandles != self.NumCurlObjs:
                    _, Success, Error = self.CurlMultiObj.info_read()

                    for CurlObj in Success:
                        Camera = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Cameras)))
                        if Camera.Reconnect:
                            continue

                        Camera.OnDisconnect('Success')
                        Camera.Reconnect = time.time() + 5

                    for CurlObj, ErrorNo, ErrorStr in Error:
                        Camera = next(iter(filter(lambda x: x.CurlObj == CurlObj, self.Cameras)))
                        if Camera.Reconnect:
                            continue

                        Camera.OnDisconnect('{} ({})'.format(ErrorStr, ErrorNo))
                        Camera.Reconnect = time.time() + 5

                    for Camera in self.Cameras:
                        if Camera.Reconnect and Camera.Reconnect < time.time():
                            self.CurlMultiObj.remove_handle(Camera.CurlObj)
                            self.CurlMultiObj.add_handle(Camera.CurlObj)
                            Camera.Reconnect = None

                if monitor.waitForAbort(1):
                    for Camera in self.Cameras:
                        Camera.OnDisconnect('Exit')
                    break

                if Ret != pycurl.E_CALL_MULTI_PERFORM:
                    break

        del monitor


if __name__ == '__main__':
    log('Addon started')

    #if not xbmcvfs.exists(__settings__):
    #    xbmc.executebuiltin('Addon.OpenSettings(' + __addon_id__ + ')')

    loadSettings()

    EventMgr = DahuaEventMgr()
    EventMgr.Run()
