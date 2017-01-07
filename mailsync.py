#!/usr/bin/env python
# coding: utf-8
# imap-idle for mbsync (or other imap sync)
# copyright (c) 2016, Gabriel Pettier
# usage:
# - edit the MBSYNC, GPG_COMMAND, POST_SYNC_COMMANDS and conf variables
# to suit your configuration
# - run imap_idle.py
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
import click
import libtmux


# these values are overridden by the cli function (entry point)
ACCOUNTS = {}
MBSYNC = ''
POST_SYNC_COMMANDS = []
FULLSYNC_INTERVAL = 0


def icheck_output(*args, **kwargs):
    print("calling, {}, {}".format(' '.join(map(str, args)), kwargs))
    process = Popen(*args, **kwargs)
    process.wait()


def _idle_client(account, box):
    c = ACCOUNTS[account]
    if 'pass_cmd' in c:
        c['pass'] = check_output([c['pass_cmd']], shell=True).strip()
    client = IMAPClient(
        c['host'], use_uid=True, ssl=c['ssl'])
    client.login(c['user'], c['pass'])
    try:
        client.select_folder(box)
    except:
        print(Style.BRIGHT + Fore.RED +
              "unable to select folder {}".format(box) +
              Fore.RESET + Style.RESET_ALL)
        return
    client.idle()

    print("connected, {}: {}".format(account, box))
    while True:
        for m in client.idle_check(timeout=30):
            if m != (b'OK', b'Still here'):
                print(Style.BRIGHT + Fore.GREEN,
                      "event: {}, {}, {}".format(account, box, m) +
                      Fore.RESET + Style.RESET_ALL)
                sync(c['local'], box)
        sleep(1)


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
    global ACCOUNTS, MBSYNC, POST_SYNC_COMMANDS, FULLSYNC_INTERVAL
    cfg = load(conf)

    MBSYNC = cfg['sync_command']
    POST_SYNC_COMMANDS = cfg['post_sync']
    ACCOUNTS = cfg['accounts']
    FULLSYNC_INTERVAL = cfg.get('fullsync_interval')


def sync(host=None, box=None):
    if not host:
        print("initial sync" + Fore.LIGHTWHITE_EX + Style.DIM)
        icheck_output(split(MBSYNC) + ['-a'])
    else:
        print(Style.BRIGHT + Fore.CYAN +
              "syncing: {}:{}".format(host, box) +
              Fore.LIGHTWHITE_EX + Style.RESET_ALL + Style.DIM)
        icheck_output(split(MBSYNC) + ['{}:{}'.format(host, box)])

        print(Style.RESET_ALL + Style.BRIGHT + Fore.CYAN +
              "done syncing {}:{}".format(host, box) +
              Fore.RESET + Style.RESET_ALL)

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
    while True:
        try:
            print(Style.BRIGHT + Fore.GREEN +
                  "connecting to {}:{}".format(account, box) +
                  Style.RESET_ALL + Fore.RESET)
            _idle_client(account, box)
        except Exception as e:
            print(Style.BRIGHT + Fore.RED +
                  "error {} in {}:{} connection, restarting"
                  .format(e, account, box) +
                  Fore.RESET + Style.RESET_ALL)


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


@cli.command('idle')
def idle():
    """Sync all the mailboxes, then spawn clients for monitored mailboxes
    """
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


@cli.command('fullsync')
@click.argument('account', required=False)
@click.argument('box', required=False)
@click.option('-t', default=0)
def full_sync(account=None, box=None, t=0):
    if t:
        while True:
            timeout = t
            while timeout:
                print(timeout, end=' \r')
                sleep(1)
                timeout -= 1
            sync(host=account, box=box)
    else:
        sync(host=account, box=box)


def _main(session):
    window = session.list_windows()[0]
    i = 0
    for account, c in ACCOUNTS.items():
        for box in c['boxes']:
            spawn_client(window, account, box, split=bool(i))
            i += 1
    if FULLSYNC_INTERVAL:
        spawn_recurrent_fullsync(window)
