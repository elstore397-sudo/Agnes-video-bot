#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
import time
import base64
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

# ========== KONFIGURASI ==========
# Ganti dengan data milikmu
BOT_TOKEN = "8875490753:AAGXo5uMd_J1GOf423u2lj9qqJGqBRptFU8"        # Token dari @BotFather
AGNES_API_KEY = "sk-r7lyiDYxadlM3og6fXekCEMQ4iYd2v4klNWEjsWLcHRcmcr1"   # API Key dari Agnes
AGNES_API_URL = "https://apihub.agnes-ai.com"  # Base URL Agnes

# ========== LOGGING ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FUNGSI GENERATE VIDEO ==========
def generate_video(prompt, image_path, duration=5):
    """
    Kirim request ke Agnes API untuk generate video dari gambar
    """
    logger.info("Membaca gambar...")
    
    # Baca gambar sebagai base64
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Gambar berhasil dibaca ({len(image_data)} bytes)")
    except Exception as e:
        logger.error(f"Gagal membaca gambar: {e}")
        return {"error": f"Gagal membaca gambar: {str(e)}"}
    
    # Kirim request ke Agnes API
    logger.info("Mengirim request ke Agnes API...")
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
        'height': 768,
        'width': 1152
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response dari Agnes: {result}")
        
        # Cek error
        if result.get('error'):
            error_msg = result['error'].get('message', 'Unknown error')
            return {"error": f"Agnes API error: {error_msg}"}
        
        # Ambil video_id (BUKAN task_id)
        video_id = result.get('video_id')
        if video_id:
            logger.info(f"Video ID: {video_id}")
            return poll_video_result(video_id)
        else:
            return {"error": f"Tidak ada video_id dalam response: {result}"}
            
    except requests.exceptions.Timeout:
        logger.error("Timeout saat memanggil Agnes API")
        return {"error": "Timeout - Server Agnes tidak merespons"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error request: {e}")
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Error unexpected: {e}")
        return {"error": str(e)}

def poll_video_result(video_id, max_wait=180, interval=5):
    """
    Polling hasil video menggunakan video_id (WAJIB!)
    Berdasarkan Agnes AI Official Skill:
    - Endpoint: GET /agnesapi?video_id=<ID>
    - JANGAN gunakan task_id untuk polling
    """
    logger.info(f"Mulai polling untuk video_id: {video_id}")

    # ENDPOINT YANG BENAR berdasarkan Skill Resmi Agnes
    url = f"{AGNES_API_URL}/agnesapi?video_id={video_id}"
    headers = {'Authorization': f'Bearer {AGNES_API_KEY}'}

    start_time = time.time()
    last_status = None

    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, headers=headers, timeout=30)

            # Jika 404, berarti video belum siap
            if response.status_code == 404:
                if last_status != 'waiting':
                    logger.info("Video belum siap (404), menunggu...")
                    last_status = 'waiting'
                time.sleep(interval)
                continue

            response.raise_for_status()
            result = response.json()

            # Cek status dari response
            status = result.get('status')
            logger.info(f"Status video: {status}")
            last_status = status

            # Cek error
            if result.get('error'):
                error_msg = result['error'].get('message', 'Unknown error')
                return {"error": f"Agnes API error: {error_msg}"}

            # Status selesai
            if status == 'completed':
                video_url = result.get('video_url') or result.get('url')
                if video_url:
                    logger.info(f"✅ Video selesai: {video_url}")
                    return {"success": True, "video_url": video_url}
                else:
                    return {"error": "Video selesai tapi tidak ada URL"}

            # Status gagal
            elif status in ['failed', 'error']:
                msg = result.get('message', 'Unknown error')
                return {"error": f"Video gagal: {msg}"}

            # Status: 'queued', 'processing', 'pending'
            elif status in ['queued', 'processing', 'pending', 'running']:
                progress = result.get('progress', 0)
                logger.info(f"Status: {status}, Progress: {progress}%")
                time.sleep(interval)

            # Status tidak dikenal
            else:
                logger.info(f"Status tidak dikenal: {status}, menunggu...")
                time.sleep(interval)

        except requests.exceptions.Timeout:
            logger.warning("Polling timeout, mencoba lagi...")
            time.sleep(interval)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Polling error: {e}, mencoba lagi...")
            time.sleep(interval)
        except Exception as e:
            logger.error(f"Polling unexpected error: {e}")
            time.sleep(interval)

    return {"error": "⏰ Timeout - Video membutuhkan waktu lebih lama dari 3 menit"}

# ========== HANDLER BOT (Versi Updater) ==========
def start(update, context):
    """Handler untuk command /start"""
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "👋 Halo! Kirimkan foto dan deskripsi untuk membuat video AI.\n\n"
        "📌 Cara:\n"
        "1. Upload foto\n"
        "2. Kirim deskripsi video\n"
        "3. Tunggu 1-3 menit\n\n"
        "Klik tombol di bawah:",
        reply_markup=reply_markup
    )

def generate_button(update, context):
    """Handler tombol Buat Video"""
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📤 Kirimkan **foto** dulu, lalu kirimkan **deskripsi** videonya.\n\n"
        "Contoh deskripsi: 'anjing berlari di pantai, sunset'"
    )

def help_button(update, context):
    """Handler tombol Bantuan"""
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📖 **Panduan:**\n\n"
        "1. Kirim foto\n"
        "2. Kirim deskripsi (contoh: 'anjing berlari di pantai')\n"
        "3. Tunggu 1-3 menit\n"
        "4. Video akan muncul!\n\n"
        "Model: agnes-video-v2.0\n"
        "Durasi: 5 detik\n"
        "Kuota: Terbatas (gratis)"
    )

def handle_photo(update, context):
    """Simpan foto yang diupload user"""
    try:
        photo = update.message.photo[-1]
        file = photo.get_file()
        
        os.makedirs("temp", exist_ok=True)
        file_path = f"temp/{update.effective_user.id}_photo.jpg"
        file.download(file_path)
        
        context.user_data['photo_path'] = file_path
        context.user_data['photo_received'] = True
        
        update.message.reply_text(
            "✅ Foto berhasil diupload!\n"
            "Sekarang kirimkan **deskripsi** untuk video.\n\n"
            "Contoh: 'kucing bermain di taman'"
        )
    except Exception as e:
        logger.error(f"Error handle_photo: {e}")
        update.message.reply_text(f"❌ Gagal upload foto: {str(e)}")

def handle_text(update, context):
    """Proses deskripsi dari user"""
    if not context.user_data.get('photo_received'):
        update.message.reply_text(
            "⚠️ Kirimkan foto dulu ya!\n"
            "Upload foto yang ingin dijadikan video."
        )
        return
    
    prompt = update.message.text
    context.user_data['prompt'] = prompt
    
    # Kirim pesan proses
    status_msg = update.message.reply_text(
        "🎬 Sedang membuat video...\n"
        "Mohon tunggu 1-3 menit.\n"
        "⏳ Jangan kirim pesan lain sampai selesai!"
    )
    
    # Proses generate
    try:
        result = generate_video(
            prompt=prompt,
            image_path=context.user_data['photo_path'],
            duration=5
        )
        
        # Hapus file temp
        if os.path.exists(context.user_data['photo_path']):
            os.remove(context.user_data['photo_path'])
        context.user_data.clear()
        
        # Kirim hasil
        if result.get('success'):
            video_url = result.get('video_url')
            keyboard = [[InlineKeyboardButton("📥 Download Video", url=video_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status_msg.delete()
            update.message.reply_video(
                video_url,
                caption="🎉 **Video selesai!**\n\n"
                        f"📝 Prompt: {prompt[:100]}...\n"
                        "Klik tombol di bawah untuk download.",
                reply_markup=reply_markup
            )
        else:
            error_msg = result.get('error', 'Unknown error')
            status_msg.edit_text(
                f"❌ Gagal membuat video:\n{error_msg}\n\n"
                "Coba lagi nanti atau gunakan deskripsi yang berbeda."
            )
            
    except Exception as e:
        logger.error(f"Error generate: {e}")
        status_msg.edit_text(
            f"❌ Terjadi error:\n{str(e)}\n\n"
            "Coba lagi nanti."
        )

def cancel(update, context):
    """Handler untuk /cancel"""
    # Hapus file temp jika ada
    if context.user_data.get('photo_path'):
        try:
            if os.path.exists(context.user_data['photo_path']):
                os.remove(context.user_data['photo_path'])
        except:
            pass
    
    context.user_data.clear()
    update.message.reply_text(
        "🔄 Proses dibatalkan.\n"
        "Kirim /start untuk memulai ulang."
    )

# ========== MAIN ==========
def main():
    """Jalankan bot dengan versi Updater (lebih stabil)"""
    try:
        # Buat updater
        updater = Updater(token=BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Tambahkan handler
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("cancel", cancel))
        dp.add_handler(MessageHandler(Filters.photo, handle_photo))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
        dp.add_handler(CallbackQueryHandler(generate_button, pattern="^generate$"))
        dp.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
        
        # Jalankan bot
        logger.info("🤖 Bot sedang berjalan... (versi Updater)")
        print("🤖 Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Error main: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
