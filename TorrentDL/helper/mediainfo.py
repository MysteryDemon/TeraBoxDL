import asyncio
from asyncio.subprocess import PIPE
from aiohttp import ClientSession
from re import search as re_search
from shlex import split as ssplit
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, path as aiopath, mkdir
from os import path as ospath, getcwd
from string import ascii_letters
from random import SystemRandom
from telegraph.aio import Telegraph
from telegraph.exceptions import RetryAfterError
from asyncio import create_subprocess_exec, create_subprocess_shell
from pyrogram.handlers import MessageHandler 
from pyrogram.filters import command
from pyrogram import Client, filters, enums
from TorrentDL import bot
from TorrentDL import LOGS as LOGGER

class TelegraphHelper:
    def __init__(self):
        self.telegraph = Telegraph(domain='graph.org')
        self.short_name = ''.join(SystemRandom().choices(ascii_letters, k=8))
        self.access_token = None
        self.author_name = "MysteryDemon"
        self.author_url = "https://github.com/MysteryDemon"

    async def create_account(self):
        await self.telegraph.create_account(
            short_name=self.short_name,
            author_name=self.author_name,
            author_url=self.author_url
        )
        self.access_token = self.telegraph.get_access_token()
        LOGGER.info(f"Telegraph Account Generated : {self.short_name}")

    async def create_page(self, title, content):
        try:
            return await self.telegraph.create_page(
                title=title,
                author_name=self.author_name,
                author_url=self.author_url,
                html_content=content
            )
        except RetryAfterError as st:
            LOGGER.warning(f'Telegraph Flood control exceeded. I will sleep for {st.retry_after} seconds.')
            await sleep(st.retry_after)
            return await self.create_page(title, content)

    async def edit_page(self, path, title, content):
        try:
            return await self.telegraph.edit_page(
                path=path,
                title=title,
                author_name=self.author_name,
                author_url=self.author_url,
                html_content=content
            )
        except RetryAfterError as st:
            LOGGER.warning(f'Telegraph Flood control exceeded. I will sleep for {st.retry_after} seconds.')
            await sleep(st.retry_after)
            return await self.edit_page(path, title, content)

    async def edit_telegraph(self, path, telegraph_content):
        nxt_page = 1
        prev_page = 0
        num_of_path = len(path)
        for content in telegraph_content:
            if nxt_page == 1:
                content += f'<b><a href="https://telegra.ph/{path[nxt_page]}">Next</a></b>'
                nxt_page += 1
            else:
                if prev_page <= num_of_path:
                    content += f'<b><a href="https://telegra.ph/{path[prev_page]}">Prev</a></b>'
                    prev_page += 1
                if nxt_page < num_of_path:
                    content += f'<b> | <a href="https://telegra.ph/{path[nxt_page]}">Next</a></b>'
                    nxt_page += 1
            await self.edit_page(
                path=path[prev_page],
                title=f"{config_dict['TITLE_NAME']} Torrent Search",
                content=content
            )
        return

async def gen_mediainfo(client, message, link=None, media=None, mmsg=None):
    temp_send = await client.send_message(chat_id=message.chat.id, text='<b>Generating MediaInfo...</b>', reply_to_message_id=message.id, disable_web_page_preview=False)
    try:
        path = "Mediainfo/"
        if not await aiopath.isdir(path):
            await mkdir(path)
        if link:
            filename = re_search(".+/(.+)", link).group(1)
            des_path = ospath.join(path, filename)
            headers = {"user-agent":"Mozilla/5.0 (Linux; Android 12; 2201116PI) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36"}
            async with ClientSession() as session:
                async with session.get(link, headers=headers) as response:
                    async with aiopen(des_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(10000000):
                            await f.write(chunk)
                            break
        elif media:
            des_path = ospath.join(path, media.file_name)
            if media.file_size <= 50000000:
                await mmsg.download(ospath.join(getcwd(), des_path))
            else:
                async for chunk in bot.stream_media(media, limit=5):
                    async with aiopen(des_path, "ab") as f:
                        await f.write(chunk)
        stdout, _, _ = await cmd_exec(ssplit(f'mediainfo "{des_path}"'))
        tc = f"<h4>📌 {ospath.basename(des_path)}</h4><br><br>"
        if len(stdout) != 0:
            tc += parseinfo(stdout)
    except Exception as e:
        LOGGER.error(e, exc_info=True)
        await temp_send.edit(f"MediaInfo Stopped due to {str(e)}")
    finally:
        await aioremove(des_path)
    link_id = (await telegraph.create_page(title='MediaInfo X', content=tc))["path"]
    await temp_send.edit(f"<b>MediaInfo:</b>\n\n➲ <b>Link :</b> https://graph.org/{link_id}", disable_web_page_preview=False)

section_dict = {'General': '🗒', 'Video': '🎞', 'Audio': '🔊', 'Text': '🔠', 'Menu': '🗃'}
def parseinfo(out):
    tc = ''
    trigger = False
    for line in out.split('\n'):
        for section, emoji in section_dict.items():
            if line.startswith(section):
                trigger = True
                if not line.startswith('General'):
                    tc += '</pre><br>'
                tc += f"<h4>{emoji} {line.replace('Text', 'Subtitle')}</h4>"
                break
        if trigger:
            tc += '<br><pre>'
            trigger = False
        else:
            tc += line + '\n'
    tc += '</pre><br>'
    return tc

async def cmd_exec(cmd, shell=False):
    if shell:
        proc = await create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)
    else:
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await proc.communicate()
    stdout = stdout.decode().strip()
    stderr = stderr.decode().strip()
    LOGGER.info(f'Out :- {stdout}\nError :- {stderr}')
    return stdout, stderr, proc.returncode

async def srm(c, m, text, photo=None, video=None, markup=None, reply_id=None, delete=20, **kwargs):
 try:
   replyid = reply_id if reply_id else m.id
   mid = m.message.id if hasattr(m, 'message') else replyid
   tosend = m.message.chat.id if hasattr(m, 'message') else m.chat.id
   if photo:
      my = await c.send_photo(
          chat_id=tosend,
          photo=photo,
          caption=text,
          reply_to_message_id=mid,
          reply_markup=markup,
          **kwargs
      )
   elif video:
       pass
       
   else:
       my = await c.send_message(
          chat_id=tosend,
          text=text,
          reply_to_message_id=mid,
          reply_markup=markup,
          **kwargs
      )
   if delete:
      await delete_msg([my, m], dt=delete)
   return my
 except:
   LOGGER.error('srm', exc_info=True)

telegraph = TelegraphHelper()
