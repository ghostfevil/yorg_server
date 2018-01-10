from panda3d.core import loadPrcFileData
loadPrcFileData('', 'window-type none')
loadPrcFileData('', 'audio-library-name null')
import sys
import argparse
import sqlite3
from os.path import exists
from os import mkdir
import logging
from logging.handlers import TimedRotatingFileHandler
import sleekxmpp
from sleekxmpp.jid import JID
import direct.directbase.DirectStart


if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    raw_input = input


class SupporterMgr(object):

    def __init__(self):
        self.conn = sqlite3.connect('supporters.db')
        self.cur = self.conn.cursor()

    def supporters(self):
        self.cur.execute('SELECT * from supporters')
        return [elm[0] for elm in self.cur.fetchall()]


class User(object):

    def __init__(self, name, is_supporter):
        self.name = name
        self.is_supporter = is_supporter
        self.last_seen = globalClock.get_frame_time()


class YorgServer(sleekxmpp.ClientXMPP):

    def __init__(self, jid, password):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)
        self.users = []
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.on_message)
        #self.add_event_handler("presence_available", self.on_presence_available)
        #self.add_event_handler("presence_unavailable", self.on_presence_unavailable)

    def is_supporter(self, name):
        return name in self.supp_mgr.supporters()

    def start(self, event):
        self.supp_mgr = SupporterMgr()
        fake_users_names = [
            'user1@domain1.tld',
            'user2@longdomainname1.tld',
            'user3@domain1.tld',
            'user4longname@domain1.tld',
            'user5@domain1.tld',
            'user6@domain2.tld',
            'user7@domain2.tld',
            'user8@domain2.tld',
            'user9@domain2.tld',
            'user10longname@longdomainname2.tld',
            'user11@domain2.tld',
            'user12@domain2.tld',
            'user13@domain2.tld',
            'user14@longdomainname2.tld',
            'user15@domain2.tld',
            'user16@domain3.tld',
            'user17@domain3.tld',
            'user18@domain3.tld']
        #fake_users_names = []  # uncomment this so don't use fake names
        self.fake_users = [
            User(usr_name, self.is_supporter(usr_name)) for usr_name in fake_users_names]
        self.send_presence()
        self.get_roster()

    def on_connected(self, msg):
        supp_pref = lambda name: '1' if self.is_supporter(name) else '0'
        usr_name = str(msg['from'])
        self.users += [User(usr_name, self.is_supporter(usr_name))]
        for user in self.users:
            if JID(str(user.name)).bare != JID(str(msg['from'])).bare:
                self.send_message(
                    mfrom='ya2_yorg@jabb3r.org',
                    mto=user.name,
                    mtype='ya2_yorg',
                    msubject='user_connected',
                    mbody=supp_pref(msg['from'].full) + msg['from'].full)

    def on_disconnected(self, msg):
        usr_name = str(msg['from'])
        for user in self.users[:]:
            if JID(str(user.name)).bare != JID(str(msg['from'])).bare:
                self.send_message(
                    mfrom='ya2_yorg@jabb3r.org',
                    mto=user.name,
                    mtype='ya2_yorg',
                    msubject='user_disconnected',
                    mbody=msg['from'].full)
            else:
                self.users.remove(user)

    def on_keep_alive(self, msg):
        for user in self.users:
            if str(user.name) == str(msg['from']):
                user.last_seen = globalClock.get_frame_time()

    def maintain(self, task):
        for user in self.users[:]:
            if globalClock.get_frame_time() - user.last_seen > 15:
                print 'removing user', user.name
                self.users.remove(user)
                self.on_disconnected({'from': JID(user.name)})
        return task.again

    def on_list_users(self, msg):
        supp_pref = lambda name: '1' if self.is_supporter(name) else '0'
        fake_names = [usr.name for usr in self.fake_users]
        supp_names = [supp_pref(name) + name for name in self.user_names() + fake_names]
        to_remove = []
        for user in self.user_names():
            if JID(user).bare == JID(msg['from']).bare: to_remove += [user]
        map(self.remove_user, to_remove)
        usr_name = str(msg['from'])
        self.users += [User(usr_name, self.is_supporter(usr_name))]
        self.send_message(
            mfrom='ya2_yorg@jabb3r.org',
            mto=msg['from'],
            mtype='ya2_yorg',
            msubject='list_users',
            mbody='\n'.join(supp_names))

    def on_message(self, msg):
        logging.info('MESSAGE: ' + str(msg))
        if msg['subject'] == 'list_users':
            self.on_list_users(msg)
        if msg['subject'] == 'connected':
            self.on_connected(msg)
        if msg['subject'] == 'disconnected':
            self.on_disconnected(msg)
        if msg['subject'] == 'keep_alive':
            self.on_keep_alive(msg)

    def remove_user(self, usr_name):
        for usr in self.users[:]:
            if usr.name == usr_name: self.users.remove(usr)

    def user_names(self):
        return [usr.name for usr in self.users]

if not exists('logs'): mkdir('logs')
logging.basicConfig(level=logging.DEBUG,
                    format='%(levelname)-8s %(message)s')

handler = TimedRotatingFileHandler('logs/yorg_server.log', when='midnight',
                                   interval=1)
handler.suffix = '%Y%m%d'
logging.getLogger().addHandler(handler)

parser = argparse.ArgumentParser()
parser.add_argument('user')
parser.add_argument('pwd')
args = parser.parse_args()

xmpp = YorgServer(args.user, args.pwd)
xmpp.register_plugin('xep_0030') # Service Discovery
xmpp.register_plugin('xep_0004') # Data Forms
xmpp.register_plugin('xep_0060') # PubSub
xmpp.register_plugin('xep_0199') # XMPP Ping

if xmpp.connect():
    xmpp.process(block=False)

taskMgr.doMethodLater(5.0, xmpp.maintain, 'maintain')
base.run()