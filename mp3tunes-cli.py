#!/usr/bin/env python
# MP3Tunes Python library and player (play tracks randomly)
# devloop - 09 / 2010
# http://my.opera.com/devloop/blog/2010/09/25/une-librairie-et-un-lecteur-en-python-pour-mp3tunes
import httplib
import json
import sys
import termios
import urllib
import random
import os

import shelve
import getpass

import gobject
gobject.threads_init()

class pytunes:
    
    partner_token = "3139047358"
    cnx = None
    connected = False
    session_id = None

    def __init__(self):
        pass
    
    def __del__(self):
        if self.connected == True:
            self.cnx.close()
        
    def login(self, login, password):
        # Login on locker acount
        conn = httplib.HTTPSConnection("shop.mp3tunes.com")
        p = "/api/v1/login?output=json&username=%s&password=%s&partner_token=%s" \
            % (login, password, self.partner_token)
        conn.request("GET", p)
        response = conn.getresponse()
        
        if response.status != 200:
            print "HTTP Error:", response.message
            return False
            
        data = response.read()
        tab = json.loads(data)
        if tab['status'] == 0:
            print "Login Error:", tab['errorMessage']
            return False
            
        conn.close()
        sid = tab["session_id"]
        self.session_id = sid
        return sid
        
    def _request(self, type, dargs={}):
        if self.session_id == None:
            print "You must login first !"
            sys.exit()

        if not self.connected:
            self.cnx = httplib.HTTPConnection("ws.mp3tunes.com")
            self.connected = True

        page = "/api/v1/lockerData?output=json&sid=%s&partner_token=%s&type=%s" \
            % (self.session_id, self.partner_token, type)
        if dargs != {}:
            page += "&" + urllib.urlencode(dargs)
        self.cnx.request("GET", page)
        response = self.cnx.getresponse()
        if response.status != 200:
            print "HTTP Error:", response.reason
            return None
        data = response.read()
        tab = json.loads(data)
        return tab
        
    def getArtists(self, count = -1, set = -1, token = ""):
        # Get an artist list.
        type = "artist"
        d = {}
        if count != -1:
            d['count'] = count
        if set != -1:
            d['set'] = set
        if token != "":
            d['token'] = token
        return self._request(type, d)['artistList']

    def getAlbums(self, count = -1, set = -1, token = "", artist_id = -1):
        # Get an album list
        type = "album"
        d = {}
        if count != -1:
            d['count'] = count
        if set != -1:
            d['set'] = set
        if token != "":
            d['token'] = token
        if artist_id != -1:
            d['artist_id'] = artist_id
        return self._request(type, d)['albumList']

    def getTracks(self, count = -1, set = -1, token = "", album_id = -1, playlist_id = -1):
        # Get some tracks
        type = "track"
        d = {}
        if count != -1:
            d['count'] = count
        if set != -1:
            d['set'] = set
        if token != "":
            d['token'] = token
        if album_id != -1:
            d['album_id'] = album_id
        if playlist_id != -1:
            d['playlist_id'] = playlist_id
        return self._request(type, d)['trackList']

    def lastUpdate(self, type="locker"):
        # Get last activity on the account
        # Valid types are "playlist", "locker", and "preferences".
        if self.session_id == None:
            print "You must login first !"
            sys.exit()

        if not self.connected:
            self.cnx = httplib.HTTPConnection("ws.mp3tunes.com")
            self.connected = True

        page = "/api/v1/lastUpdate?output=json&sid=%s&partner_token=%s&type=%s" \
            % (self.session_id, self.partner_token, type)
        self.cnx.request("GET", page)
        response = self.cnx.getresponse()
        if response.status != 200:
            print "HTTP Error:", response.reason
            return None
        data = response.read()
        tab = json.loads(data)
        return tab

    def accountData(self):
        # Get information on your account
        if self.session_id == None:
            print "You must login first !"
            sys.exit()

        if not self.connected:
            self.cnx = httplib.HTTPConnection("ws.mp3tunes.com")
            self.connected = True

        page = "/api/v1/accountData?output=json&sid=%s&partner_token=%s" \
            % (self.session_id, self.partner_token)
        self.cnx.request("GET", page)
        response = self.cnx.getresponse()
        if response.status != 200:
            print "HTTP Error:", response.reason
            return None
        data = response.read()
        tab = json.loads(data)
        return tab
    
    def lockerSearch(self, types, s, count = -1, set = -1, result_data_level = -1):
        # Search in the locker. 'Types' can be "artist", "album", "track" or a list with these values
        if self.session_id == None:
            print "You must login first !"
            sys.exit()

        if not self.connected:
            self.cnx = httplib.HTTPConnection("ws.mp3tunes.com")
            self.connected = True
            
        d = {}
        if count != -1:
            d['count'] = count
        if set != -1:
            d['set'] = set
        if result_data_level in ["min", "max"]:
            d['result_data_level'] = result_data_level
        
        if isinstance(types, str):
            if not types in ["artist", "album", "track"]:
                print "Invalid type:", types
                return {}
            
        if isinstance(types, list):
            for x in types:
                if x not in ["artist", "album", "track"]:
                    print "Invalid type:", x
                    return {}
            types = ",".join(types)
        
        page = "/api/v1/lockerSearch?output=json&sid=%s&partner_token=%s" \
            % (self.session_id, self.partner_token)
        page += "&type=%s&s=%s" % (types, s)
            
        if d != {}:
            page += "&" + urllib.urlencode(d)

        self.cnx.request("GET", page)
        response = self.cnx.getresponse()
        if response.status != 200:
            print "HTTP Error:", response.reason
            return None
        data = response.read()
        tab = json.loads(data)
        return tab

class PlayerTUI():
    def __init__(self, tracklist):
        # tracklist must be the list of tracks as returned by pytunes.getTracks()

        self.player = gst.element_factory_make("playbin2", "player")
        self.l = len(tracklist)
        self.tracklist = tracklist
        self.pause = False

        bus = self.player.get_bus()
        bus.enable_sync_message_emission()
        bus.add_signal_watch()
        # Detect when a song finish playing
        bus.connect('message::eos', self.on_eos)

        # The MainLoop
        self.mainloop = gobject.MainLoop()
        # Watch for console input
        gobject.io_add_watch(sys.stdin, gobject.IO_IN, self.on_stdin)

        print "Press h to get help"
        self.next()
        try:
            self.mainloop.run()
        except KeyboardInterrupt:
            self.quit()

    def help(self):
        # print available commands
        print "Commands:"
        print "  q: quit"
        print "  p: pause"
        print "  n: next"
        print "  +: volume up"
        print "  -: volume down"
        print "  m: toggle mute"
        print "  h: print usage"

    def on_stdin(self, fd, condition):
        c = os.read(fd.fileno(), 1)

        if c == 'q':
            self.quit()
        elif c == 'p':
            self.toggle_pause()
        elif c == 'n':
            self.next()
        elif c == '+':
            self.volume(0.05)
        elif c == '-':
            self.volume(-0.05)
        elif c == 'm':
            self.toggle_mute()
        elif c == 'h':
            self.help()

        return True

    def on_eos(self, bus, message):
        self.next()

    def quit(self):
        self.mainloop.quit()

    def toggle_mute(self):
        state = self.player.get_property('mute')
        if state == False:
          print "Sound: off"
        else:
          print "Sound: on"
        self.player.set_property('mute', not state)

    def volume(self, i):
        current = self.player.get_property('volume')
        if (i < 0 and current >= 0.05) or (i > 0 and current <= 0.95):
          current += i
          print "Volume: %s%%" % int(current * 100)
          self.player.set_property('volume', current)

    def toggle_pause(self):
        self.pause = not self.pause
        if self.pause == True:
          print "Pause: on"
          self.player.set_state(gst.STATE_PAUSED)
        else:
          print "Pause: off"
          self.player.set_state(gst.STATE_PLAYING)

    def next(self):
        self.player.set_state(gst.STATE_NULL)
        x = self.tracklist[random.randint(0,self.l - 1)]
        print "%s by %s (%s)" % (x['trackTitle'], x['artistName'], x['albumTitle'])
        #set the uri
        self.player.set_property('uri', x['playURL'])

        #start playing
        self.player.set_state(gst.STATE_PLAYING)
        self.pause = False

if __name__ == '__main__':
  print "* MP3Tunes random CLI Player - devloop *"
  conf = os.getenv('USERPROFILE') or os.getenv('HOME')
  conf += os.path.sep + ".pytunes"

  # username will be saved to .pytunes file
  # keeping password is optionnal
  user = shelve.open(conf, 'c')
  if user.has_key("login"):
    login = user["login"]
    print "Username:", login
  else:
    login = raw_input("Username: ")
    user["login"] = login
  if user.has_key("password"):
    password = user["password"]
  else:
    password = getpass.getpass(prompt="Password: ")
    if not user.has_key("remember"):
      while True:
        confirm = raw_input("Save the password in the config file ? (Y/N): ").upper()
        if confirm == "Y":
          user["password"] = password
          user["remember"] = True
          break
        elif confirm == "N":
          user["remember"] = False
          break
  user.close()

  tunes = pytunes()
  if not tunes.login(login, password):
      sys.exit()

  # Here's a small example using the library
  #
  # 1. Get every artists whose name starts with a 'S'
  #   tab =  tunes.getArtists(token="S")
  # 2. Filter to search for Serge Gainsbourg (of course we could have used togen="Serge Gainsbourg")
  #   sg = [x for x in tab if x["artistName"] == u"Serge Gainsbourg"][0]
  # 3. Get all Serge Gainsbourg's albums with its artistId
  #   tab = tunes.getAlbums(artist_id = sg['artistId'])
  # 4. Search for the B.B. Initials Album
  #   bb = [x for x in tab if x["albumTitle"].find(u"B.B.") != -1][0]
  # 5. Get every tracks from this album
  #   tab = tunes.getTracks(album_id = bb["albumId"])
  # 6. Find the "Bloody Jack" track (Gainsbourg / B.B. Initials)
  #   bj = [x for x in tab if x["trackTitle"] == u"Bloody Jack"][0]
  # 7. Display the stream url
  #   print bj["playURL"]

  print "Loading tracks info..."
  tracks = tunes.getTracks()
  l = len(tracks)
  print "Found", l, "tracks"

  import pygst
  pygst.require("0.10")
  import gst

  # configuring the terminal : canonical and no-echo modes
  fd = sys.stdin.fileno()
  new = termios.tcgetattr(fd)
  old = termios.tcgetattr(fd)
  new[3] &= ~termios.ICANON
  new[3] &= ~termios.ECHO
  termios.tcsetattr(fd, termios.TCSANOW, new)

  # Launch the CLI player
  tui = PlayerTUI(tracks)

  # restoring terminal configuration
  termios.tcsetattr(fd, termios.TCSAFLUSH, old)
