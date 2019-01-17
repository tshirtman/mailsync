#!/usr/bin/env python3
# coding: utf-8

# imap-idle for mbsync (or other imap sync)
# copyright (c) 2016-2017, Gabriel Pettier
# usage:
# - edit the MBSYNC, GPG_COMMAND, POST_SYNC_COMMANDS and conf variables
# to suit your configuration
# - run mailsync.py
# BSD licensed
# Please see http://en.wikipedia.org/wiki/BSD_licenses

from appdirs import user_config_dir
from colorama import Fore, Style
from imapclient import IMAPClient
from os.path import join, expanduser
from shlex import split
from subprocess import Popen, check_output
from sys import argv
from time import asctime, sleep
from yaml import load
from signal import signal, SIGUSR2
from functools import partial
from threading import Thread
try:
    from NetworkManager import NetworkManager
except:
    NetworkManager = None

import click
import libtmux


# these values are overridden by the cli function (entry point)
ACCOUNTS = {}
MBSYNC = ''
POST_SYNC_COMMANDS = []
FULLSYNC_INTERVAL = 0
SYNC_TIMEOUT = None


def icheck_output(*args, **kwargs):
    print("calling, {}, {}".format(' '.join(map(str, args)), kwargs))
    process = Popen(*args, **kwargs)
    return process.wait()


def _idle_client(account, box, state):
    wait_connect()
    c = ACCOUNTS[account]
    renew = 600

    if 'pass_cmd' in c:
        c['pass'] = check_output([c['pass_cmd']], shell=True).strip()

    client = None
    try:
        client = IMAPClient(c['host'], use_uid=True, ssl=c['ssl'])
        client.login(c['user'], c['pass'])
        try:
            client.select_folder(box)
        except:
            print(Style.BRIGHT + Fore.RED +
                  "unable to select folder {}".format(box) +
                  Fore.RESET + Style.RESET_ALL)
            client.logout()
            return

        client.idle()

        print("connected, {}: {}".format(account, box))
        while not state['got_signal'] and renew > 0:
            for m in client.idle_check(timeout=30):
                # XXX check for "BYE" events and restart the connection
                if m != (b'OK', b'Still here'):
                    print(Style.BRIGHT + Fore.GREEN,
                          "event: {}, {}, {}".format(account, box, m) +
                          Fore.RESET + Style.RESET_ALL)
                    sync(c['local'], box)
            sleep(1)
            renew -= 1

    finally:
        if client:
            client.idle_done()
            client.logout()


def spawn_client(window, account, box, split=True):
    if split:
        panel = window.split_window()
    else:
        panel = window.list_panes()[0]
    window.select_layout('even-vertical')
    panel.clear()
    panel.send_keys(u'%s client "%s" "%s"' % (argv[0], account, box))


def spawn_recurrent_fullsync(window):
    panel = window.split_window()
    window.select_layout('even-vertical')
    panel.clear()
    panel.send_keys(u'%s fullsync -t %s' % (argv[0], FULLSYNC_INTERVAL))


@click.group()
@click.option('--conf',
              default=join(user_config_dir('mailsync'), 'mailsync.conf'),
              type=click.File('r'), required=False)
def cli(conf):
    global ACCOUNTS, MBSYNC, POST_SYNC_COMMANDS, FULLSYNC_INTERVAL, \
        SYNC_TIMEOUT
    cfg = load(conf)

    MBSYNC = cfg['sync_command']
    POST_SYNC_COMMANDS = cfg['post_sync']
    ACCOUNTS = cfg['accounts']
    FULLSYNC_INTERVAL = cfg.get('fullsync_interval')
    SYNC_TIMEOUT = cfg.get('sync_timeout')


def sync(host=None, box=None):
    ret = None
    timeout = SYNC_TIMEOUT

    if timeout:
        CMD = 'timeout {} {}'.format(timeout, MBSYNC)
    else:
        CMD = MBSYNC

    while not timeout or ret in (None, 124):
        if not host:
            print("initial sync" + Fore.LIGHTWHITE_EX + Style.DIM)
            ret = icheck_output(split(CMD) + ['-a'])
        else:
            print(Style.BRIGHT + Fore.CYAN +
                  "syncing: {}:{}".format(host, box) +
                  Fore.LIGHTWHITE_EX + Style.RESET_ALL + Style.DIM)
            ret = icheck_output(split(CMD) + ['{}:{}'.format(host, box)])

            if ret != 124:
                print(Style.RESET_ALL + Style.BRIGHT + Fore.CYAN +
                      "done syncing {}:{}".format(host, box) +
                      Fore.RESET + Style.RESET_ALL)

        if ret == 124:
            print(Fore.RED + Style.BRIGHT +
                  "sync timed out after %ss trying again!" % (timeout) +
                  Style.RESET_ALL + Fore.RESET)

    for c in POST_SYNC_COMMANDS:
        print(Fore.YELLOW + Style.BRIGHT)
        icheck_output(
            [
                expanduser(x) for x in split(
                    c.format(host=host or '', box=box or '')
                )
            ]
        )
        print(Style.RESET_ALL + Fore.RESET)

    print(Fore.BLUE + Style.BRIGHT +
          "last sync of %s:%s at %s" % (host, box, asctime()) +
          Style.RESET_ALL + Fore.RESET)


@cli.command('client')
@click.argument('account')
@click.argument('box')
def idle_client(account, box):
    """connect to account and wait for events on box to sync
    """
    state = {'got_signal': False}
    signal(SIGUSR2, partial(handle_signal, state))
    retry_delay = 5

    while True:
        try:
            print(Style.BRIGHT + Fore.GREEN +
                  "connecting to {}:{}".format(account, box) +
                  Style.RESET_ALL + Fore.RESET)
            _idle_client(account, box, state)
        except Exception as e:
            print(Style.BRIGHT + Fore.RED +
                  "error {} in {}:{} connection, retrying in {} seconds"
                  .format(e, account, box, retry_delay) +
                  Fore.RESET + Style.RESET_ALL)
            for i in range(retry_delay):
                sleep(1)
                print('.', end='')

        if state['got_signal']:
            state['got_signal'] = False
            print(Style.BRIGHT + Fore.YELLOW +
                  "forced reconnection, restarting" +
                  Fore.RESET + Style.RESET_ALL)


def handle_signal(state, sig, frame):
    state['got_signal'] = True


@cli.command('suspend')
def suspend():
    pass


@cli.command('resume')
def resume():
    session = get_session()
    stop_all(session)
    run(session)


def run(session):
    session.list_windows()[0].list_panes()[0].send_keys(
        'mailsync fullsync; mailsync idle')


@cli.command('list')
@click.argument('account')
def list_boxes(account):
    c = ACCOUNTS[account]
    if 'pass_cmd' in c:
        c['pass'] = check_output([c['pass_cmd']], shell=True).strip()
    client = IMAPClient(
        c['host'], use_uid=True, ssl=c['ssl'])
    try:
        client.login(c['user'], c['pass'])
        from pprint import pprint
        pprint(client.list_folders())
    finally:
        client.logout()


@cli.command('idle')
def idle():
    """Sync all the mailboxes, then spawn clients for monitored mailboxes
    """
    signal(SIGUSR2, partial(handle_signal, {}))
    connection_canary()
    session = get_session()
    _main(session)
    session.attach_session()


@cli.command('run')
def main():
    """start sync and attach to session
    """
    session = get_session()
    run(session)
    session.attach_session()


@cli.command('stop')
def stop():
    stop_all(get_session())


def get_session():
    server = libtmux.Server()
    try:
        session = server.find_where({'session_name': 'mailsync'})
    except:
        session = None

    if not session:
        session = server.new_session('mailsync')

    return session


def stop_all(session):
    for w in session.list_windows():
        for p in w.list_panes()[1:]:
            p.cmd('send-keys', '^C')

        sleep(1)
        for p in w.list_panes()[1:]:
            p.cmd('send-keys', '^D')

    w.list_panes()[0].cmd('send-keys', '^C')


def connected():
    return any(
        x.State == 2
        for x in NetworkManager.ActiveConnections
        if x.Devices[0].Driver != 'bridge'
    )


def wait_connect():
    if NetworkManager:
        if not connected():
            print("waiting for connection")
            while not connected():
                print(".", end='')
                sleep(1)


def connection_canary():
    t = Thread(target=connection_canary_thread)
    t.daemon = True
    t.start()


def connection_canary_thread():
    while True:
        sleep(10)
        if not connected():
            print("lost connection, restarting…")
            sleep(2)
            resume()
            break


@cli.command('fullsync')
@click.argument('account', required=False)
@click.argument('box', required=False)
@click.option('-t', default=0)
def full_sync(account=None, box=None, t=0):
    state = {'got_signal': False}

    signal(SIGUSR2, partial(handle_signal, state))

    wait_connect()

    if t:
        while True:
            timeout = t
            while timeout and not state['got_signal']:
                print(' %s ' % timeout, end='\r')
                sleep(1)
                timeout -= 1
            state['got_signal'] = False
            sync(host=account, box=box)
    else:
        sync(host=account, box=box)


@cli.command('debug')
@click.argument('account', required=False)
def debug(account):
    c = ACCOUNTS[account]
    if 'pass_cmd' in c:
        c['pass'] = check_output([c['pass_cmd']], shell=True).strip()
    client = IMAPClient(
        c['host'], use_uid=True, ssl=c['ssl'])
    try:
        client.login(c['user'], c['pass'])
        print(client.capabilities())
    finally:
        client.logout()


def _main(session):
    window = session.list_windows()[0]
    i = 0
    for account, c in ACCOUNTS.items():
        for box in c['boxes']:
            spawn_client(window, account, box, split=bool(i))
            i += 1
    if FULLSYNC_INTERVAL:
        spawn_recurrent_fullsync(window)
