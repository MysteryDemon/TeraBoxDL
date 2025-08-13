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
from truelink import TrueLinkResolver
from TeraBoxDownloader import bot, Var, __version__, StartTime, LOGS, BUTTONS_PER_PAGE, VALID_DOMAINS, resolver, aria2, active_downloads, folder_processing_lock, user_folder_selections, folder_processing, folder_task_queue, download_lock, lock
from TeraBoxDownloader.core.database import db
from terabox import script
from TeraBoxDownloader.core.add_user_to_db import add_user_to_database
from TeraBoxDownloader.core.check_user_status import handle_user_status
from TeraBoxDownloader.core.broadcast import broadcast_messages, temp, get_readable_time
from TeraBoxDownloader.core.func_utils import is_fsubbed, get_fsubs, editMessage, sendMessage, new_task, is_valid_url, generate_buttons
from TeraBoxDownloader.helper.utils import wait_for_download, add_download, handle_download_and_send

@bot.on_message(command('start') & private)
@new_task
async def start_msg(client, message: Message):
    await add_user_to_database(client, message)
    uid = message.from_user.id
    from_user = message.from_user
    txtargs = message.text.split()
    temp_msg = await sendMessage(message, "<i>Connecting...</i>")
    
    if not await is_fsubbed(uid):
        txt, btns, fsub_pic = await get_fsubs(uid, txtargs)
        return await client.send_photo(chat_id=uid, photo=Var.START_PHOTO, caption=txt, reply_markup=InlineKeyboardMarkup(btns))
        
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
        
@bot.on_message(command('status') & private & user(Var.ADMINS))
@new_task
async def stats(client, message: Message):
    users = await db.total_users_count()
    await client.send_message(message.chat.id, f"𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀: {users}")

@bot.on_message(filters.command(["broadcast", "pin_broadcast"]) & user(Var.ADMINS) & filters.reply)
@new_task
async def users_broadcast(client, message: Message):
    if lock.locked():
        return await sendMessage(message, "Broadcast in progress, please wait.")
    pin = message.command[0] == "pin_broadcast"
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    b_sts = await sendMessage(message, "Starting broadcast...")
    total_users = await db.total_users_count()
    done, success, failed = 0, 0, 0
    start_time = time.time()

    async with lock:
        async for user in users:
            try:
                sts = await broadcast_messages(int(user['id']), b_msg, pin)
                if sts == "Success":
                    success += 1
                elif sts == "Error":
                    failed += 1
            except Exception:
                failed += 1
            done += 1
            if done % 20 == 0:
                time_taken = get_readable_time(time.time() - start_time)
                btn = [[InlineKeyboardButton("SUPPORT", url="https://t.me/+E90oYz68k-gxMmY0")]]
                await b_sts.edit_text(
                    f"Broadcast in progress...\n\nTotal Users: {total_users}\nCompleted: {done}/{total_users}\nSuccess: {success}",
                    reply_markup=InlineKeyboardMarkup(btn)
                )
        time_taken = get_readable_time(time.time() - start_time)
        await b_sts.edit_text(f"Broadcast completed in {time_taken}\n\nTotal Users: {total_users}\nSuccess: {success}\nFailed: {failed}")

@bot.on_callback_query(filters.regex("^(about|help|mysteryknull|gotohome)$"))
@new_task
async def set_cb(client, query: CallbackQuery):
    data = query.data
    if query.data == "mysteryknull":
        await query.answer("Admins Only !!!", show_alert=True)  
    elif data == "about":
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
        
@bot.on_message(filters.regex(r"https?://\S+") & ~filters.command(["folder", "start", "log", "status", "broadcast", "pin_broadcast"]))
@new_task
async def download_handler(_, message: Message):
    url = message.text.strip()
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]

    waiting_msg = await message.reply("<b>Added Link To Queue</b>")
    async with download_lock:
        try:
            if domain in VALID_DOMAINS:
                if not resolver.is_supported(url):
                    await waiting_msg.delete()
                    await message.reply("❌ Unsupported URL")
                    return

                await waiting_msg.edit_text("<b><i>Processing...</b></i>")
                await waiting_msg.delete()
                result = await resolver.resolve(url)
                if hasattr(result, "contents") and isinstance(result.contents, list):
                    await waiting_msg.delete()
                    await message.reply("Use /folder to download folder links")
                    return
                direct_url = getattr(result, "url", None)
                filename = getattr(result, "filename", None)
                if not filename:
                    filename = os.path.basename(parsed_url.path) or "output.file"
                headers = getattr(result, "headers", None)
                if direct_url:
                    output_path = os.path.abspath(os.path.join(Var.DOWNLOAD_DIR, filename))
                    download = add_download(direct_url, output_path, headers)
                    await handle_download_and_send(message, download, message.from_user.id, LOGS)
                else:
                    await message.reply("⚠️ Failed to extract direct URL from TeraBox TrueLink.")
            else:
                await waiting_msg.edit_text("<b><i>Processing...</b></i>")
                await waiting_msg.delete()
                filename = os.path.basename(parsed_url.path) or "output.file"
                output_path = os.path.abspath(os.path.join(Var.DOWNLOAD_DIR, filename))
                download = add_download(url, output_path, None)
                await handle_download_and_send(message, download, message.from_user.id, LOGS)
        except Exception as e:
            LOGS.exception(f"❌ Error processing {url}: {e}")
            await message.reply(f"❌ Error: {e}")
        finally:
            await waiting_msg.delete()

@bot.on_message(filters.regex(r"^/c_[a-fA-F0-9]+$"))
@new_task
async def cancel_download(client, message):
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

@bot.on_message(command('folder') & filters.private)
@new_task
async def folder_command_handler(client, message: Message):
    match = re.search(r'https?://\S+', message.text)
    if not match:
        return await message.reply("❌ No valid URL found. Usage: /folder <folder_link>")
    folder_link = match.group(0).strip()
    user_id = message.from_user.id
    from urllib.parse import urlparse
    parsed_url = urlparse(folder_link)
    domain = parsed_url.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    if domain not in VALID_DOMAINS:
        return await message.reply("❌ Only links from terabox are accepted.")
    if not resolver.is_supported(folder_link):
        return await message.reply("<b>❌ Unsupported folder link.</b>")
    waiting_msg = await message.reply("<b>Added Link To Queue</b>")
    await folder_processing_lock.acquire()
    try:
        await waiting_msg.edit("<b><i>Processing...</b></i>")
        result = await resolver.resolve(folder_link)
    except Exception as e:
        folder_processing_lock.release()
        await waiting_msg.delete()
        return await message.reply(f"<b>❌ Failed to resolve link: {e}</b>")
    if not hasattr(result, "contents") or not isinstance(result.contents, list) or not result.contents:
        folder_processing_lock.release()
        await waiting_msg.delete()
        return await message.reply("<b>❌ No files found in this folder.</b>")
    files = result.contents
    user_folder_selections[user_id] = {
        "files": files,
        "selected": set(),
        "message_id": None,
        "folder_link": folder_link,
        "page": 0,
        "lock": folder_processing_lock 
    }
    await waiting_msg.delete()
    await send_file_selection_ui(client, message, files, user_id)

async def send_file_selection_ui(client, message, files, user_id):
    user_folder_selections[user_id]["page"] = 0 
    await update_file_selection_ui(client, message, user_id)

@bot.on_callback_query()
@new_task
async def file_selection_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    if user_id not in user_folder_selections:
        await query.answer("No active selection found.", show_alert=True)
        return

    data = query.data
    state = user_folder_selections[user_id]
    files = state["files"]
    selected = state["selected"]
    page = state.get("page", 0)
    total_pages = (len(files) - 1) // BUTTONS_PER_PAGE + 1
    if data == "select_all":
        selected.clear()
        selected.update(range(len(files)))
    elif data == "cancel":
        await query.edit_message_text("❌.")
        await cleanup_selection_state(user_id)
        return
    elif data == "next_page":
        if page < total_pages - 1:
            state["page"] = page + 1
    elif data == "prev_page":
        if page > 0:
            state["page"] = page - 1
    elif data.startswith("select_"):
        idx_str = data.split("_", 1)[1]
        if idx_str.isdigit():
            idx = int(idx_str)
            if 0 <= idx < len(files):
                if idx in selected:
                    selected.remove(idx)
                else:
                    selected.add(idx)
            else:
                await query.answer("Invalid file index.", show_alert=True)
                return
        else:
            await query.answer("Invalid selection.", show_alert=True)
            return
    elif data == "done":
        if not selected:
            await query.answer("Select at least one file.", show_alert=True)
            return
        await query.answer("Starting downloads...", show_alert=False)
        try:
            await query.message.delete()
        except Exception as e:
            print(f"Failed to delete selection UI: {e}")
        await download_selected_files_sequentially(client, query.message, state, user_id)
        await cleanup_selection_state(user_id)
        lock = state.get("lock")
        if lock:
            lock.release()
        return
    else:
        await query.answer("Unknown action.", show_alert=True)
        return
        
    page = state.get("page", 0)
    start_idx = page * BUTTONS_PER_PAGE
    end_idx = min(start_idx + BUTTONS_PER_PAGE, len(files))
    new_buttons = []
    for idx in range(start_idx, end_idx):
        file = files[idx]
        fname = getattr(file, "filename", f"File {idx + 1}")
        sel_mark = "📌 " if idx in selected else ""
        new_buttons.append([InlineKeyboardButton(f"{sel_mark}{fname}", callback_data=f"select_{idx}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("<< 𝖯𝗋𝖾𝗏", callback_data="prev_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("𝖭𝖾𝗑𝗍 >>", callback_data="next_page"))
    action_buttons = [
        InlineKeyboardButton("𝖲𝖾𝗅𝖾𝖼𝗍 𝖠𝗅𝗅 📌", callback_data="select_all"),
        InlineKeyboardButton("𝖣𝗈𝗇𝖾 ✅", callback_data="done"),
        InlineKeyboardButton("𝖢𝖺𝗇𝖼𝖾𝗅 ✘", callback_data="cancel")
    ]
    if nav_buttons:
        new_buttons.append(nav_buttons)
    new_buttons.append(action_buttons)
    try:
        await query.edit_message_reply_markup(InlineKeyboardMarkup(new_buttons))
    except Exception as e:
        print(f"Failed to update selection UI: {e}")

async def cleanup_selection_state(user_id):
    if user_id in user_folder_selections:
        del user_folder_selections[user_id]

async def update_file_selection_ui(client, message, user_id):
    state = user_folder_selections[user_id]
    files = state["files"]
    selected = state["selected"]
    page = state.get("page", 0)
    total_pages = (len(files) - 1) // BUTTONS_PER_PAGE + 1
    start_idx = page * BUTTONS_PER_PAGE
    end_idx = min(start_idx + BUTTONS_PER_PAGE, len(files))
    new_buttons = []
    for idx in range(start_idx, end_idx):
        file = files[idx]
        fname = getattr(file, "filename", f"File {idx + 1}")
        sel_mark = "📌 " if idx in selected else ""
        new_buttons.append([InlineKeyboardButton(f"{sel_mark}{fname}", callback_data=f"select_{idx}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("<< 𝖯𝗋𝖾𝗏", callback_data="prev_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("𝖭𝖾𝗑𝗍 >>", callback_data="next_page"))
    action_buttons = [
        InlineKeyboardButton("𝖲𝖾𝗅𝖾𝖼𝗍 𝖠𝗅𝗅 📌", callback_data="select_all"),
        InlineKeyboardButton("𝖣𝗈𝗇𝖾 ✅", callback_data="done"),
        InlineKeyboardButton("𝖢𝖺𝗇𝖼𝖾𝗅 ✘", callback_data="cancel")
    ]
    if nav_buttons:
        new_buttons.append(nav_buttons)
    new_buttons.append(action_buttons)
    try:
        sent = await message.reply("<b>Select files to download:</b>", reply_markup=InlineKeyboardMarkup(new_buttons))
        state["selection_message"] = sent
        if selection_message:
            try:
                await selection_message.delete()
            except Exception as e:
                print(f"Failed to send selection UI: {e}")
    except Exception as e:
        print(f"Failed to update selection UI: {e}")
        
async def download_selected_files_sequentially(client, message, state, user_id):
    files = state["files"]
    selected = sorted(list(state["selected"]))
    folder_link = state["folder_link"]
    for idx in selected:
        file = files[idx]
        fname = getattr(file, "filename", f"File_{idx+1}")
        direct_url = getattr(file, "url", None)
        headers = getattr(file, "headers", None)
        if not direct_url:
            await client.send_message(user_id, f"<b>❌ Could not get direct URL for {fname}. Skipping.</b>")
            continue
        output_path = os.path.abspath(os.path.join(Var.DOWNLOAD_DIR, fname))
        try:
            download = add_download(direct_url, output_path, headers)
            await handle_download_and_send(message, download, user_id, LOGS)
        except Exception as e:
            await client.send_message(user_id, f"<b>❌ Error downloading {fname}: {e}</b>")
    selection_message = state.get("selection_message")
    if selection_message:
        try:
            await selection_message.delete()
        except Exception as e:
            print(f"Failed to delete selection message: {e}")
    task_msg = await client.send_message(user_id, "<b>✅ Task Complete.</b>")
    await task_msg.delete(3)
