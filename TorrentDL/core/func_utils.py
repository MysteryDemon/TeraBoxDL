from urllib.parse import urlparse
from multiprocessing import cpu_count
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps
from re import findall
from math import floor
from os import path as ospath
from time import time, sleep
from traceback import format_exc
from asyncio import sleep as asleep, create_subprocess_shell
from asyncio.subprocess import PIPE

from aiohttp import ClientSession
from aiofiles import open as aiopen
from aioshutil import rmtree as aiormtree
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton
from pyrogram.errors import MessageNotModified, FloodWait, UserNotParticipant, ReplyMarkupInvalid, MessageIdInvalid

from TeraBoxDownloader import bot, bot_loop, LOGS, Var
from .reporter import rep

def handle_logs(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception:
            await rep.report(format_exc(), "error")
    return wrapper
    
async def sync_to_async(func, *args, wait=True, **kwargs):
    pfunc = partial(func, *args, **kwargs)
    future = bot_loop.run_in_executor(ThreadPoolExecutor(max_workers=cpu_count() * 125), pfunc)
    return await future if wait else future
    
def new_task(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return bot_loop.create_task(func(*args, **kwargs))
    return wrapper

def is_valid_url(url):
    """Helper function to check if the link is a valid URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

async def sendMessage(chat, text, buttons=None, get_error=False, **kwargs):
    try:
        if isinstance(chat, int):
            return await bot.send_message(chat_id=chat, text=text, disable_web_page_preview=True,
                                        disable_notification=False, reply_markup=buttons, **kwargs)
        else:
            return await chat.reply(text=text, quote=True, disable_web_page_preview=True, disable_notification=False,
                                    reply_markup=buttons, **kwargs)
    except FloodWait as f:
        await rep.report(f, "warning")
        sleep(f.value * 1.2)
        return await sendMessage(chat, text, buttons, get_error, **kwargs)
    except ReplyMarkupInvalid:
        return await sendMessage(chat, text, None, get_error, **kwargs)
    except Exception as e:
        await rep.report(format_exc(), "error")
        if get_error:
            raise e
        return str(e)
        
async def editMessage(msg, text, buttons=None, get_error=False, **kwargs):
    try:
        if not msg:
            return None
        return await msg.edit_text(text=text, disable_web_page_preview=True, 
                                        reply_markup=buttons, **kwargs)
    except FloodWait as f:
        await rep.report(f, "warning")
        sleep(f.value * 1.2)
        return await editMessage(msg, text, buttons, get_error, **kwargs)
    except ReplyMarkupInvalid:
        return await editMessage(msg, text, None, get_error, **kwargs)
    except (MessageNotModified, MessageIdInvalid):
        pass
    except Exception as e:
        await rep.report(format_exc(), "error")
        if get_error:
            raise e
        return str(e)

async def is_fsubbed(uid):
    if len(Var.FSUB_CHATS) == 0:
        return True
    for chat_id in Var.FSUB_CHATS:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=uid)
        except UserNotParticipant:
            return False
        except Exception as err:
            await rep.report(format_exc(), "warning")
            continue
    return True
        
async def get_fsubs(uid, txtargs):
    txt = "<blockquote><b>Please Join Following Channels to Use this Bot!</b></blockquote>\n\n"
    btns = []
    fsub_pic = Var.START_PHOTO
    for no, chat in enumerate(Var.FSUB_CHATS, start=1):
        try:
            cha = await bot.get_chat(chat)
            member = await bot.get_chat_member(chat_id=chat, user_id=uid)
            sta = "Joined ✅️"
        except UserNotParticipant:
            sta = "Not Joined ❌️"
            inv = await bot.create_chat_invite_link(chat_id=chat)
            btns.append([InlineKeyboardButton(cha.title, url=inv.invite_link)])
        except Exception as err:
            await rep.report(format_exc(), "warning")
            continue
        txt += f"<b>{no}. Title :</b> <i>{cha.title}</i>\n  <b>Status :</b> <i>{sta}</i>\n\n"
    if len(txtargs) > 1:
        return txt, btns, fsub_pic
        
async def generate_buttons():
    btns = []
    if Var.START_BUTTONS:
        for elem in Var.START_BUTTONS.split():
            try:
                bt, link = elem.split('|', maxsplit=1)
            except ValueError:
                continue
            if is_valid_url(link):
                button = InlineKeyboardButton(bt, url=link)
            else:
                button = InlineKeyboardButton(bt, callback_data=link)
            if btns and len(btns[-1]) == 1:
                btns[-1].append(button)
            else:
                btns.append([button]) 
    return btns
                

def convertTime(s: int) -> str:
    m, s = divmod(int(s), 60)
    hr, m = divmod(m, 60)
    days, hr = divmod(hr, 24)
    convertedTime = (f"{int(days)}d, " if days else "") + \
          (f"{int(hr)}h, " if hr else "") + \
          (f"{int(m)}m, " if m else "") + \
          (f"{int(s)}s, " if s else "")
    return convertedTime[:-2]

def convertBytes(sz) -> str:
    if not sz: 
        return ""
    sz = int(sz)
    ind = 0
    Units = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T', 5: 'P'}
    while sz > 2**10:
        sz /= 2**10
        ind += 1
    return f"{round(sz, 2)} {Units[ind]}B"
