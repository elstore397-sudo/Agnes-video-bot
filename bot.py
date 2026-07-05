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
    """Handler /start"""
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    await update.message.reply_text(
        "👋 Halo! Kirim foto + deskripsi untuk buat video 10 detik!\n\n"
        "📌 Cara:\n"
        "1. Kirim FOTO\n"
        "2. Kirim DESKRIPSI (contoh: 'anjing berlari di pantai')\n"
        "3. Tunggu 1-3 menit\n\n"
        "Atau klik tombol di bawah:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def generate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler tombol 'Buat Video'"""
    query = update.callback_query
    await query.answer()  # Penting: biar loading di Telegram hilang
    
    await query.edit_message_text(
        "📤 **Cara membuat video:**\n\n"
        "1. Kirim **FOTO** yang ingin dijadikan video\n"
        "2. Setelah foto terkirim, kirim **DESKRIPSI**\n"
        "3. Tunggu 1-3 menit, video akan muncul!\n\n"
        "Contoh deskripsi:\n"
        "『seorang gadis tersenyum memegang tumbler』"
    )

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler tombol 'Bantuan'"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📖 **Panduan Bot:**\n\n"
        "📸 Kirim FOTO\n"
        "✏️ Kirim DESKRIPSI\n"
        "⏱️ Tunggu 1-3 menit\n"
        "🎬 Video 10 detik siap!\n\n"
        "📦 Model: agnes-video-v2.0\n"
        "⏱️ Durasi: 10 detik\n"
        "📱 Format: 9:16 (Vertical)\n"
        "💰 Gratis\n\n"
        "Gunakan /cancel untuk membatalkan."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simpan foto yang diupload user"""
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        os.makedirs("temp", exist_ok=True)
        file_path = f"temp/{update.effective_user.id}_photo.jpg"
        await file.download_to_drive(file_path)
        
        context.user_data['photo_path'] = file_path
        context.user_data['photo_received'] = True
        
        await update.message.reply_text(
            "✅ **Foto berhasil diupload!**\n\n"
            "Sekarang kirimkan **DESKRIPSI** videonya.\n"
            "Contoh: 'kucing bermain di taman, cinematic lighting'"
        )
    except Exception as e:
        logger.error(f"Error handle_photo: {e}")
        await update.message.reply_text(f"❌ Gagal upload foto: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses deskripsi dari user dan generate video"""
    if not context.user_data.get('photo_received'):
        await update.message.reply_text(
            "⚠️ **Kirim foto dulu ya!**\n\n"
            "Upload foto yang ingin dijadikan video, "
            "lalu kirim deskripsinya."
        )
        return
    
    prompt = update.message.text
    status_msg = await update.message.reply_text(
        "🎬 **Sedang membuat video 10 detik...**\n"
        "⏳ Mohon tunggu 1-3 menit.\n"
        "📤 Jangan kirim pesan lain sampai selesai!"
    )
    
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
            video_url = result.get('video_url')
            
            try:
                # Download video dulu
                video_bytes = download_video(video_url)
                
                await status_msg.delete()
                await update.message.reply_video(
                    video_bytes,
                    caption=f"🎉 **Video 10 detik selesai!**\n\n"
                            f"📝 Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n"
                            f"⏱️ Durasi: 10 detik\n"
                            f"📱 Format: 9:16",
                    filename="video_10detik.mp4",
                    timeout=120.0,
                    supports_streaming=True
                )
                
            except Exception as e:
                # Fallback: kirim URL
                logger.warning(f"Download video gagal, kirim URL: {e}")
                keyboard = [[InlineKeyboardButton("📥 Download Video", url=video_url)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await status_msg.delete()
                await update.message.reply_video(
                    video_url,
                    caption=f"🎉 **Video 10 detik selesai!**\n\n"
                            f"📝 Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
                    reply_markup=reply_markup,
                    timeout=120.0
                )
        else:
            error_msg = result.get('error', 'Unknown error')
            await status_msg.edit_text(
                f"❌ **Gagal membuat video:**\n\n{error_msg}\n\n"
                "💡 **Tips:**\n"
                "- Coba deskripsi yang lebih detail\n"
                "- Pastikan gambar jelas\n"
                "- Tunggu beberapa saat lalu coba lagi"
            )
            
    except Exception as e:
        logger.error(f"Error generate: {e}")
        await status_msg.edit_text(
            f"❌ **Terjadi error:**\n\n{str(e)}\n\n"
            "Coba lagi nanti."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /cancel"""
    if context.user_data.get('photo_path'):
        try:
            if os.path.exists(context.user_data['photo_path']):
                os.remove(context.user_data['photo_path'])
                logger.info(f"File temp dihapus: {context.user_data['photo_path']}")
        except Exception as e:
            logger.warning(f"Gagal hapus file temp: {e}")
    
    context.user_data.clear()
    await update.message.reply_text(
        "🔄 **Proses dibatalkan.**\n"
        "Kirim /start untuk memulai ulang."
    )

# ========== ERROR HANDLER ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log error dan kirim pesan ke user"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ **Terjadi error internal.**\n"
                "Tim developer sudah diberitahu.\n"
                "Coba lagi nanti."
            )
    except:
        pass

# ========== MAIN ==========
def main():
    """Jalankan bot"""
    try:
        # Buat application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Tambahkan handler
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # CallbackQueryHandler untuk tombol
        application.add_handler(CallbackQueryHandler(generate_button, pattern="^generate$"))
        application.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
        
        # Error handler
        application.add_error_handler(error_handler)
        
        # Jalankan bot
        logger.info("🤖 Bot sedang berjalan...")
        print("=" * 55)
        print("🤖 BOT VIDEO AI AGNES - 10 DETIK")
        print("=" * 55)
        print("✅ Bot berjalan dengan sukses!")
        print("📱 Buka Telegram dan kirim /start ke bot-mu")
        print("⏱️ Durasi video: 10 detik")
        print("📐 Format: 9:16 (Vertical)")
        print("=" * 55)
        print("Tekan Ctrl+C untuk berhenti.")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Error main: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
