from TorrentDL import LOGS, UPDATE_INTERVAL, MIN_PROGRESS_STEP, SPLIT_SIZE, Var, aria2, active_downloads, last_upload_update, last_upload_update, last_upload_progress, last_upload_speed
from pyrogram import Client, filters
from pyrogram.types import Message
from datetime import datetime
from threading import Thread
import subprocess
import asyncio
import aria2p
import psutil
import time
import uuid
import os
import math

def is_aria2_running():
    for proc in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            name = proc.info.get("name") or ""
            cmdline = proc.info.get("cmdline") or []
            if "aria2c" in name or any("aria2c" in str(cmd) for cmd in cmdline):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    return False

def stream_aria2_logs(process):
    for line in process.stdout:
        LOGS.info(f"[aria2c] {line.decode().strip()}")

def generate_download_id():
    return uuid.uuid4().hex[:16]

def start_aria2():
    if not is_aria2_running():
        LOGS.info("🔄 Starting aria2c with logging...")
        process = subprocess.Popen(
            [
                "aria2c",
                "--enable-rpc=true",
                f"--rpc-secret={Var.ARIA2_SECRET}",
                "--rpc-listen-all=true",
                "--rpc-listen-port=6800",
                "--disable-ipv6",
                "--max-connection-per-server=16",
                "--rpc-allow-origin-all=true",
                "--force-sequential",
                "--allow-overwrite=true",
                "--continue=false",
                "--daemon=false",
                "--console-log-level=notice",
                "--summary-interval=1"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        Thread(target=stream_aria2_logs, args=(process,), daemon=True).start()
        time.sleep(2)
    else:
        LOGS.info("ℹ️ aria2c is already running.")

def add_download(url: str, output_path: str, headers: dict = None):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    options = {
        "dir": os.path.dirname(output_path),
        "out": os.path.basename(output_path),
        "split": "16",
        "max-connection-per-server": "16",
        "min-split-size": "1M",
        "enable-http-pipelining": "true",
        "auto-file-renaming": "false",
        "allow-overwrite": "true",
    }
    if headers:
        options["header"] = [f"{k}: {v}" for k, v in headers.items()]
    download = aria2.add_uris([url], options=options)
    LOGS.info(f"Added to aria2: {output_path}")
    return download

async def wait_for_download(download):
    while download.is_active:
        await asyncio.sleep(2)
        try:
            download.update()
        except Exception as e:
            if "is not found" in str(e):
                LOGS.info(f"Download was cancelled: {download.gid}")
                break
            else:
                raise
    try:
        download.update()
    except Exception as e:
        if "is not found" in str(e):
            LOGS.info(f"Download was cancelled: {download.gid}")
        else:
            raise
    return download

async def update_status_message(status_message, text):
    try:
        await status_message.edit_text(text)
    except Exception as e:
        LOGS.error(f"Failed to update status message: {e}")

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

async def handle_download_and_send(message, download, user_id, LOGS, status_message=None):
    status_message = await message.reply_text("<b><i>Downloading...</b></i>")
    start_time = datetime.now()
    download_id = uuid.uuid4().hex
    active_downloads[download_id] = {
        "download": download,
        "status_message": status_message,
        "cancelled": False
    }

    while not download.is_complete:
        if active_downloads[download_id].get("cancelled"):
            LOGS.info(f"Download cancelled for ID: {download_id}")
            break

        await asyncio.sleep(15)
        try:
            download.update()
        except Exception as e:
            if "is not found" in str(e):
                LOGS.info(f"Download was cancelled or removed: {download.gid}")
                break
            else:
                LOGS.error(f"Error updating download: {e}")
                break

        progress = download.progress
        elapsed_time = datetime.now() - start_time
        elapsed_minutes, elapsed_seconds = divmod(elapsed_time.seconds, 60)
        if hasattr(download, "eta") and download.eta:
            eta_seconds = download.eta.total_seconds() if hasattr(download.eta, "total_seconds") else float(download.eta)
            eta_seconds = max(0, int(eta_seconds))
        else:
            eta_seconds = 0
        eta_min, eta_sec = divmod(int(eta_seconds), 60)
        speed = download.download_speed if hasattr(download, "download_speed") else 0
        remaining_seconds = max(0, int(eta_seconds))
        bar_length = 12
        filled_slots = int(progress / (100 / bar_length))
        status_bar = f"{'⬢' * filled_slots}{'⬡' * (bar_length - filled_slots)}"
        status_text = (
            f"<i><b>{download.name}</b></i>\n\n"
            f"<b>Task By {message.from_user.first_name}</b>  ( #ID{user_id} )\n"
            f"┟ [{status_bar}] {progress:.2f}%\n"
            f"┠ <b>Processed</b> → <i>{format_size(download.completed_length)} of {format_size(download.total_length)}</i>\n"
            f"┠ <b>Status</b> → <b>Download</b>\n"
            f"┠ <b>Speed</b> → <i>{format_size(speed)}</i>/s\n"
            f"┠ <b>Time</b> → <i>{elapsed_minutes}m{elapsed_seconds}s of {eta_min}m{eta_sec}s ({remaining_seconds}s left)</i>\n"
            f"┠ <b>Engine</b> → <i>Aria2 v1.37.0</i>\n"
            f"┖ <b>Stop</b> → <i>/c_{download_id}</i>\n"
        )
        while True:
            try:
                await update_status_message(status_message, status_text)
                break
            except Exception as e:
                if type(e).__name__ == "FloodWait":
                    LOGS.error(f"Flood wait detected! Sleeping for {e.value} seconds")
                    await asyncio.sleep(e.value)
                else:
                    LOGS.error(f"Failed to update status message: {e}")
                    break

    completed = download
    try:
        completed.update()
    except Exception as e:
        if "is not found" in str(e):
            LOGS.info(f"Download was cancelled or removed: {completed.gid}")
            return
        else:
            LOGS.error(f"Error updating completed download: {e}")
            await message.reply(f"❌ Error updating download: {e}")
            return
            
    file_path = completed.files[0].path if completed.files else None
    elapsed_time = datetime.now() - start_time
    elapsed_minutes, elapsed_seconds = divmod(elapsed_time.seconds, 60)
    status_text = (
        f"<i><b>{download.name}</b></i>\n\n"
        f"<b>Task By {message.from_user.first_name}</b>  ( #ID{user_id} )\n"
        f"┠ <b>Status</b> → Completed\n"
        f"┠ <b>Time Taken</b> → {elapsed_minutes}m{elapsed_seconds}s\n"
        f"┖ <b>Engine</b> → Aria2 v1.37.0\n"
    )
    await update_status_message(status_message, status_text)
    if not file_path or not os.path.exists(file_path):
        await message.reply(f"❌ File not found: {file_path}")
        return

    file_size = os.path.getsize(file_path)
    caption = f"<b>{download.name}</b>\n"
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in [".mp4", ".mkv", ".mov", ".avi"]:
            if file_size > SPLIT_SIZE:
                split_files = await split_video_with_ffmpeg(file_path, os.path.splitext(file_path)[0], SPLIT_SIZE)
                for i, part in enumerate(split_files):
                    part_caption = f"{caption}\n\nPart {i+1}/{len(split_files)}"
                    upload_id = uuid.uuid4().hex
                    msg = await message.reply_document(
                        part,
                        caption=part_caption,
                        progress=upload_progress,
                        progress_args=(status_message, download.name, message.from_user.first_name, user_id, upload_id)
                    )
                    await message._client.send_document(Var.LOG_CHANNEL, msg.document.file_id, caption=part_caption)
                    os.remove(part)
            else:
                upload_id = uuid.uuid4().hex
                part_caption = caption
                msg = await message.reply_document(
                    file_path,
                    caption=caption,
                    progress=upload_progress,
                    progress_args=(status_message, download.name, message.from_user.first_name, user_id, upload_id)
                )
                await message._client.send_document(Var.LOG_CHANNEL, msg.document.file_id, caption=part_caption)
        else:
            upload_id = uuid.uuid4().hex
            part_caption = caption 
            msg = await message.reply_document(
                file_path,
                caption=caption,
                progress=upload_progress,
                progress_args=(status_message, download.name, message.from_user.first_name, user_id, upload_id)
            )
            await message._client.send_document(Var.LOG_CHANNEL, msg.document.file_id, caption=part_caption)
        LOGS.info(f"📤 Sent file to user: {file_path}")
        await status_message.delete()
    except Exception as e:
        LOGS.error(f"❌ Failed to send file: {e}")
        await message.reply(f"❌ Failed to send file: {e}")

async def split_video_with_ffmpeg(input_path, output_prefix, split_size):
    try:
        original_ext = os.path.splitext(input_path)[1].lower() or '.mp4'
        start_time = datetime.now()
        proc = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        total_duration = float(stdout.decode().strip())
        file_size = os.path.getsize(input_path)
        parts = math.ceil(file_size / split_size)
        if parts == 1:
            return [input_path]
        duration_per_part = total_duration / parts
        split_files = []
        for i in range(parts):
            output_path = f"{output_prefix}.{i+1:03d}{original_ext}"
            cmd = [
                'ffmpeg', '-y', '-ss', str(i * duration_per_part),
                '-i', input_path, '-t', str(duration_per_part),
                '-c', 'copy', '-map', '0',
                '-avoid_negative_ts', 'make_zero',
                output_path
            ]
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
            split_files.append(output_path)
        return split_files
    except Exception as e:
        LOGS.error(f"Split error: {e}")
        raise

async def upload_progress(current, total, status_message, file_name, user_name, user_id, upload_id):
    now = time.time()
    progress = (current / total) * 100 if total else 0
    prev_bytes, prev_time = last_upload_speed.get(upload_id, (0, now))
    elapsed = max(now - prev_time, 1e-3)
    speed = (current - prev_bytes) / elapsed
    last_upload_speed[upload_id] = (current, now)
    last_time = last_upload_update.get(upload_id, 0)
    last_percent = last_upload_progress.get(upload_id, 0)
    bar_length = 12
    filled_slots = int(progress / (100 / bar_length))
    status_bar = f"{'⬢' * filled_slots}{'⬡' * (bar_length - filled_slots)}"
    if (now - last_time >= UPDATE_INTERVAL) or (progress - last_percent >= MIN_PROGRESS_STEP) or (progress == 100):
        status_text = (
            f"<i><b>{file_name}</b></i>\n\n"
            f"<b>Task By {user_name}</b>  ( #ID{user_id} )\n"
            f"┟ [{status_bar}] {progress:.2f}%\n"
            f"┠ <b>Processed</b> → <i>{format_size(current)} of {format_size(total)}</i>\n"
            f"┠ <b>Status</b> → <b>Upload</b>\n"
            f"┠ <b>Speed</b> → <i>{format_size(speed)}/s</i>\n"
            f"┖ <b>Engine</b> → <i>Pyrogram</i>\n"
        )
        try:
            await status_message.edit_text(status_text)
            last_upload_update[upload_id] = now
            last_upload_progress[upload_id] = progress
        except Exception as e:
            LOGS.error(f"Failed to update upload status message: {e}")
