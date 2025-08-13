import asyncio
import datetime
from pyrogram import Client
from pyrogram.types import Message
from TorrentDL import bot, Var
from TorrentDL.core.database import db

async def handle_user_status(bot, cmd):
    chat_id = cmd.from_user.id
    if not await db.is_user_exist(chat_id):
        await db.add_user(chat_id)
        if Var.FSUB_LOG_CHANNEL is not None:
            bot_username = (await bot.get_me()).username
            await bot.send_message(
                int(Var.FSUB_LOG_CHANNEL),
                f"<b><blockquote>#NEW_USER: \n\nNew User <a href='tg://user?id={cmd.from_user.id}'>{cmd.from_user.first_name}</a> started @{bot_username} !!</blockquote></b>"
            )
