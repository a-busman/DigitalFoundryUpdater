#!/usr/local/bin/python3

from time import sleep
from signal import signal, SIGINT
from tkinter.filedialog import askdirectory
from tkinter import Tk
from downloader import Downloader
from threading import Lock, Thread

import sys
import toml
import logging

exit_signal = False
exit_lock = Lock()


def _parse_conf(conf_file: str):
    """Parses the incoming toml config file"""
    try:
        conf = toml.load(conf_file)
    except Exception as e:
        logging.warning(f"Failed to decode TOML file: {e}. Using chrome as browser.")
        return "chrome", "", "", "", ""
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


def main():
    root = Tk()
    root.withdraw()
    # Check for output directory
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S')

    output_path = askdirectory()
    root.update()
    if output_path == '':
        logging.warning("No output path selected. Using current directory")
        output_path = '.'

    browser, refresh_rate_min, sid, token, to, from_ = _parse_conf("conf.toml")

    downloader = Downloader(browser, sid, token, to, from_, output_path)

    def handle_sigint(_sig, _frame):
        print()
        global exit_signal
        global exit_lock

        if downloader is None:
            logging.info('Shutting down...')
            logging.shutdown()
            sys.exit(0)

        exit_lock.acquire()
        t = Thread(target=downloader.download)
        t.daemon = True

        if exit_signal:
            exit_lock.release()
            logging.info('Shutting down...')
            logging.shutdown()
            sys.exit(0)
        else:
            exit_signal = True
            exit_lock.release()
            logging.info("Checking now...")
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
            logging.error(f"Exception: {e}")
        logging.info(f"Sleeping for {refresh_rate_min} minutes.")
        sleep(refresh_rate_min * 60)


if __name__ == '__main__':
    main()
