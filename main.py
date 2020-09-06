#!/usr/local/bin/python3

from time import sleep
from signal import signal, SIGINT
from tkinter.filedialog import askdirectory
from tkinter import Tk
from downloader import Downloader
from threading import Lock, Thread

import sys
import logging

exit_signal = False
exit_lock = Lock()


def main():
    refresh_rate_min = 60

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

    downloader = Downloader("twilio.toml", output_path)

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
        downloader.download()
        logging.info(f"Sleeping for {refresh_rate_min} minutes.")
        sleep(refresh_rate_min * 60)


if __name__ == '__main__':
    main()
