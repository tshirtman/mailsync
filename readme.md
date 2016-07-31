mailsync, an imap sync wrapper with idle support
================================================

The aim of this project is simply to have a slightly better way to get your
mails locally than polling. And to call any number of post-sync commands.

The idea is to still use a normal client like mbsync, but to also automatically
connect to your mailboxes, and to wait for events on them, before launching
a new sync, specifically on the affected mailbox, this should be both faster
and more efficient.

For ease of visualisation, while keeping the normal cli interface of mbsync (or
your favorite imap client), tmux is used to display the sync information of
each connection.

A configuration file is required, which is based on yaml. Please see
mailsync.conf.example

installation
------------

install with pip or setup.py, because of the usage of 'click' to parse parameters, running it directly without installation won't work, but you can install it in your userspace with --user, or in a virtualenv.

    # after clonning
    pip install --user .

    # or directly from pypi
    pip install --user mailsync
