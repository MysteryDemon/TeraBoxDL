import os
import aria2p
import asyncio
from time import time
from asyncio import Lock, new_event_loop, set_event_loop
from os import path as ospath, mkdir, system, getenv
from logging import INFO, ERROR, FileHandler, StreamHandler, basicConfig, getLogger
from traceback import format_exc
from asyncio import Queue, Lock
from asyncio import Semaphore, create_task, gather
from urllib.parse import urlparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client
from pyrogram.enums import ParseMode
from dotenv import load_dotenv
from uvloop import install

install()
basicConfig(format="[%(asctime)s] [%(name)s | %(levelname)s] - %(message)s [%(filename)s:%(lineno)d]",
            datefmt="%m/%d/%Y, %H:%M:%S %p",
            handlers=[FileHandler('log.txt'), StreamHandler()],
            level=INFO)

getLogger("pyrogram").setLevel(ERROR)
LOGS = getLogger(__name__)

active_downloads = {}
last_upload_update = {}
download_semaphore = Semaphore(5)
download_lock = Semaphore(1)
last_upload_update = {}
download_metadata_names = {}
last_upload_progress = {}
last_upload_speed = {}
lock = asyncio.Lock()
UPDATE_INTERVAL = 5 
MIN_PROGRESS_STEP = 15 
SPLIT_SIZE = 2 * 1024 * 1024 * 1024
BUTTONS_PER_PAGE = 12
__version__ = "2.33"
StartTime = time()
load_dotenv('torrentdl.env')

class Var:
    API_ID, API_HASH, BOT_TOKEN = getenv("API_ID"), getenv("API_HASH"), getenv("BOT_TOKEN")
    if not BOT_TOKEN or not API_HASH or not API_ID:
        LOGS.critical('Important Variables Missing. Fill Up and Retry..!! Exiting Now...')
        exit(1)
    LOG_CHANNEL = int(getenv("LOG_CHANNEL") or 0) 
    FSUB_LOG_CHANNEL = int(getenv("FSUB_LOG_CHANNEL") or LOG_CHANNEL or 0)  
    ADMINS = list(map(int, getenv("ADMINS", "1242011540").split()))
    START_PHOTO = getenv("START_PHOTO", "https://i.ibb.co/G4PtskS2/image.png")
    START_MSG = getenv("START_MSG", "<blockquote>𝖴𝗉𝗍𝗂𝗆𝖾: {uptime} <b>|</b> 𝖵𝖾𝗋𝗌𝗂𝗈𝗇: {version}</blockquote>\n<blockquote><b>Hey {first_name}</b>\n\n<b>𝗂 𝖺𝗆 𝖺 𝗍𝖾𝗋𝖺𝖻𝗈𝗑 𝖽𝗈𝗐𝗇𝗅𝗈𝖺𝖽𝖾𝗋 𝖻𝗈𝗍. 𝗌𝖾𝗇𝖽 𝗆𝖾 𝖺𝗇𝗒 𝗍𝖾𝗋𝖺𝖻𝗈𝗑 𝗅𝗂𝗇𝗄 𝖺𝗇𝖽 𝗂 𝗐𝗂𝗅𝗅 𝖽𝗈𝗐𝗇𝗅𝗈𝖺𝖽 𝗂𝗍 𝗐𝗂𝗍𝗁𝗂𝗇 𝖺 𝖿𝖾𝗐 𝗌𝖾𝖼𝗈𝗇𝖽𝗌 𝖺𝗇𝖽 𝗌𝖾𝗇𝖽 𝗂𝗍 𝗍𝗈 𝗒𝗈𝗎</b></blockquote>")
    START_BUTTONS = getenv("START_BUTTONS", "UPDATES|https://t.me/BotClusters SUPPORT|https://t.me/+E90oYz68k-gxMmY0\n ABOUT|about HELP|help")
    ARIA2_SECRET = getenv("ARIA2_SECRET", "F91D6A347E9B0ACFA517CC0AB634E2F4F68891E90ADAD3CE57F26EC99B18E6CFB2172C6")
    DOWNLOAD_DIR = getenv("DOWNLOAD_DIR", "downloads")  
            
try:
    aria2 = aria2p.API(
        aria2p.Client(
            host="http://localhost",
            port=6800,
            secret=Var.ARIA2_SECRET
        )
    )
            
    bot_loop = new_event_loop()
    set_event_loop(bot_loop)
    bot = Client(
        name="TeraBoxDownloader",
        api_id=Var.API_ID,
        api_hash=Var.API_HASH,
        bot_token=Var.BOT_TOKEN,
        plugins=dict(root="TorrentDL/modules"),
        parse_mode=ParseMode.HTML,
        workers=300
    )
            
    scheduler = AsyncIOScheduler(event_loop=bot_loop)
except Exception as ee:
    LOGS.error("Initialization error: %s", str(ee))
    exit(1)
