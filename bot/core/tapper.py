import asyncio
import random
import string
import time
from urllib.parse import unquote, quote

import aiohttp
import json
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView

from .agents import generate_random_user_agent
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers
from .helper import format_duration


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None
        self.role_type = None
        self.player_id = None

        self.session_ug_dict = self.load_user_agents() or []

        headers['User-Agent'] = self.check_user_agent()

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type='android', browser_type='chrome')

    def info(self, message):
        from bot.utils import info
        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug
        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning
        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error
        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical
        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success
        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"

        if not any(session['session_name'] == self.session_name for session in self.session_ug_dict):
            user_agent_str = generate_random_user_agent()

            self.session_ug_dict.append({
                'session_name': self.session_name,
                'user_agent': user_agent_str})

            with open(user_agents_file_name, 'w') as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)

            logger.success(f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully")

            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"

        try:
            with open(user_agents_file_name, 'r') as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data

        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")

        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")

        return []

    def check_user_agent(self):
        load = next(
            (session['user_agent'] for session in self.session_ug_dict if session['session_name'] == self.session_name),
            None)

        if load is None:
            return self.save_user_agent()

        return load

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            if settings.REF_ID == '':
                self.start_param = 'share_6168926126'
            else:
                self.start_param = settings.REF_ID

            peer = await self.tg_client.resolve_peer('OfficialBananaBot')
            # InputBotApp = types.InputBotAppShortName(bot_id=peer, short_name="game")

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://interface.carv.io'
            ))

            auth_url = web_view.url
            #print(auth_url)
            # self.success(f"auth_url:{auth_url}")
            tg_web_data = unquote(
                string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])

            try:
                if self.user_id == 0:
                    information = await self.tg_client.get_me()
                    self.user_id = information.id
                    self.first_name = information.first_name or ''
                    self.last_name = information.last_name or ''
                    self.username = information.username or ''
            except Exception as e:
                print(e)

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: aiohttp.ClientSession, initdata: str):
        try:
            json_data = {"tgInfo": initdata}
            resp = await http_client.post("https://interface.carv.io/banana/login", json=json_data, ssl=False)
            if resp.status == 429:
                seconds = int(resp.headers.get('Retry-After')) * 60 + 60
                self.warning(f"{resp.reason} sleep {seconds}")
                await asyncio.sleep(seconds)
                return await self.login(http_client=http_client, initdata=initdata)
            resp_json = await resp.json()
            return resp_json.get("data").get("token"), resp.headers['set-cookie'], resp.cookies

        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Login error {error}")

    async def get_lottery_info(self, http_client: aiohttp.ClientSession):
        try:
            http_client.headers['Request-Time'] = str(int(time.time() * 1000))
            resp = await http_client.get("https://interface.carv.io/banana/get_lottery_info", ssl=False)
            resp_json = await resp.json()
            remain_lottery_count = resp_json['data']['remain_lottery_count']
            if remain_lottery_count > 0:
                self.info(f"remain lottery count:{remain_lottery_count}")
                await self.do_lottery(http_client=http_client)

            last_countdown_start_time = resp_json['data']['last_countdown_start_time']
            if (time.time() - (last_countdown_start_time / 1000)) / 60 > resp_json['data']['countdown_interval']:
                await self.claim_lottery(http_client=http_client)
            return True
        except Exception as e:
            self.error(f"get_lottery_info: {e}")

    async def claim_lottery(self, http_client: aiohttp.ClientSession):
        try:
            json_data = {"claimLotteryType": 1}
            resp = await http_client.post("https://interface.carv.io/banana/claim_lottery", json=json_data, ssl=False)
            resp_json = await resp.json()
            if resp_json['msg'] == u'Success':
                self.success(f"Claim your Banana")
        except Exception as e:
            self.error(f"claim_lottery: {e}")

    async def do_lottery(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post("https://interface.carv.io/banana/do_lottery", json={}, ssl=False)
            resp_json = await resp.json()
            if resp_json['msg'] == u'Success':
                self.success(f"Harvest")
        except Exception as e:
            self.error(f"do_lottery: {e}")

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Proxy: {proxy} | Error: {error}")

    async def get_user_info(self, http_client: aiohttp.ClientSession):
        try:
            max_click_count = 60
            today_click_count = 0
            while max_click_count > today_click_count:
                http_client.headers['Request-Time'] = str(int(time.time() * 1000))
                resp = await http_client.get("https://interface.carv.io/banana/get_user_info", ssl=False)
                if resp.status == 200:
                    resp_json = await resp.json()
                    data = resp_json.get('data')
                    max_click_count = data['max_click_count']
                    today_click_count = data['today_click_count']
                    if data is not None:
                        if max_click_count > today_click_count:
                            self.info(f"peels:{data['peel']}, max_click_count:{data['max_click_count']},"
                                      f" today_click_count:{data['today_click_count']}")
                            await self.do_click(http_client=http_client)
                            await asyncio.sleep(random.randint(40, 60))
                        else:
                            logger.success(f"Click Already completed")
                else:
                    return True
            return True
        except Exception as e:
            self.error(f"do_click error: {e}")

    async def do_click(self, http_client: aiohttp.ClientSession):
        try:
            click_count = random.randint(settings.CLICK_COUNT[0], settings.CLICK_COUNT[1])
            json_data = {'clickCount': click_count}
            resp = await http_client.post("https://interface.carv.io/banana/do_click", json=json_data, ssl=False)
            resp_json = await resp.json()
            data = resp_json.get('data')
            if data is not None:
                self.success(f"Click Peel: {data['peel']}")
        except Exception as e:
            self.error(f"do_click error: {e}")

    async def get_quest_list(self, http_client: aiohttp.ClientSession):
        try:
            http_client.headers['Request-Time'] = str(int(time.time() * 1000))
            resp = await http_client.get("https://interface.carv.io/banana/get_quest_list", ssl=False)
            resp_json = await resp.json()
            quest_list = resp_json['data']['quest_list']
            for quest in quest_list:
                if quest['quest_type'] == u'telegram_join_group' or quest['quest_type'] == u'follow_on_twitter'\
                        or quest['quest_type'] == u'like_tweet' or quest['quest_type'] == u'retweet_tweet':
                    if quest['is_achieved'] and quest['is_claimed'] is not True:
                        await self.claim_quest(http_client=http_client, quest_id=quest['quest_id'])
                        self.success(f"claim : {quest['quest_name']}, peel: {quest['peel']}")
                        await asyncio.sleep(1)
                    elif quest['is_achieved'] is False:
                        if quest['quest_name'] not in settings.BLACKLIST_TASK:
                            if await self.achieve_quest(http_client=http_client, quest_id=quest['quest_id']):
                                self.success(f"achieve: {quest['quest_name']}")
                                await asyncio.sleep(random.randint(5, 15))
                            else:
                                self.warning(f"achieve failed: {quest['quest_name']}")
                                await asyncio.sleep(random.randint(5, 15))
        except Exception as e:
            self.error(f"get_quest_list error: {e}")

    async def claim_quest(self, http_client: aiohttp.ClientSession, quest_id: int):
        try:
            http_client.headers['Request-Time'] = str(int(time.time() * 1000))
            json_data = {"quest_id": quest_id}
            resp = await http_client.post("https://interface.carv.io/banana/claim_quest", json=json_data, ssl=False)
            resp_json = await resp.json()
            return resp_json['data']['peel']
        except Exception as e:
            self.error(f"claim_quest error: {e}")

    async def achieve_quest(self, http_client: aiohttp.ClientSession, quest_id: int):
        try:
            json_data = {"quest_id": quest_id}
            resp = await http_client.post("https://interface.carv.io/banana/achieve_quest", json=json_data, ssl=False)
            resp_json = await resp.json()
            return resp_json['data']['is_achieved']
        except Exception as e:
            self.error(f"achieve_quest error: {e}")

    async def claim_quest_lottery(self, http_client: aiohttp.ClientSession):
        try:
            http_client.headers['Request-Time'] = str(int(time.time() * 1000))
            resp = await http_client.get("https://interface.carv.io/banana/get_quest_list", ssl=False)
            resp_json = await resp.json()
            progress = resp_json['data']['progress']
            claim_size = int(progress.split('/')[0]) / int(progress.split('/')[1])
            if claim_size > 0:
                http_client.headers['Request-Time'] = str(int(time.time() * 1000))
                resp = await http_client.post("https://interface.carv.io/banana/claim_quest_lottery", json={}, ssl=False)
                resp_json = await resp.json()
                if resp_json['msg'] == u'Success':
                    self.success(f"Claim: {resp_json['msg']}")
                    await asyncio.sleep(1)
                    await self.claim_quest_lottery(http_client=http_client)

        except Exception as e:
            self.error(f"claim_quest_lottery error: {e}")

    async def run(self, proxy: str | None) -> None:
        access_token = None
        login_need = True

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        while True:
            try:
                if login_need:
                    if "Authorization" in http_client.headers:
                        del http_client.headers["Authorization"]

                    init_data = await self.get_tg_web_data(proxy=proxy)

                    http_client.headers['Request-Time'] = str(int(time.time() * 1000))
                    access_token, set_cookie, cookie = await self.login(http_client=http_client, initdata=init_data)

                    http_client.headers["Authorization"] = f"Bearer {access_token}"
                    # cookie.setdefault('banana-game:user:token', set_cookie.split('=')[1])
                    # http_client.cookie_jar.
                    # http_client.headers['cookie'] = cookie

                    if self.first_run is not True:
                        self.success("Logged in successfully")
                        self.first_run = True
                        login_need = False

                await self.get_user_info(http_client=http_client)

                await asyncio.sleep(60)

                await self.get_lottery_info(http_client=http_client)

                await asyncio.sleep(60)

                await self.get_quest_list(http_client=http_client)

                await asyncio.sleep(60)

                await self.claim_quest_lottery(http_client=http_client)

                await asyncio.sleep(60)

                try:
                    http_client.headers['Request-Time'] = str(int(time.time() * 1000))
                    resp = await http_client.get("https://interface.carv.io/banana/get_lottery_info", ssl=False)
                    resp_json = await resp.json()
                    if resp_json['data']['remain_lottery_count'] == 0:
                        countdown_interval = resp_json['data']['countdown_interval'] - (time.time() - (resp_json['data']['last_countdown_start_time'] / 1000)) / 60
                        self.info(f"Sleep {format_duration(countdown_interval * 60)}")
                        await asyncio.sleep(countdown_interval * 60)
                except Exception as e:
                    self.error(f"sleep error: {e}")

                await asyncio.sleep(60)

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Unknown error: {error}")
                await asyncio.sleep(delay=3)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        # 在创建Tapper实例之前添加随机休眠
        # if settings.SLEEP_BETWEEN_START:
        #     sleep_time = random.randint(settings.SLEEP_BETWEEN_START[0], settings.SLEEP_BETWEEN_START[1])
        #     logger.info(f"{tg_client.name} | Sleep for {sleep_time} seconds before starting session...")
        #     await asyncio.sleep(sleep_time)

        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
