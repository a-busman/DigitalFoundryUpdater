from bs4 import BeautifulSoup, Tag
from browsercookie import chrome, safari, firefox
from requests import get, Response
from notify import Notifier
from threading import Lock
from typing import BinaryIO, Tuple, List, Dict

import logging
import toml
import sys
import time


def _parse_conf(conf_file: str):
    """Parses the incoming toml config file"""
    conf = toml.load(conf_file)

    sid = conf['auth']['sid']
    token = conf['auth']['token']

    to = conf['phone']['to']
    from_ = conf['phone']['from']

    browser = conf['conf']['browser']

    return browser, sid, token, to, from_


def _convert_title(title: str) -> str:
    """Converts a title to a filename that can be used.

        Removes '/' and replaces with '-'

        Removes ':' and replaces with '|'"""
    download_prefix = 'Download '
    title = title[len(download_prefix):]
    title = title.replace('/', '-')
    title = title.replace(':', '|')
    return title


def _download_with_progress(r: Response, f: BinaryIO, total_length: int):
    """Downloads data to a file, showing progress on stdout."""
    dl = 0
    for data in r.iter_content(chunk_size=4096):
        dl += len(data)
        f.write(data)
        done = 50 * dl // total_length
        sys.stdout.write(f"\r[{'=' * (done - 1)}{'=' if done == 50 else '' if done == 0 else '>'}{' ' * (50 - done)}]"
                         f" {100 * dl // total_length:3d}%")
        sys.stdout.flush()


def _get_art_link(art_tag: Tag) -> str:
    """Gets the cover art link for a given video tag"""
    style_str = art_tag['style']
    tokens = style_str.split('(')
    url = 'https:' + tokens[1][:-1]
    url = url.split('.jpg')
    return url[0] + '.jpg'


class Downloader:
    """A downloader which checks for new videos on the Digital Foundry homepage, and downloads them."""
    __scheme = 'https://'
    __domain = 'www.digitalfoundry.net'
    __url = __scheme + __domain
    __cache_file = 'cache'

    __download_strings = {
        'other': 'See more download options',
        'hevc': ' Download HEVC',
        'now': 'Download now'
    }

    def __init__(self, conf_file: str, output_dir: str):
        browser, sid, token, to, from_ = _parse_conf(conf_file)
        self.__browser = browser
        self.__load_cookie_jar()
        self.__output_dir = output_dir
        self.__notifier = Notifier(sid, token, to, from_)
        self.__lock = Lock()

    def __load_cookie_jar(self):
        if self.__browser == 'chrome':
            self.__cj = chrome()
        elif self.__browser == 'safari':
            self.__cj = safari()
        elif self.__browser == 'firefox':
            self.__cj = firefox()
        else:
            raise ValueError

    def load_cookie_jar(self):
        self.__load_cookie_jar()

    def download(self) -> None:
        """Checks the Digital Foundry homepage for new videos, and downloads them."""
        if not self.__has_valid_cookie():
            return

        self.__lock.acquire()
        logging.info('Checking Digital Foundry Homepage...')
        r = get(self.__url, cookies=self.__cj)
        if not r.ok:
            msg = 'Can\'t reach Digital Foundry Homepage.'
            logging.warning(msg)
            self.__notifier.notify(msg)
            self.__lock.release()
            return

        hrefs = self.__get_links(r)
        total_downloads = len(hrefs)

        if total_downloads > 0:
            logging.info(f"Found {total_downloads} new video{'s' if total_downloads > 1 else ''}!")
        for i in range(0, len(hrefs)):
            self.__process_downloads(hrefs[i], i + 1, total_downloads)
        logging.info("All videos downloaded.")
        self.__lock.release()
        return

    def __has_valid_cookie(self) -> bool:
        """Checks if there is a valid digital foundry cookie in the cookie jar"""
        df_cookie = None

        for cookie in self.__cj:
            if cookie.domain == self.__domain:
                df_cookie = cookie
                break

        if df_cookie is None:
            msg = 'No Digital Foundry cookie found. Please log in to Digital Foundry in your browser.'
            logging.warning(msg)
            self.__notifier.notify(msg)
            return False
        elif df_cookie.is_expired(time.time()):
            msg = 'Digital Foundry cookie expired. Please log in to Digital Foundry in your browser.'
            logging.warning(msg)
            self.__notifier.notify(msg)
            return False

        return True

    def __get_links(self, r: Response) -> List[Dict[str, str]]:
        """Gets all the download links from a given response. If link is in cache, it won't be added to list."""
        soup = BeautifulSoup(r.content, 'html.parser')
        all_videos = soup.find_all('div', {'class', 'video'})

        hrefs = []

        total_downloads_available = 0

        cache = None
        whole_file = ""
        try:
            cache = open(self.__cache_file, "r")
        except Exception as ex:
            logging.error(f"Problem opening cache file from {self.__cache_file}: {ex}")
        finally:
            if cache is not None:
                whole_file = cache.read()
            for video in all_videos:
                art_tag = video.find('a', {'class', 'cover'})
                art = _get_art_link(art_tag)
                total_downloads_available += 1
                if (cache is not None and art_tag['href'] not in whole_file) or cache is None:
                    hrefs.append({'art': art, 'href': art_tag['href']})
            if cache is not None:
                cache.close()

        if total_downloads_available <= 2:
            msg = f'Only found {total_downloads_available} download(s). Make sure you are logged in to Digital Foundry in your browser'
            logging.warning(msg)
            self.__notifier.notify(msg)
        return hrefs

    def __process_downloads(self, href: Dict[str, str], current: int, total: int) -> None:
        """Follows HEVC link on a page with two file types"""
        r = get(self.__url + href['href'], cookies=self.__cj)
        soup = BeautifulSoup(r.content, 'html.parser')
        dl_buttons = soup.find_all('a', class_='button wide download', limit=2)
        hevc_button = None
        for button in dl_buttons:
            if button.get_text() == self.__download_strings['hevc']:
                hevc_button = button
                break
        if hevc_button is None:
            return
        self.__process_hevc_download(hevc_button['href'], href, current, total)

    def __process_hevc_download(self, href: str, original_link: Dict[str, str], current: int, total: int) -> None:
        """Follows Download Now link on HEVC download page"""
        r = get(self.__url + href, cookies=self.__cj)
        soup = BeautifulSoup(r.content, 'html.parser')
        download_button = soup.find('a', text=self.__download_strings['now'])
        self.__download_video(soup.title.get_text(), download_button['href'], original_link, current, total)

    def __download_video(self, title: str, href: str, original_link: Dict[str, str], current: int, total: int) -> None:
        """Downloads a file at the given href"""
        # Get actual video
        r = get(self.__url + href, cookies=self.__cj, stream=True)
        total_length = r.headers.get('content-length')
        title = _convert_title(title)
        if r.status_code == 404:
            logging.error(f"{self.__url}{href} returned 404")
            self.__notifier.notify(f"{title} returned 404")
            return

        logging.info('Downloading...')
        print(f'{current}/{total} {title}')
        try:
            with open(self.__output_dir + '/' + title + '.mp4', 'wb') as f:
                self.__download_art(original_link['art'], title)
                if total_length is None:  # no content length header
                    f.write(r.content)
                    self.__notifier.notify(f'New video downloaded: {title}')
                else:
                    _download_with_progress(r, f, int(total_length))
                    self.__notifier.notify(f'New video downloaded: {title}')
        except Exception as ex:
            logging.error(f"Failed to download {title}: {ex}")
        else:
            try:
                with open(self.__cache_file, 'a') as f:
                    f.write(original_link['href'] + '\n')
            except Exception as ex:
                logging.error(f"Could not open cache file at {self.__cache_file}: {ex}")
        print()

    def __download_art(self, href: str, title: str):
        """Downloads a jpg at the given href"""
        art = get(href, cookies=self.__cj)
        with open(self.__output_dir + '/' + title + '.jpg', 'wb') as f:
            f.write(art.content)
