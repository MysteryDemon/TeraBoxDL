from TorrentDL import LOGS, UPDATE_INTERVAL, MIN_PROGRESS_STEP, SPLIT_SIZE, Var, aria2, active_downloads, last_upload_update, last_upload_progress, last_upload_speed
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
                "--summary-interval=1",
                "--bt-save-metadata=true"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        Thread(target=stream_aria2_logs, args=(process,), daemon=True).start()
        time.sleep(2)
    else:
        LOGS.info("ℹ️ aria2c is already running.")

def add_download(url: str, output_path: str, headers: dict = None):
    if not output_path:
        output_path = f"./downloads/{generate_download_id()}"

    directory = os.path.dirname(output_path)
    if not directory:
        directory = "./downloads"
        output_path = os.path.join(directory, os.path.basename(output_path))

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
        # Only edit if the text is different (prevents 400 MESSAGE_NOT_MODIFIED)
        if getattr(status_message, "text", None) == text:
            return
        await status_message.edit_text(text)
    except Exception as e:
        LOGS.error(f"Failed to update status message: Telegram says: {e}")

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

    # Phase 1: Show metadata fetching progress
    while True:
        await asyncio.sleep(5)
        try:
            download.update()
        except Exception as e:
            if "is not found" in str(e):
                LOGS.info(f"Download was cancelled or removed: {download.gid}")
                return
            else:
                LOGS.error(f"Error updating download: {e}")
                return

        files = download.files if hasattr(download, "files") else []
        meta_files = [f for f in files if "[METADATA]" in str(f.path)]
        real_files = [f for f in files if "[METADATA]" not in str(f.path)]

        if meta_files and not real_files:
            # Show metadata progress
            meta_file = meta_files[0]
            processed = format_size(getattr(meta_file, "completed_length", 0))
            total = format_size(getattr(meta_file, "length", 0))
            progress = (getattr(meta_file, "completed_length", 0) / getattr(meta_file, "length", 1)) * 100 if getattr(meta_file, "length", 0) else 0
            bar_length = 12
            filled_slots = int(progress / (100 / bar_length)) if progress else 0
            status_bar = f"{'⬢' * filled_slots}{'⬡' * (bar_length - filled_slots)}"
            status_text = (
                f"<i><b>Fetching torrent metadata...</b></i>\n\n"
                f"<b>Task By {message.from_user.first_name}</b>  ( #ID{user_id} )\n"
                f"┟ [{status_bar}] {progress:.2f}%\n"
                f"┠ <b>Processed</b> → <i>{processed} of {total}</i>\n"
                f"┠ <b>Status</b> → <b>Metadata</b>\n"
                f"┠ <b>Engine</b> → <i>Aria2 v1.37.0</i>\n"
                f"┖ <b>Stop</b> → <i>/c_{download_id}</i>\n"
            )
            await update_status_message(status_message, status_text)
        if real_files:
            break  # Metadata fetched, real files are present

    # Phase 2: Monitor real file download progress
    while not download.is_complete:
        if active_downloads[download_id].get("cancelled"):
            LOGS.info(f"Download cancelled for ID: {download_id}")
            return

        await asyncio.sleep(5)
        try:
            download.update()
        except Exception as e:
            if "is not found" in str(e):
                LOGS.info(f"Download was cancelled or removed: {download.gid}")
                return
            else:
                LOGS.error(f"Error updating download: {e}")
                return

        files = download.files if hasattr(download, "files") else []
        real_files = [f for f in files if "[METADATA]" not in str(f.path)]
        total_length = sum(getattr(f, "length", 0) for f in real_files)
        completed_length = sum(getattr(f, "completed_length", 0) for f in real_files)
        progress = (completed_length / total_length) * 100 if total_length else 0
        bar_length = 12
        filled_slots = int(progress / (100 / bar_length)) if progress else 0
        status_bar = f"{'⬢' * filled_slots}{'⬡' * (bar_length - filled_slots)}"
        status_text = (
            f"<i><b>{download.name}</b></i>\n\n"
            f"<b>Task By {message.from_user.first_name}</b>  ( #ID{user_id} )\n"
            f"┟ [{status_bar}] {progress:.2f}%\n"
            f"┠ <b>Processed</b> → <i>{format_size(completed_length)} of {format_size(total_length)}</i>\n"
            f"┠ <b>Status</b> → <b>Download</b>\n"
            f"┠ <b>Engine</b> → <i>Aria2 v1.37.0</i>\n"
            f"┖ <b>Stop</b> → <i>/c_{download_id}</i>\n"
        )
        await update_status_message(status_message, status_text)

    # Phase 3: Upload/send real files (skip metadata)
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

    files = completed.files if hasattr(completed, "files") else []
    real_files = [f for f in files if "[METADATA]" not in str(f.path)]

    found_file = False
    for file_obj in real_files:
        file_path = file_obj.path
        if not file_path or not os.path.exists(file_path):
            LOGS.error(f"File not found: {file_path}")
            await message.reply(f"❌ File not found: {file_path}")
            continue
        found_file = True
        # [your send/upload logic here, unchanged]

    if not found_file:
        await message.reply("❌ No valid files found to send.")
        return

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
