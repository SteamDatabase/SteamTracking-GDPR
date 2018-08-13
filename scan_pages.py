#!/usr/bin/env python

import re
import os
import sys
import pickle
import logging
from time import sleep
from urllib.parse import urlencode
from getpass import getpass
from requests_html import HTMLSession
from steam import webauth as wa

logging.basicConfig(level=logging.DEBUG if sys.argv[-1] == 'debug' else logging.ERROR,
                    format="%(levelname)-8s | %(message)s",
                    )
LOG = logging.getLogger()

# change cwd to wherever this file is
try:
    os.chdir(os.path.dirname(__file__))
except:
    pass

def load_cookies():
    try:
        return pickle.load(open('.steamcookies', 'rb'))
    except Exception as exp:
        LOG.error("Failed to load cookie file")
        LOG.exception(exp)
        return


def save_cookies(inst):
    try:
        pickle.dump(inst, open('.steamcookies', 'wb'))
    except Exception as exp:
        LOG.error("Failed to save cookie file")
        LOG.exception(exp)
        return


def login():
    username = input("Steam Username:")
    password = getpass()

    twofactor_code = email_code = captch = None

    steam_auth = wa.WebAuth(username, password)

    while not steam_auth.complete:
        try:
            steam_auth.login(twofactor_code=twofactor_code,
                             email_code=email_code,
                             captcha=captch,
                             )
        except wa.CaptchaRequired:
            LOG.info("Captch URL: %s", steam_auth.captcha_url)
            captch = input("Captch code:")
        except wa.EmailCodeRequired:
            email_code = input("Email code:")
        except wa.TwoFactorCodeRequired:
            twofactor_code = input("2FA code:")

    save_cookies(steam_auth.session.cookies)
    return steam_auth.session.cookies


# BEGIN SESSION ===========================================================================

cookies = load_cookies()

if not cookies:
    LOG.error("Login required")

    if sys.stdin.isatty():
        cookies = login()
    else:
        sys.exit(1)

web = HTMLSession()
web.cookies = cookies

steamid = web.cookies.get_dict()['steamLoginSecure'].split('%', 1)[0]

# verify that login hasn't randomly expired
resp = web.get('https://store.steampowered.com/account/')

if resp.history:
    LOG.error("Login has expired")
    os.remove('.steamcookies')
    sys.exit(1)

# ACCOUNT DATA HELP PAGE =================================================================

LOG.info("Scanning help site accountdata page...")

resp = web.get('https://help.steampowered.com/en/accountdata', allow_redirects=False)

if resp.status_code != 200:
    LOG.error("Failed to load accountdata page. HTTP Code: %d", resp.status_code)
else:
    # generate markdown version of the account data page
    elements = resp.html.find('.AccountDataPage .feature_title,.AccountDataPage a')

    if not elements:
        LOG.error("Account page has no elements")
    else:
        with open("steam_accountdata.md", "w") as fp:
            for elm in elements:
                title = elm.text

                # a tags are for pages
                if elm.element.tag == 'a':
                    if steamid in elm.attrs['href']:
                        raise RuntimeError("SteamID in URL")

                    url = elm.attrs['href']

                    fp.write(f'{title} | {url}\n')
                # feature_title are the seperate categories
                else:
                    underline = '-' * len(title)

                    fp.write(f"\n{title}\n"
                             f"{underline}\n"
                             f"\n"
                             f"Page | URL\n"
                             f"--- | ---\n"
                             )

# Dota 2 gcpd pages =====================================================================

LOG.info("Scanning Dota 2 pages...")

try:
    prev_pages = pickle.load(open('.gcpd_570', 'rb'))
except Exception as exp:
    prev_pages = {}
    LOG.info("Failed to load previous Dota 2 gcpd data")
#   LOG.exception(exp)

url = 'https://steamcommunity.com/my/gcpd/570'

resp = web.get(url)

if resp.status_code != 200:
    LOG.info("Failed to load Dota 2 gcpd page. HTTP Code: %d", resp.status_code)
else:
    pages = {}

    # scan through all the dota gcpd pages
    for category, sub, subname in re.findall(r"#profile_private_info_categories_dd.*?== \'(.*?)\' \).*?{ value:\'(.*?)\', text:\'(.*?)\'}", resp.html.text):
        LOG.info("Loading %s -> %s", category, sub)

        for c in range(4):
            resp = web.get(url, params={'category': category, 'tab': sub})

            # check if data failed to load and retry
            if resp.status_code != 200 or resp.html.find('.profile_ban_status'):
                sleep(2 ** (c+1) - 1)
                continue

            break

        # if we still failed to load, error out
        if resp.html.find('.profile_ban_status'):
            LOG.info("Failed after %s tries: %s", c+1, resp.html.find('.profile_ban_status', first=True).text)
            columns = []
        else:
            columns = list(map(lambda x: x.text, resp.html.find('.generic_kv_table th')))

        if not columns:
            columns = prev_pages.get((category, sub), [])

        pages.setdefault(category, []).append((sub, columns))

    # generate output file
    LOG.info("Generating dota2_570_gcpd.md...")

    page_data = {}

    if not pages:
        LOG.info("Empty pages Dota 2 (570)")
    else:
        with open('dota2_570_gcpd.md', 'w') as fp:
            for i, category in enumerate(sorted(pages.keys()), 1):
                category_url = url + "?" + urlencode({'category': category})

                fp.write(f"{i}. [{category}]({category_url})\n")

                for ii, (subcat, columns) in enumerate(sorted(pages[category]), 1):
                    page_data[(category, subcat)] = columns

                    subcat_url = url + "?" + urlencode({'category': category, 'tab': subcat})

                    fp.write(f"    {ii}. [{subcat}]({subcat_url})\n")

                    for column in columns:
                        fp.write(f"        * {column}\n")

        # save page data for next run
        try:
            pickle.dump(page_data, open('.gcpd_570', 'wb'))
        except Exception as exp:
            LOG.info("Failed to save Dota 2 gcpd data")
#           LOG.exception(exp)

# Other gcpd pages =====================================================================

games = [
    ('730', 'csgo', 'Counter-Strike: Global Offensive'),
    ('620', 'portal2',  'Portal 2'),
    ('440', 'tf2',  'Team Fortress 2'),
]

for appid, game_title_short, game_title in games:
    url = f'https://steamcommunity.com/my/gcpd/{appid}'

    LOG.info("Scanning %s pages...", game_title)

    try:
        prev_pages = pickle.load(open(f'.gcpd_{appid}', 'rb'))
    except Exception as exp:
        prev_pages = {}
        LOG.info("Failed to load previous %s gcpd data", game_title)
#       LOG.exception(exp)

    resp = web.get(url)

    if resp.status_code != 200:
        LOG.info("Failed to load %s gcpd page. HTTP Code: %d", game_title, resp.status_code)
    else:
        pages = {}

        # scan through all the dota gcpd pages
        for tab_name, tab_id in list(map(lambda e: (e.text, e.attrs['id'].split('_', 1)[1]), resp.html.find('#tabs .tab'))):
            LOG.info("Loading %s...", tab_name)

            for c in range(4):
                resp = web.get(url, params={'tab': tab_id})

                # check if data failed to load and retry
                if resp.status_code != 200 or resp.html.find('.profile_ban_status'):
                    sleep(2 ** (c+1) - 1)
                    continue

                break

            # if we still failed to load, error out
            if resp.html.find('.profile_ban_status'):
                LOG.info("Failed after %s tries: %s", c+1, resp.html.find('.profile_ban_status', first=True).text)
                columns = []
            else:
                columns = sorted(set(map(lambda x: x.text, resp.html.find('.generic_kv_table th'))))

            if not columns:
                columns = prev_pages.get((tab_name, tab_id), [])

            pages[(tab_name, tab_id)] = columns

        # generate output file
        LOG.info(f"Generating {game_title_short}_{appid}_gcpd.md...")

        if not pages:
            LOG.info("Empty pages for %s (%s)", game_title, appid)
        else:
            with open(f'{game_title_short}_{appid}_gcpd.md', 'w') as fp:
                for i, ((tab_name, tab_id), columns) in enumerate(sorted(pages.items()), 1):

                    tab_url = url + "?" + urlencode({'tab': tab_id})

                    fp.write(f"{i}. [{tab_name}]({tab_url})\n")

                    for column in columns:
                        if column:
                            fp.write(f"    * {column}\n")

            # save page data for next run
            try:
                pickle.dump(pages, open(f'.gcpd_{appid}', 'wb'))
            except Exception as exp:
                LOG.info("Failed to save %s gcpd data", game_title)
                LOG.exception(exp)
