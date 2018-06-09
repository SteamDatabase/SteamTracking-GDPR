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

logging.basicConfig(level=logging.INFO if sys.argv[-1] == 'debug' else logging.ERROR,
                    format="%(levelname)-8s | %(message)s",
                    )
LOG = logging.getLogger()

# change cwd to wherever this file is
os.chdir(os.path.dirname(__file__))

def load_cookies():
    try:
        return pickle.load(open('.steamcookies', 'rb'))
    except Exception as exp:
        LOG.error("Failed to load cookie file")
        LOG.exception(exp)
        return

    LOG.error("No previous cookies found :(")


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


# BEIN SESSION ===========================================================================

cookies = load_cookies()

if not cookies:
    cookies = login()

web = HTMLSession()
web.cookies = cookies

steamid = web.cookies.get_dict()['steamLogin'].split('%', 1)[0]

# ACCOUNT DATA HELP PAGE =================================================================

LOG.info("Scanning help site accountdata page...")

resp = web.get('https://help.steampowered.com/en/accountdata')

if resp.status_code != 200:
    LOG.error("Failed to load accountdata page. HTTP Code: %d", resp.status_code)
else:
    # generate markdown version of the account data page
    with open("steam_accountdata.md", "w") as fp:
        for elm in resp.html.find('.AccountDataPage .feature_title,.AccountDataPage a'):
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
    prev_pages = pickle.load(open('.gcpd_dota', 'rb'))
except Exception as exp:
    prev_pages = {}
    LOG.error("Failed to load previous Dota 2 gcpd data")
    LOG.exception(exp)

url = 'https://steamcommunity.com/my/gcpd/570'

resp = web.get(url)

if resp.status_code != 200:
    LOG.error("Failed to load Dota 2 gcpd page. HTTP Code: %d", resp.status_code)
else:
    pages = {}

    # scan through all the dota gcpd pages
    for category, sub, subname in re.findall(r"#profile_private_info_categories_dd.*?== \'(.*?)\' \).*?{ value:\'(.*?)\', text:\'(.*?)\'}", resp.html.text):
        LOG.info("Loading %s -> %s", category, sub)

        for c in range(4):
            resp = web.get(url, params={'category': category, 'tab': sub})
            resp.raise_for_status()

            # check if data failed to load and retry
            if resp.html.find('.profile_ban_status'):
                sleep(2 ** (c+1) - 1)
                continue

            break

        # if we still failed to load, error out
        if resp.html.find('.profile_ban_status'):
            LOG.error("Failed after %s tries: %s", c+1, resp.html.find('.profile_ban_status', first=True).text)
            columns = prev_pages.get((category, sub), [])
        else:
            columns = list(map(lambda x: x.text, resp.html.find('.generic_kv_table th')))

        pages.setdefault(category, []).append((sub, columns))

    # generate output file
    LOG.info("Generating dota2_570_gcpd.md...")

    page_data = {}

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
        pickle.dump(page_data, open('.gcpd_dota', 'wb'))
    except Exception as exp:
        LOG.error("Failed to save Dota 2 gcpd data")
        LOG.exception(exp)
