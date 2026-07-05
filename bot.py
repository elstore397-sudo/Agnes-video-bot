#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
import time
import base64
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters,
    CallbackQueryHandler,
    ContextTypes
)

# ========== KONFIGURASI ==========
BOT_TOKEN = "8875490753:AAGXo5uMd_J1GOf423u2lj9qqJGqBRptFU8"
AGNES_API_KEY = "sk-r7lyiDYxadlM3og6fXekCEMQ4iYd2v4klNWEjsWLcHRcmcr1"
AGNES_API_URL = "https://apihub.agnes-ai.com"

# ========== LOGGING ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== GENERATE VIDEO ==========
def generate_video(prompt, image_path, duration=10):
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Gambar siap ({len(image_data)} bytes)")
    except Exception as e:
        return {"error": f"Gagal membaca gambar: {str(e)}"}
    
    url = f"{AGNES_API_URL}/v1/videos"
    headers = {
        'Authorization': f'Bearer {AGNES_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'agnes-video-v2.0',
        'prompt': prompt,
        'image': image_base64,
        'duration': duration,
        'aspect_ratio': '9:16'
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response: {result}")
        
        if result.get('error'):
            return {"error": f"Agnes API error: {result['error'].get('message', 'Unknown')}"}
        
        task_id = result.get('task_id') or result.get('id') or result.get('video_id')
        if task_id:
            return poll_video_result(task_id)
        return {"error": f"Tidak ada task_id: {result}"}
            
    except requests.exceptions.Timeout:
        return {"error": "⏰ Timeout - Server Agnes tidak merespons"}
    except Exception as e:
        return {"error": str(e)}

# ========== POLLING ==========
def poll_video_result(task_id, max_wait=600, interval=5):
    url = f"{AGNES_API_URL}/v1/videos/{task_id}"
    headers = {'Authorization': f'Bearer {AGNES_API_KEY}'}
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 404:
                logger.info("⏳ Video belum siap...")
                time.sleep(interval)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            status = result.get('status')
            progress = result.get('progress', 0)
            elapsed = int(time.time() - start_time)
            
            logger.info(f"Status: {status}, Progress: {progress}%, Elapsed: {elapsed}s")
            
            if result.get('error'):
                return {"error": f"API error: {result['error'].get('message', 'Unknown')}"}
            
            if status == 'completed':
                video_url = result.get('video_url') or result.get('url') or result.get('output')
                if video_url:
                    logger.info(f"✅ Video URL: {video_url}")
                    return {"success": True, "video_url": video_url}
                return {"error": "Tidak ada URL video"}
            
            elif status in ['failed', 'error']:
                return {"error": f"Video gagal: {result.get('message', 'Unknown')}"}
            
            elif status in ['queued', 'processing', 'pending', 'running', 'in_progress']:
                if elapsed % 30 == 0 and elapsed > 0:
                    logger.info(f"⏳ Masih {status} - {progress}% - {elapsed}s")
                time.sleep(interval)
            else:
                time.sleep(interval)
                
        except Exception as e:
            logger.warning(f"Polling error: {e}")
            time.sleep(interval)
    
    return {"error": "⏰ Timeout - Video membutuhkan waktu lebih dari 10 menit"}

# ========== DOWNLOAD VIDEO (DENGAN RETRY) ==========
def download_video(video_url, max_retries=3):
    """Download video dengan retry dan timeout 180 detik"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Download video (attempt {attempt+1}/{max_retries})...")
            response = requests.get(video_url, timeout=180, stream=True)
            response.raise_for_status()
            
            content_length = response.headers.get('content-length')
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                logger.info(f"Ukuran video: {size_mb:.2f} MB")
            
            content = response.content
            logger.info(f"✅ Download selesai ({len(content)} bytes)")
            return content
            
        except requests.exceptions.Timeout:
            logger.warning(f"Download timeout, retry {attempt+1}/{max_retries}")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"Download error: {e}, retry {attempt+1}/{max_retries}")
            time.sleep(5)
    
    raise Exception("Gagal download video setelah 3 percobaan")

# ========== HANDLER BOT ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    await update.message.reply_text(
        "👋 Kirim foto + deskripsi untuk buat video 10 detik!\n\n"
        "📌 Tunggu 3-5 menit ya!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def generate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📤 **Cara:**\n1. Kirim FOTO\n2. Kirim DESKRIPSI\n3. Tunggu 3-5 menit"
    )

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 **Panduan:**\n📸 Kirim FOTO\n✏️ Kirim DESKRIPSI\n⏱️ Tunggu 3-5 menit\n🎬 Video siap!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        os.makedirs("temp", exist_ok=True)
        file_path = f"temp/{update.effective_user.id}_photo.jpg"
        await file.download_to_drive(file_path)
        context.user_data['photo_path'] = file_path
        context.user_data['photo_received'] = True
        await update.message.reply_text("✅ Foto siap! Kirim deskripsi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('photo_received'):
        await update.message.reply_text("⚠️ Kirim foto dulu!")
        return
    
    prompt = update.message.text
    status_msg = await update.message.reply_text(
        "🎬 **Membuat video 10 detik...**\n⏳ Tunggu 3-5 menit"
    )
    
    try:
        result = generate_video(
            prompt=prompt,
            image_path=context.user_data['photo_path'],
            duration=10
        )
        
        if os.path.exists(context.user_data['photo_path']):
            os.remove(context.user_data['photo_path'])
        context.user_data.clear()
        
        if result.get('success'):
            video_url = result.get('video_url')
            
            try:
                video_bytes = download_video(video_url)
                size_mb = len(video_bytes) / (1024 * 1024)
                
                await status_msg.delete()
                
                if size_mb > 50:
                    await update.message.reply_document(
                        video_bytes,
                        filename="video_10detik.mp4",
                        caption=f"🎉 Video selesai! ({size_mb:.1f}MB)\n📝 {prompt[:100]}"
                    )
                else:
                    await update.message.reply_video(
                        video_bytes,
                        caption=f"🎉 **Video selesai!**\n📝 {prompt[:100]}",
                        filename="video.mp4",
                        timeout=180.0
                    )
                
            except Exception as e:
                logger.warning(f"Download gagal: {e}")
                keyboard = [[InlineKeyboardButton("📥 Download", url=video_url)]]
                await status_msg.delete()
                await update.message.reply_text(
                    f"🎉 Video selesai! Klik tombol download:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            await status_msg.edit_text(f"❌ {result.get('error')}")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('photo_path'):
        try:
            os.remove(context.user_data['photo_path'])
        except:
            pass
    context.user_data.clear()
    await update.message.reply_text("🔄 Dibatalkan.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ========== MAIN ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(generate_button, pattern="^generate$"))
    app.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
    app.add_error_handler(error_handler)
    
    print("🤖 Bot jalan! Timeout 10 menit, retry download 3x.")
    app.run_polling()

if __name__ == "__main__":
    main()
