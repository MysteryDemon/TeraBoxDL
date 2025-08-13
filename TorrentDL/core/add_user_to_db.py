from TeraBoxDownloader.core.database import db
from TeraBoxDownloader import Var
from pyrogram import Client
from pyrogram.types import Message

async def add_user_to_database(bot: Client, cmd: Message):
    if not await db.is_user_exist(cmd.from_user.id):
        await db.add_user(cmd.from_user.id)
        if Var.FSUB_LOG_CHANNEL is not None:
            bot_username = (await bot.get_me()).username
            await bot.send_message(
                int(Var.FSUB_LOG_CHANNEL),
                f"<b><blockquote>#NEW_USER: \n\nNew User <a href='tg://user?id={cmd.from_user.id}'>{cmd.from_user.first_name}</a> started @{bot_username} !!</blockquote></b>"
            )
            
