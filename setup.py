from setuptools import setup


setup(
    name='mailsync',
    author='Gabriel Pettier',
    url='https://github.com/tshirtman/mailsync',
    license='BSD',
    version='1.0',
    description=(
        'a wrapper script for mbsync (or other imap sync clients) that '
        'also waits for IDLE events for new sync, instead of regular '
        'polling'
    ),
    py_modules=['mailsync'],
    install_requires=[
        'Click',
        'ImapClient',
        'libtmux',
        'colorama',
        'pyyaml',
        'appdirs',
    ],
    entry_points='''
        [console_scripts]
        mailsync=mailsync:cli
    '''
)
