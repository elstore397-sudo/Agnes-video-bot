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
    """Generate video dari gambar - kirim base64 langsung"""
    try:
        # Baca gambar sebagai base64
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Gambar siap ({len(image_data)} bytes)")
    except Exception as e:
        return {"error": f"Gagal membaca gambar: {str(e)}"}
    
    # Kirim request
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
        
        # Ambil task_id
        task_id = result.get('task_id') or result.get('id') or result.get('video_id')
        if task_id:
            return poll_video_result(task_id)
        return {"error": f"Tidak ada task_id: {result}"}
            
    except requests.exceptions.Timeout:
        return {"error": "⏰ Timeout - Server Agnes tidak merespons"}
    except Exception as e:
        return {"error": str(e)}

# ========== POLLING ==========
def poll_video_result(task_id, max_wait=180, interval=5):
    """Polling hasil video"""
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
            logger.info(f"Status: {status}")
            
            if result.get('error'):
                return {"error": f"API error: {result['error'].get('message', 'Unknown')}"}
            
            if status == 'completed':
                video_url = result.get('video_url') or result.get('url') or result.get('output')
                if video_url:
                    return {"success": True, "video_url": video_url}
                return {"error": "Tidak ada URL video"}
            
            elif status in ['failed', 'error']:
                return {"error": f"Video gagal: {result.get('message', 'Unknown')}"}
            
            elif status in ['queued', 'processing', 'pending', 'running', 'in_progress']:
                progress = result.get('progress', 0)
                logger.info(f"⏳ {status} - {progress}%")
                time.sleep(interval)
            else:
                time.sleep(interval)
                
        except Exception as e:
            logger.warning(f"Polling error: {e}")
            time.sleep(interval)
    
    return {"error": "⏰ Timeout - Video membutuhkan waktu lebih dari 3 menit"}

# ========== DOWNLOAD VIDEO ==========
def download_video(video_url):
    """Download video dari URL"""
    response = requests.get(video_url, timeout=120)
    response.raise_for_status()
    return response.content

# ========== HANDLER BOT ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    await update.message.reply_text(
        "👋 Kirim foto + deskripsi untuk buat video 10 detik!",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        await update.message.reply_text("✅ Foto siap! Kirim deskripsi videonya.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('photo_received'):
        await update.message.reply_text("⚠️ Kirim foto dulu!")
        return
    
    prompt = update.message.text
    status_msg = await update.message.reply_text("🎬 Membuat video 10 detik... (1-3 menit)")
    
    try:
        result = generate_video(
            prompt=prompt,
            image_path=context.user_data['photo_path'],
            duration=10
        )
        
        # Hapus file temp
        if os.path.exists(context.user_data['photo_path']):
            os.remove(context.user_data['photo_path'])
        context.user_data.clear()
        
        if result.get('success'):
            video_bytes = download_video(result['video_url'])
            await status_msg.delete()
            await update.message.reply_video(
                video_bytes,
                caption=f"🎉 Video selesai!\n📝 {prompt[:100]}",
                filename="video.mp4",
                timeout=120.0
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

# ========== MAIN ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^(generate|help)$"))
    
    print("🤖 Bot jalan! Tekan Ctrl+C berhenti.")
    app.run_polling()

if __name__ == "__main__":
    main()
