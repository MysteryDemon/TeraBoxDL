import re
import os
import psutil
import aria2p
import time
import asyncio
from pyrogram.filters import command, private, user, create
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from pyrogram import Client, filters
from urllib.parse import urlparse
from pyrogram import __version__ as pyroversion
from TorrentDL import bot, Var, __version__, StartTime, LOGS, BUTTONS_PER_PAGE, aria2, active_downloads, download_lock, lock
from torrentdl import script
from TorrentDL.core.func_utils import editMessage, sendMessage, new_task, is_valid_url, generate_buttons, get_readable_time
from TorrentDL.helper.utils import wait_for_download, add_download, handle_download_and_send, start_aria2
from TorrentDL.helper.mediainfo import srm, gen_mediainfo

def admin_only(_, __, message):
    return message.from_user.id in Var.ADMINS

@bot.on_message(command('start') & filters.private & filters.create(admin_only))
@new_task
async def start_msg(client, message: Message):
    uid = message.from_user.id
    from_user = message.from_user
    txtargs = message.text.split()
    temp_msg = await sendMessage(message, "<i>Connecting...</i>")
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

    smsg = Var.START_MSG.format(
        uptime=get_readable_time(time.time() - StartTime), 
        version=__version__,
        first_name=from_user.first_name,
        last_name=from_user.last_name,
        mention=from_user.mention, 
        user_id=from_user.id
    )
    
    if Var.START_PHOTO:
        await message.reply_photo(
            photo=Var.START_PHOTO,
            caption=smsg,
            reply_markup=InlineKeyboardMarkup(btns) if btns else None
        )
    else:
        await sendMessage(message, smsg, InlineKeyboardMarkup(btns) if btns else None)
    await temp_msg.delete()

@bot.on_message(command('log') & private & user(Var.ADMINS))
@new_task
async def _log(client, message: Message):
    try:
        await message.reply_document("log.txt", quote=True)
    except FileNotFoundError:
        await sendMessage(message, "<b>No log file found.</b>")

@bot.on_callback_query(filters.regex("^(about|help|gotohome)$"))
@new_task
async def set_cb(client, query: CallbackQuery):
    data = query.data 
    if data == "about":
        await query.message.edit_text(
            text=script.ABOUT_TXT,
            reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("DEVELOPER", url="https://t.me/MysteryDemon"), InlineKeyboardButton("BACK", callback_data="gotohome")]]))
    elif data == "help":
        await query.message.edit_text(
            text=script.HELP_TXT,
            reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("REPORT BUGS", url="https://t.me/velsvalt"), InlineKeyboardButton("BACK", callback_data="gotohome")]]))
    elif data == "gotohome":
        await query.message.edit_text(
            text=Var.START_MSG.format(
            uptime=get_readable_time(time.time() - StartTime), 
            version=__version__,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name,
            mention=query.from_user.mention, 
            user_id=query.from_user.id),
            reply_markup=InlineKeyboardMarkup(await generate_buttons()))

@bot.on_message(filters.command(["mi", "mediainfo"]) & filters.create(admin_only))
async def mediainfo(client, message):
    rply = message.reply_to_message
    help_msg = "<b>By replying to media:</b>"
    help_msg += f"\n<code>/mi or /mediainfo" + " {media}" + "</code>"
    help_msg += "\n\n<b>By reply/sending download link:</b>"
    help_msg += f"\n<code>/mi or /mediainfo" + " {link}" + "</code>"
    if len(message.command) > 1 or rply and rply.text:
        link = rply.text if rply else message.command[1]
        return await gen_mediainfo(client, message, link)
    elif rply:
        if file := next(
            (
                i
                for i in [rply.document, rply.video, rply.audio, rply.voice, rply.animation, rply.video_note,
                ]
                if i is not None
            ),
            None,
        ):
            return await gen_mediainfo(client, message, None, file, rply)
        else:
            return await srm(client, message, help_msg)
    else:
        return await srm(client, message, help_msg)

@bot.on_message(
    filters.regex(r"(https?://\S+|magnet:\?xt=urn:btih:[a-fA-F0-9]+)") &
    ~filters.command(["start", "log"]) &
    filters.create(admin_only)
)
@new_task
async def download_handler(_, message: Message):
    url = message.text.strip()
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path) or "output.file"
    output_path = os.path.abspath(os.path.join(Var.DOWNLOAD_DIR, filename))
    async with download_lock:
        try:
            download = add_download(url, output_path, headers=None)
            await handle_download_and_send(message, download, message.from_user.id, LOGS)
        except Exception as e:
            LOGS.exception(f"❌ Error processing {url}: {e}")
            await message.reply(f"❌ Error: {e}")

@bot.on_message(filters.regex(r"^/c_[a-fA-F0-9]+$"))
@new_task
async def cancel_download(client, message: Message):
    cmd = message.text.strip()
    download_id = cmd[3:]
    download_data = active_downloads.get(download_id)
    if download_data:
        download = download_data.get("download")
        status_message = download_data.get("status_message")
        try:
            download.remove(force=True)
            cancel_message = await message.reply("🛑 Download canceled!")
            await cancel_message.delete()
            if status_message:
                try:
                    await status_message.delete()
                except Exception as e:
                    await message.reply(f"⚠️ Failed to delete status message: {e}")
        except Exception as e:
            await message.reply(f"<b>❌ Failed to cancel: {e}</b>")
        del active_downloads[download_id]
    else:
        await message.reply("<b>❌ No active download with this ID.</b>")
