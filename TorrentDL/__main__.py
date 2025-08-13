import re
import logging
import subprocess
import asyncio
from aiofiles import open as aiopen
from datetime import datetime
from pymongo import MongoClient
from os import path as ospath, execl, kill
from sys import executable
from signal import SIGKILL
from functools import partial, wraps
from asyncio import get_event_loop, gather
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.filters import command, user, private
from TorrentDL import bot, Var, LOGS, bot_loop, scheduler, folder_task_queue, folder_processing
from TorrentDL.helper.utils import is_aria2_running, start_aria2
from TorrentDL.core.func_utils import new_task, editMessage
from asyncio import create_task, create_subprocess_exec, create_subprocess_shell, run as asyrun, all_tasks, gather, sleep as asleep

from pyrogram import utils as pyroutils
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999

@bot.on_message(command('restart') & user(Var.ADMINS))
@new_task
async def restart(client, message):
    rmessage = await message.reply('<i>Restarting...</i>')
    async with aiopen(".restartmsg", "w") as f:
        await f.write(f"{rmessage.chat.id}\n{rmessage.id}\n")
    execl(executable, executable, "-m", "TeraBoxDownloader")
    
async def restart():
    if ospath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"<i>Restarted at {datetime.now().strftime('%H:%M:%S')}</i>")
        except Exception as e:
            LOGS.error(e)
                        
async def main():
        start_aria2()
        await bot.start() 
        await bot.set_bot_commands([
            BotCommand("start", "Check Bot Alive Status !"),
            BotCommand("folder", "Download TeraBox Folder Links.. !"),
            BotCommand("restart", "[ADMIN] Restart Bot.. !"),
        ])
        await restart()
        LOGS.info(r"""
        
███╗   ███╗██╗   ██╗███████╗████████╗███████╗██████╗ ██╗   ██╗    ██████╗ ███████╗███╗   ███╗ ██████╗ ███╗   ██╗
████╗ ████║╚██╗ ██╔╝██╔════╝╚══██╔══╝██╔════╝██╔══██╗╚██╗ ██╔╝    ██╔══██╗██╔════╝████╗ ████║██╔═══██╗████╗  ██║
██╔████╔██║ ╚████╔╝ ███████╗   ██║   █████╗  ██████╔╝ ╚████╔╝     ██║  ██║█████╗  ██╔████╔██║██║   ██║██╔██╗ ██║
██║╚██╔╝██║  ╚██╔╝  ╚════██║   ██║   ██╔══╝  ██╔══██╗  ╚██╔╝      ██║  ██║██╔══╝  ██║╚██╔╝██║██║   ██║██║╚██╗██║
██║ ╚═╝ ██║   ██║   ███████║   ██║   ███████╗██║  ██║   ██║       ██████╔╝███████╗██║ ╚═╝ ██║╚██████╔╝██║ ╚████║
╚═╝     ╚═╝   ╚═╝   ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝       ╚═════╝ ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
""")    
        LOGS.info(r"""
██████╗  ██████╗ ████████╗    ███████╗████████╗ █████╗ ██████╗ ████████╗███████╗██████╗ 
██╔══██╗██╔═══██╗╚══██╔══╝    ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝██╔════╝██╔══██╗
██████╔╝██║   ██║   ██║       ███████╗   ██║   ███████║██████╔╝   ██║   █████╗  ██║  ██║
██╔══██╗██║   ██║   ██║       ╚════██║   ██║   ██╔══██║██╔══██╗   ██║   ██╔══╝  ██║  ██║
██████╔╝╚██████╔╝   ██║       ███████║   ██║   ██║  ██║██║  ██║   ██║   ███████╗██████╔╝
╚═════╝  ╚═════╝    ╚═╝       ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══
""")
        await idle()
        LOGS.info('Stopping Bot...')
        await bot.stop()
        LOGS.info(r"""
██████╗  ██████╗ ████████╗    ███████╗████████╗ ██████╗ ██████╗ ██████╗ ███████╗██████╗ 
██╔══██╗██╔═══██╗╚══██╔══╝    ██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
██████╔╝██║   ██║   ██║       ███████╗   ██║   ██║   ██║██████╔╝██████╔╝█████╗  ██║  ██║
██╔══██╗██║   ██║   ██║       ╚════██║   ██║   ██║   ██║██╔═══╝ ██╔═══╝ ██╔══╝  ██║  ██║
██████╔╝╚██████╔╝   ██║       ███████║   ██║   ╚██████╔╝██║     ██║     ███████╗██████╔╝
╚═════╝  ╚═════╝    ╚═╝       ╚══════╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝     ╚══════╝╚═══
""")
    
if __name__ == "__main__":
    bot_loop.run_until_complete(main())
