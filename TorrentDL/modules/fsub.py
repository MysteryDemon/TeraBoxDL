import re
import asyncio
from pyrogram.filters import command, private, user
from TeraBoxDownloader import bot, Var
from TeraBoxDownloader.core.func_utils import editMessage, sendMessage, new_task
from pymongo import MongoClient

mongo_client = MongoClient(Var.MONGO_URI)
db = mongo_client[Var.DB_NAME] 
channels_collection = db["channels"]

CHANNEL_ID_PATTERN = re.compile(r"^-100\d{10}$")
    
@bot.on_message(command('addchannel') & private & user(Var.ADMINS))
@new_task
async def add_channel(client, message):
    args = message.text.split()
    if len(args) <= 1:
        return await sendMessage(message, "<b>No Channel ID Found to Add</b>")

    added_channels = []
    already_added_channels = []
    invalid_channels = []

    for channel_id in args[1:]:
        if CHANNEL_ID_PATTERN.match(channel_id):
            existing_channel = channels_collection.find_one({"channel_id": channel_id})
            if existing_channel:
                already_added_channels.append(channel_id)
                continue 

            try:
                chat = await client.get_chat(int(channel_id))
                channel_data = {
                    "channel_id": channel_id,
                    "title": chat.title,
                }
                channels_collection.update_one(
                    {"channel_id": channel_id},
                    {"$set": channel_data},
                    upsert=True,
                )
                Var.FSUB_CHATS.append(channel_id)
                channel_info = f"<blockquote><b>‣ {chat.title} (ID: {channel_id})</b></blockquote>"
                added_channels.append(channel_info)
            except Exception as e:
                invalid_channels.append(channel_id)
        else:
            invalid_channels.append(channel_id)
            
    confirmation_msg = "<blockquote><b>𝗦𝘁𝗮𝘁𝘂𝘀:</b></blockquote>\n\n"
    if added_channels:
        confirmation_msg += f"<blockquote><b>• Added Channel(s):\n{chr(10).join(added_channels)}</b></blockquote>\n"
    if already_added_channels:
        confirmation_msg += (
            f"<blockquote><b>• Already Added Channel(s): {', '.join(already_added_channels)}</b></blockquote>\n"
        )
    if invalid_channels:
        confirmation_msg += f"<blockquote><b>• Invalid Channel ID(s): {', '.join(invalid_channels)}</b></blockquote>"
    await sendMessage(message, confirmation_msg)
    

@bot.on_message(command('remchannel') & private & user(Var.ADMINS))
@new_task
async def remove_channel(client, message):
    args = message.text.split()
    if len(args) <= 1:
        return await sendMessage(message, "<b>No Channel ID Found to Remove</b>")
    
    removed_channels = []
    not_found_channels = []
    invalid_channels = []

    for channel_id in args[1:]:
        if CHANNEL_ID_PATTERN.match(channel_id):
            try:
                channel = channels_collection.find_one({"channel_id": channel_id})
                if channel:
                    channel_name = channel.get("title", "Unknown Channel")
                    
                    result = channels_collection.delete_one({"channel_id": channel_id})
                    if result.deleted_count > 0:
                        if channel_id in Var.FSUB_CHATS:
                            Var.FSUB_CHATS.remove(channel_id) 
                        removed_channels.append(f"{channel_name} (ID: {channel_id})")
                    else:
                        not_found_channels.append(channel_id)
                else:
                    not_found_channels.append(channel_id)
            except Exception as e:
                not_found_channels.append(channel_id)
        else:
            invalid_channels.append(channel_id)

    confirmation_msg = "<blockquote><b>𝗦𝘁𝗮𝘁𝘂𝘀:</b></blockquote>\n\n"
    if removed_channels:
        confirmation_msg += f"<blockquote><b>• Removed Channel(s): {', '.join(removed_channels)}</b></blockquote>\n"
    if not_found_channels:
        confirmation_msg += f"<blockquote><b>• Not Found in Database: {', '.join(not_found_channels)}</b></blockquote>\n"
    if invalid_channels:
        confirmation_msg += f"<blockquote><b>• Invalid Channel ID(s): {', '.join(invalid_channels)}</b></blockquote>"

    await sendMessage(message, confirmation_msg)

async def load_channels():
    channels = channels_collection.find()
    valid_channels = []
    invalid_channels = []

    for channel in channels:
        channel_id = channel.get("channel_id", "")
        if CHANNEL_ID_PATTERN.match(channel_id):
            try:
                await bot.get_chat(int(channel_id))
                valid_channels.append(channel_id)
            except Exception as e:
                invalid_channels.append(channel_id)
        else:
            invalid_channels.append(channel_id)

    Var.FSUB_CHATS = valid_channels
    for invalid_channel_id in invalid_channels:
        channels_collection.delete_one({"channel_id": invalid_channel_id})

    print(f"Loaded {len(valid_channels)} valid channels from MongoDB.")
    if invalid_channels:
        print(f"Removed {len(invalid_channels)} invalid channels: {invalid_channels}")

@bot.on_message(command('getchannels') & private)
@new_task
async def get_channels(client, message):
    if not Var.FSUB_CHATS:
        return await sendMessage(message, "<b>No channels have been added yet.</b>")
    btns = []
    for channel_id in Var.FSUB_CHATS:
        try:
            chat = await client.get_chat(channel_id)
            try:
                invite_link = await client.export_chat_invite_link(channel_id)
            except Exception:
                invite_link = None
                
            if invite_link:
                btns.append([InlineKeyboardButton(text=chat.title, url=invite_link)])
            else:
                btns.append([InlineKeyboardButton(text=f"{chat.title} (No link)", url="https://t.me")])
        except Exception as e:
            btns.append([InlineKeyboardButton(text="Error fetching channel", url="https://t.me")])

    channel_info = f"<b>List of Force Sub Channels:</b>"
    channels_pic = Var.START_PHOTO
    await message.reply_photo(photo=channels_pic, caption=channel_info, reply_markup=InlineKeyboardMarkup(btns))


