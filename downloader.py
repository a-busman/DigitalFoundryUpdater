from browser_cookie3 import chrome, firefox
from requests import get, Response
from notify import Notifier
from threading import Lock
from typing import List, Dict, Tuple
from sys import stdout
from time import time

import bs4
import logging as log
import os


def _convert_title(title: str) -> str:
    """Converts a title to a filename that can be used."""
    blacklist = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '\0']

    download_prefix = 'Download '
    title = title[len(download_prefix):]
    title = ''.join(c for c in title if c not in blacklist)

    return title


def _download_with_progress(r: Response, filename: str, total_length: int):
    """Downloads data to a file, showing progress on stdout."""
    chunk_size = 4096
    dl = 0
    last = time()
    last_size = 0
    rate = 0
    units = 'B'
    with open(filename, 'wb') as f:
        for data in r.iter_content(chunk_size=chunk_size):
            dl += len(data)
            f.write(data)
            done = 50 * dl // total_length
            now = time()
            diff = now - last
            if diff > 1.0:
                rate, units = _get_units(int(float(dl - last_size) / diff))
                last = now
                last_size = dl

            stdout.write(f"\r[{'=' * (done - 1)}{'=' if done == 50 else '' if done == 0 else '>'}{' ' * (50 - done)}]"
                         f' {100 * dl // total_length:3d}% {rate:4d} {units}/s')
            stdout.flush()


def _get_units(b: int) -> Tuple[int, str]:
    """Gets a divided byte size and unit describing the size"""
    ret_rate = 0
    ret_unit = 'B'
    iters = 0
    while b > 0:
        ret_rate = b
        b //= 1024
        iters += 1

    if iters == 2:
        ret_unit = 'KiB'
    elif iters == 3:
        ret_unit = 'MiB'
    elif iters == 4:
        ret_unit = 'GiB'
    elif iters == 5:
        ret_unit = 'TiB'

    return ret_rate, ret_unit


def _logged_in(soup: bs4.BeautifulSoup) -> bool:
    """Checks to see if there are any subscribe buttons on page"""
    subscribe_button = soup.find('a', href='/sign-up')
    return subscribe_button is None


class Downloader:
    """A downloader which checks for new videos on the Digital Foundry homepage, and downloads them."""
    __scheme = 'https://'
    __domain = 'www.digitalfoundry.net'
    __url = __scheme + __domain
    __home_url = __url + '/archive'
    __cache_file = 'cache'

    __download_strings = {
        'hevc': 'Download HEVC',
        'avc': 'Download h.264',
        'now': 'Download now',
    }

    def __init__(self, browser: str, notifier: Notifier, output_dir: str, collection: str):
        self.__browser = browser
        self.__load_cookie_jar()
        self.__output_dir = output_dir
        self.__notifier = notifier
        self.__lock = Lock()
        self.__collection = collection

    def __load_cookie_jar(self):
        if self.__browser == 'chrome':
            self.__cj = chrome()
        elif self.__browser == 'firefox':
            self.__cj = firefox()
        else:
            raise ValueError(f'invalid browser: {self.__browser}')

    def load_cookie_jar(self):
        self.__load_cookie_jar()

    def download(self) -> None:
        """Checks the Digital Foundry homepage for new videos, and downloads them."""
        if not self.__has_valid_cookie():
            return

        self.__lock.acquire()

        if self.__collection is None:
            checking = 'Digital Foundry Homepage'
            url = self.__home_url
        else:
            checking = f'{self.__collection} collection'
            url = self.__url + '/browse/' + self.__collection

        log.info(f'Checking {checking}...')
        r = get(url, cookies=self.__cj)

        if not r.ok:
            msg = "Can't reach Digital Foundry Homepage."
            log.warning(msg)
            self.__notify(msg)
            self.__lock.release()
            return

        hrefs = self.__get_links(r)
        total_downloads = len(hrefs)

        if total_downloads > 0:
            log.info(f"Found {total_downloads} new video{'s' if total_downloads > 1 else ''}!")
        for i in range(0, total_downloads):
            self.__process_downloads(hrefs[i], i + 1, total_downloads)
        log.info('All videos downloaded.')
        self.__lock.release()
        return

    def __notify(self, msg: str):
        """Notifies if the notifier is present"""
        if self.__notifier is not None:
            self.__notifier.notify(msg)

    def __has_valid_cookie(self) -> bool:
        """Checks if there is a valid digital foundry cookie in the cookie jar"""
        df_cookie = None

        for cookie in self.__cj:
            if cookie.domain == self.__domain:
                df_cookie = cookie
                break

        if df_cookie is None:
            msg = 'No Digital Foundry cookie found. Please log in to Digital Foundry in your browser.'
            log.warning(msg)
            self.__notify(msg)
            return False
        elif df_cookie.is_expired(time()):
            msg = 'Digital Foundry cookie expired. Please log in to Digital Foundry in your browser.'
            log.warning(msg)
            self.__notify(msg)
            return False

        return True

    def __get_links(self, r: Response) -> List[Dict[str, str]]:
        """Gets all the download links from a given response. If link is in cache, it won't be added to list."""
        soup = bs4.BeautifulSoup(r.content, 'html.parser')

        if not _logged_in(soup):
            msg = 'Subscribe button found. Make sure you are logged in to Digital Foundry in your browser.'
            log.warning(msg)
            self.__notify(msg)
            return []

        # Main page grid items are only "featured". We want the regular video categories.
        if self.__collection is None:
            all_videos = soup.find_all('div', {'class', 'summary'})
        else:
            all_videos = soup.find_all('div', {'class', 'video-grid-item'})

        hrefs = []

        total_downloads_available = 0

        cache = None
        whole_file = ''
        try:
            cache = open(self.__cache_file, 'r')
        except Exception:
            log.exception(f'Problem opening cache file from {self.__cache_file}')
        finally:
            if cache is not None:
                whole_file = cache.read()
            for video in all_videos:
                art_tag = video.find('a', {'class', 'link_overlay'})
                total_downloads_available += 1
                if (cache is not None and art_tag['href'] not in whole_file) or cache is None:
                    hrefs.append({'href': art_tag['href']})
            if cache is not None:
                cache.close()

        return hrefs

    def __process_downloads(self, href: Dict[str, str], current: int, total: int) -> None:
        """Follows HEVC link on a page with two file types"""
        r = get(href['href'], cookies=self.__cj)
        soup = bs4.BeautifulSoup(r.content, 'html.parser')
        dl_buttons = soup.find_all('a', class_='button primary download', limit=2)
        dl_button = None
        hevc_button = None
        avc_button = None
        for button in dl_buttons:
            text = button.get_text()
            if text == self.__download_strings['hevc']:
                hevc_button = button
            elif text == self.__download_strings['avc']:
                avc_button = button
        if hevc_button is not None:
            dl_button = hevc_button
        elif avc_button is not None:
            dl_button = avc_button

        if dl_button is None:
            return

        self.__download_video(soup.title.get_text(), dl_button['href'], href, current, total)

    def __download_video(self, title: str, href: str, original_link: Dict[str, str], current: int, total: int) -> None:
        """Downloads a file at the given href"""
        # Get actual video
        r = get(href, cookies=self.__cj, stream=True)
        total_length = int(r.headers.get('content-length'))
        title = _convert_title(title)
        if r.status_code == 404:
            log.error(f'{self.__url}{href} returned 404')
            self.__notify(f'{title} returned 404')
            return

        log.info('Downloading...')
        log.info(f'{current}/{total} {title}')
        file_name = self.__output_dir + '/' + title + '.mp4'
        try:
            complete = False
            for i in range(5):
                _download_with_progress(r, file_name, total_length)
                actual_size = os.path.getsize(file_name)
                if actual_size != total_length:
                    log.error(f'File size mismatch. Got {actual_size}, expected {total_length}. Redownloading...')
                    r = get(self.__url + href, cookies=self.__cj, stream=True)
                else:
                    complete = True
                    break
            if not complete:
                raise RuntimeError('Retries failed')
            self.__notify(f'New video downloaded: {title}')
        except Exception:
            log.exception(f'Failed to download {title}')
        else:
            try:
                with open(self.__cache_file, 'a') as f:
                    f.write(original_link['href'] + '\n')
            except Exception:
                log.exception(f'Could not open cache file at {self.__cache_file}')
        print()