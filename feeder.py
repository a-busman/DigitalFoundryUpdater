import feedparser
import bs4
import logging as log
from urllib.parse import urlparse
from requests import get
from typing import List, Dict
from http.cookiejar import CookieJar


class Feeder:
    """Parses the Digital Foundry RSS feed and gets download links"""
    __scheme = 'https://'
    __domain = 'www.digitalfoundry.net'
    __path = '/feed'
    __url = __scheme + __domain + __path

    __download_strings = {
        'hevc': 'HEVC',
        'avc':  'h.264',
    }

    def __init__(self, cj: CookieJar, cache_file: str):
        self.__cj = cj
        self.__cache_file = cache_file

    def __get_video_link(self, page_url: str) -> str:
        """Gets the optimal video link from a given page link"""
        r = get(page_url, cookies=self.__cj)
        if not r.ok:
            raise ValueError(f'Page error: {r.status_code}')
        soup = bs4.BeautifulSoup(r.content, 'html.parser')
        if soup.find('section', {'class': 'supporter_promo'}) is not None:
            raise ValueError('Not subscribed to video tier')

        files = soup.find_all('div', {'class': 'video_data_file'})
        hevc_link = ''
        avc_link = ''
        for file in files:
            name = file.find('p', {'class': 'name'}).get_text()
            if name == self.__download_strings['hevc']:
                hevc_link = file.find('a')['href']
                break
            elif name == self.__download_strings['avc']:
                avc_link = file.find('a')['href']

        if hevc_link != '':
            link = hevc_link
        elif avc_link != '':
            link = avc_link
        else:
            raise ValueError('Link not found')

        return link

    @property
    def __cache_file_text(self) -> str:
        with open(self.__cache_file, 'r') as cache:
            return cache.read()

    def get_links(self) -> List[Dict[str, str]]:
        log.info(f'Checking Digital Foundry RSS feed...')

        feed = feedparser.parse(self.__url)
        if feed.status is not None and feed.status != 200:
            raise ValueError(f'RSS feed error: {feed.status}')

        entries = feed.entries
        videos = []

        cache = self.__cache_file_text

        for entry in entries:
            link = entry['link']
            path = urlparse(link).path
            if cache != '' and path in cache:
                continue

            try:
                video_link = self.__get_video_link(link)
            except ValueError as e:
                log.error(f'{link}: {e}')
                continue
            else:
                video = {'title': entry['title'],
                         'path': path,
                         'img_url': entry['media_content'][0]['url'],
                         'vid_url': video_link}
                videos.append(video)

        return videos
