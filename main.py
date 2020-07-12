#!/usr/local/bin/python3

from bs4 import BeautifulSoup
from browsercookie import chrome, safari, firefox
from time import sleep
from http.cookiejar import CookieJar, Cookie
from requests import get, Response
from signal import signal, SIGINT
from typing import BinaryIO, Tuple, List
from tkinter.filedialog import askdirectory
from tkinter import Tk

import time
import sys
import logging
import argparse

scheme = 'https://'
domain = 'www.digitalfoundry.net'
url = scheme + domain

other_downloads = 'See more download options'
hevc = ' Download HEVC'
download_now = 'Download now'
download_prefix = 'Download '
cache_file = 'cache'

refresh_rate_min = 60


def handle_sigint(sig, frame):
    print()
    logging.info('Shutting down...')
    logging.shutdown()
    sys.exit(0)


def process(browser: str, output_path: str):
    if browser == 'chrome':
        cj = chrome()
    elif browser == 'safari':
        cj = safari()
    elif browser == 'firefox':
        cj = firefox()
    else:
        raise Exception(f"Unsupported browser type: {browser}")

    if not has_valid_cookie(cj):
        sleep(refresh_rate_min * 60)
        return

    logging.info('Checking Digital Foundry Homepage...')
    r = get(url, cookies=cj)
    if not r.ok:
        logging.warning("Can't reach Digital Foundry Homepage.")
        return

    hevc_hrefs, other_hrefs = get_links(r, cache_file)
    total_downloads = len(hevc_hrefs) + len(other_hrefs)

    if total_downloads > 0:
        logging.info(f"Found {total_downloads} new video{'s' if total_downloads > 1 else ''}!")
    for i in range(0, len(hevc_hrefs)):
        process_hevc_download(hevc_hrefs[i], hevc_hrefs[i], cj, i + 1, total_downloads, output_path)
    for i in range(0, len(other_hrefs)):
        process_other_downloads(other_hrefs[i], cj, i + len(hevc_hrefs) + 1, total_downloads, output_path)
    logging.info("All videos downloaded.")
    return


def main():
    root = Tk()
    root.withdraw()
    # Check for output directory and browser type
    parser = argparse.ArgumentParser(description='Download new video files from the Digital Foundry Patreon page')
    parser.add_argument('-b', '--browser', choices=['chrome', 'safari', 'firefox'], required=True)
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S')
    output_path = askdirectory()

    root.update()

    print(output_path)
    if output_path == '':
        logging.warning("No output path selected. Using current directory")
        output_path = '.'

    signal(SIGINT, handle_sigint)
    while True:
        process(args.browser, output_path)
        logging.info(f"Sleeping for {refresh_rate_min} minutes.")
        sleep(refresh_rate_min * 60)


def has_valid_cookie(cj: CookieJar) -> bool:
    """Checks if there is a valid digital foundry cookie in the cookie jar"""
    df_cookie: Cookie = None
    for cookie in cj:
        if cookie.domain == domain:
            df_cookie = cookie
            break
    if df_cookie is None:
        logging.warning('No Digital Foundry cookie found. Please log in to Digital Foundry in Google Chrome.')
        return False
    if df_cookie.is_expired(time.time()):
        logging.warning('Digital Foundry cookie expired. Please log in to Digital Foundry in Google Chrome.')
        return False
    return True


def get_links(r: Response, cache_file_path: str) -> Tuple[List[str], List[str]]:
    """Gets all the download links from a given response. If link is in cache, it won't be added to list."""
    soup = BeautifulSoup(r.content, 'html.parser')
    all_buttons = soup.find_all('a', {'class', 'button'})

    hevc_hrefs = []
    other_hrefs = []

    total_downloads_available = 0

    try:
        cache = open(cache_file_path, "r")
        has_cache = True
    except Exception as ex:
        has_cache = False
        logging.error(f"Problem opening cache file from {cache_file_path}: {ex}")
    finally:
        if has_cache:
            whole_file = cache.read()
        for button in all_buttons:
            text = button.get_text()
            if text == other_downloads:
                total_downloads_available += 1
                if not button['href'] in whole_file or not has_cache:
                    other_hrefs.append(button['href'])
            elif text == hevc:
                total_downloads_available += 1
                if not button['href'] in whole_file or not has_cache:
                    hevc_hrefs.append(button['href'])
        if has_cache:
            cache.close()

    if total_downloads_available <= 2:
        logging.warning('Only found 2 downloads. Make sure you are logged in to Digital Foundry in Google Chrome')
    return hevc_hrefs, other_hrefs


def process_other_downloads(href: str, cookies: CookieJar, current: int, total: int, output_path: str) -> None:
    """Follows HEVC link on a page with two file types"""
    r = get(url + href, cookies=cookies)
    soup = BeautifulSoup(r.content, 'html.parser')
    hevc_button = soup.find_all('a', class_='button wide download', limit=2)
    process_hevc_download(hevc_button[1]['href'], href, cookies, current, total, output_path)


def process_hevc_download(href: str, original_link: str, cookies: CookieJar, current: int, total: int, output_path: str) -> None:
    """Follows Download Now link on HEVC download page"""
    r = get(url + href, cookies=cookies)
    soup = BeautifulSoup(r.content, 'html.parser')
    download_button = soup.find('a', text=download_now)
    download_video(soup.title.get_text(), download_button['href'], original_link, cookies, current, total, output_path)


def convert_title(title: str) -> str:
    """Converts a title to a filename that can be used.

        Removes '/' and replaces with '-'

        Removes ':' and replaces with '|'"""
    title = title[len(download_prefix):]
    title = title.replace('/', '-')
    title = title.replace(':', '|')
    return title


def download_video(title: str, href: str, original_link: str, cookies: CookieJar, current: int, total: int, output_path: str) -> None:
    """Downloads a file at the given href"""
    # Get actual video
    r = get(url + href, cookies=cookies, stream=True)
    total_length = r.headers.get('content-length')
    title = convert_title(title)
    logging.info('Downloading...')
    print(f'{current}/{total} {title}')
    try:
        with open(output_path + "/" + title + '.mp4', 'wb') as f:
            if total_length is None:  # no content length header
                f.write(r.content)
            else:
                download_with_progress(r, f, int(total_length))
    except Exception as ex:
        logging.error(f"Failed to download {title}: {ex}")
    try:
        with open(cache_file, 'a') as f:
            f.write(original_link + '\n')
    except Exception as ex:
        logging.error(f"Could not open cach file at {cache_file}: {ex}")
    print()


def download_with_progress(r: Response, f: BinaryIO, total_length: int):
    """Downloads data to a file, showing progress on stdout."""
    dl = 0
    for data in r.iter_content(chunk_size=4096):
        dl += len(data)
        f.write(data)
        done = 50 * dl // total_length
        sys.stdout.write(f"\r[{'=' * (done - 1)}{'=' if done == 50 else '' if done == 0 else '>'}{' ' * (50 - done)}]"
                         f" {100 * dl // total_length:3d}%")
        sys.stdout.flush()


if __name__ == '__main__':
    main()
