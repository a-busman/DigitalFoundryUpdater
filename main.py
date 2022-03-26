#!/usr/local/bin/python3

from time import sleep
from signal import signal, SIGINT
from tkinter.filedialog import askdirectory
from tkinter import Tk
from downloader import Downloader
from threading import Lock, Thread
from notify import Notifier
from sys import exit
from toml import load as load_toml
from argparse import ArgumentParser

import logging as log

exit_signal = False
exit_lock = Lock()


def _parse_conf(conf_file: str):
    """Parses the incoming toml config file"""
    try:
        conf = load_toml(conf_file)
    except Exception as e:
        log.warning(f'Failed to decode TOML file: {e}. Using chrome as browser.')
        return 'chrome', 60, '', '', '', ''
    else:
        sid = ''
        token = ''
        to = ''
        from_ = ''

        if 'twilio' in conf:
            if 'auth' in conf['twilio']:
                sid = conf['twilio']['auth']['sid']
                token = conf['twilio']['auth']['token']
            if 'phone' in conf['twilio']:
                to = conf['twilio']['phone']['to']
                from_ = conf['twilio']['phone']['from']

        browser = conf['conf']['browser']
        if 'refresh_mins' in conf:
            refresh_mins = conf['conf']['refresh_mins']
        else:
            refresh_mins = 60

        return browser, refresh_mins, sid, token, to, from_


def setup_parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument('-c', '--collection', help='DF collection title. For example, the last part of the path from ' +
                        'https://www.digitialfoundry.net/browse/df-retro, -c df-retro', type=str)
    parser.add_argument('-o', '--output_dir', help='Directory to download videos to')
    return parser


def main():
    parser = setup_parser()
    args = parser.parse_args()
    if args.output_dir is not None:
        output_path = args.output_dir
    else:
        root = Tk()
        root.withdraw()
        log.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=log.INFO, datefmt='%Y-%m-%d %H:%M:%S')

        output_path = askdirectory()
        root.update()
        if output_path == '':
            log.warning('No output path selected. Using current directory')
            output_path = '.'

    browser, refresh_rate_min, sid, token, to, from_ = _parse_conf('conf.toml')
    try:
        notifier = Notifier(sid, token, to, from_)
    except Exception as e:
        log.warning(f'Notifier failed to start: {e}')
        notifier = None

    downloader = Downloader(browser, notifier, output_path, args.collection)

    def handle_sigint(_sig, _frame):
        print()
        global exit_signal
        global exit_lock

        if downloader is None:
            log.info('Shutting down...')
            log.shutdown()
            exit(0)

        exit_lock.acquire()
        t = Thread(target=downloader.download)
        t.daemon = True

        if exit_signal:
            exit_lock.release()
            log.info('Shutting down...')
            log.shutdown()
            exit(0)
        else:
            exit_signal = True
            exit_lock.release()
            log.info('Checking now...')
            downloader.load_cookie_jar()
            t.start()

        sleep(0.75)
        exit_lock.acquire()
        exit_signal = False
        exit_lock.release()

    signal(SIGINT, handle_sigint)
    while True:
        try:
            downloader.download()
        except Exception as e:
            log.error(e)
        log.info(f'Sleeping for {refresh_rate_min} minutes.')
        sleep(refresh_rate_min * 60)


if __name__ == '__main__':
    main()
