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
    filters,  # <- GANTI: Filters → filters (huruf kecil)
    CallbackQueryHandler,
    ContextTypes
)

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

# ========== FUNGSI UPLOAD GAMBAR ==========
def upload_image_to_agnes(image_path):
    """
    Upload gambar ke Agnes API, dapatkan URL
    """
    logger.info("Upload gambar ke Agnes...")
    url = f"{AGNES_API_URL}/v1/uploads"
    headers = {'Authorization': f'Bearer {AGNES_API_KEY}'}
    
    try:
        with open(image_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(url, headers=headers, files=files, timeout=30)
            response.raise_for_status()
            result = response.json()
            image_url = result.get('url')
            logger.info(f"✅ Gambar berhasil diupload: {image_url}")
            return image_url
    except Exception as e:
        logger.error(f"Gagal upload gambar: {e}")
        raise Exception(f"Gagal upload gambar: {str(e)}")

# ========== FUNGSI GENERATE VIDEO ==========
def generate_video(prompt, image_path, duration=10):
    """
    Generate video dari gambar dengan durasi 10 detik
    """
    try:
        # STEP 1: Upload gambar ke Agnes
        image_url = upload_image_to_agnes(image_path)
        
        # STEP 2: Kirim request generate video
        logger.info("Mengirim request ke Agnes API untuk generate video...")
        url = f"{AGNES_API_URL}/v1/videos"
        
        headers = {
            'Authorization': f'Bearer {AGNES_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'agnes-video-v2.0',
            'prompt': prompt,
            'image_url': image_url,      # PAKAI URL, BUKAN BASE64!
            'duration': duration,        # 10 DETIK
            'aspect_ratio': '9:16'       # Vertical untuk TikTok/Reels
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response dari Agnes: {result}")
        
        # Cek error
        if result.get('error'):
            error_msg = result['error'].get('message', 'Unknown error')
            return {"error": f"Agnes API error: {error_msg}"}
        
        # Ambil video_id untuk polling
        video_id = result.get('video_id')
        if video_id:
            logger.info(f"Video ID: {video_id}")
            return poll_video_result(video_id)
        else:
            return {"error": f"Tidak ada video_id dalam response: {result}"}
            
    except requests.exceptions.Timeout:
        logger.error("Timeout saat memanggil Agnes API")
        return {"error": "⏰ Timeout - Server Agnes tidak merespons"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error request: {e}")
        return {"error": f"Error request: {str(e)}"}
    except Exception as e:
        logger.error(f"Error unexpected: {e}")
        return {"error": f"Error: {str(e)}"}

# ========== FUNGSI POLLING ==========
def poll_video_result(video_id, max_wait=180, interval=5):
    """
    Polling hasil video menggunakan video_id
    Endpoint: GET /agnesapi?video_id=<ID>
    """
    logger.info(f"Mulai polling untuk video_id: {video_id}")
    
    url = f"{AGNES_API_URL}/agnesapi?video_id={video_id}"
    headers = {'Authorization': f'Bearer {AGNES_API_KEY}'}
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            # Jika 404, video belum siap
            if response.status_code == 404:
                if last_status != 'waiting':
                    logger.info("⏳ Video belum siap (404), menunggu...")
                    last_status = 'waiting'
                time.sleep(interval)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            # Cek status
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
            
            # Status proses
            elif status in ['queued', 'processing', 'pending', 'running']:
                progress = result.get('progress', 0)
                logger.info(f"⏳ Status: {status}, Progress: {progress}%")
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
    
    return {"error": "⏰ Timeout - Video membutuhkan waktu lebih dari 3 menit"}

# ========== FUNGSI DOWNLOAD VIDEO ==========
def download_video(video_url):
    """
    Download video dari URL untuk dikirim ke Telegram
    """
    logger.info(f"Download video dari: {video_url}")
    try:
        response = requests.get(video_url, timeout=120)
        response.raise_for_status()
        logger.info(f"✅ Video berhasil didownload ({len(response.content)} bytes)")
        return response.content
    except Exception as e:
        logger.error(f"Gagal download video: {e}")
        raise Exception(f"Gagal download video: {str(e)}")

# ========== HANDLER BOT ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Halo! Kirimkan foto dan deskripsi untuk membuat video AI.\n\n"
        "📌 Cara:\n"
        "1. Upload foto\n"
        "2. Kirim deskripsi video (contoh: 'anjing berlari di pantai')\n"
        "3. Tunggu 1-3 menit\n"
        "4. Video 10 detik akan muncul!\n\n"
        "Klik tombol di bawah:",
        reply_markup=reply_markup
    )

async def generate_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler tombol Buat Video"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📤 Kirimkan **foto** dulu, lalu kirimkan **deskripsi** videonya.\n\n"
        "Contoh deskripsi: 'anjing berlari di pantai, sunset'"
    )

async def help_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler tombol Bantuan"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 **Panduan:**\n\n"
        "1. Kirim foto\n"
        "2. Kirim deskripsi (contoh: 'anjing berlari di pantai')\n"
        "3. Tunggu 1-3 menit\n"
        "4. Video 10 detik akan muncul!\n\n"
        "📦 Model: agnes-video-v2.0\n"
        "⏱️ Durasi: 10 detik\n"
        "📱 Format: 9:16 (Vertical)\n"
        "💰 Gratis (rate limit 16 req/menit)"
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
            "✅ Foto berhasil diupload!\n"
            "Sekarang kirimkan **deskripsi** untuk video.\n\n"
            "Contoh: 'kucing bermain di taman, cinematic'"
        )
    except Exception as e:
        logger.error(f"Error handle_photo: {e}")
        await update.message.reply_text(f"❌ Gagal upload foto: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proses deskripsi dari user dan generate video"""
    if not context.user_data.get('photo_received'):
        await update.message.reply_text(
            "⚠️ Kirimkan foto dulu ya!\n"
            "Upload foto yang ingin dijadikan video."
        )
        return
    
    prompt = update.message.text
    context.user_data['prompt'] = prompt
    
    # Kirim pesan proses
    status_msg = await update.message.reply_text(
        "🎬 Sedang membuat video 10 detik...\n"
        "⏳ Mohon tunggu 1-3 menit.\n"
        "📤 Jangan kirim pesan lain sampai selesai!"
    )
    
    # Proses generate
    try:
        result = generate_video(
            prompt=prompt,
            image_path=context.user_data['photo_path'],
            duration=10  # DURASI 10 DETIK!
        )
        
        # Hapus file temp
        if os.path.exists(context.user_data['photo_path']):
            os.remove(context.user_data['photo_path'])
        context.user_data.clear()
        
        # Kirim hasil
        if result.get('success'):
            video_url = result.get('video_url')
            
            try:
                # Download video dulu (biar gak expired)
                video_bytes = download_video(video_url)
                
                # Kirim video ke Telegram
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
                # Fallback: kirim URL kalo download gagal
                logger.warning(f"Download video gagal, kirim URL: {e}")
                keyboard = [[InlineKeyboardButton("📥 Download Video", url=video_url)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await status_msg.delete()
                await update.message.reply_video(
                    video_url,
                    caption=f"🎉 **Video 10 detik selesai!**\n\n"
                            f"📝 Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n"
                            "Klik tombol di bawah untuk download.",
                    reply_markup=reply_markup,
                    timeout=120.0
                )
        else:
            error_msg = result.get('error', 'Unknown error')
            await status_msg.edit_text(
                f"❌ Gagal membuat video:\n{error_msg}\n\n"
                "💡 Tips:\n"
                "- Coba deskripsi yang lebih detail\n"
                "- Pastikan gambar jelas\n"
                "- Tunggu beberapa saat lalu coba lagi"
            )
            
    except Exception as e:
        logger.error(f"Error generate: {e}")
        await status_msg.edit_text(
            f"❌ Terjadi error:\n{str(e)}\n\n"
            "Coba lagi nanti."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /cancel"""
    # Hapus file temp jika ada
    if context.user_data.get('photo_path'):
        try:
            if os.path.exists(context.user_data['photo_path']):
                os.remove(context.user_data['photo_path'])
                logger.info(f"File temp dihapus: {context.user_data['photo_path']}")
        except Exception as e:
            logger.warning(f"Gagal hapus file temp: {e}")
    
    context.user_data.clear()
    await update.message.reply_text(
        "🔄 Proses dibatalkan.\n"
        "Kirim /start untuk memulai ulang."
    )

# ========== MAIN ==========
def main():
    """Jalankan bot dengan versi Application (PTB v20+)"""
    try:
        # Buat application (bukan updater)
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Tambahkan handler
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))  # filters.PHOTO
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))  # filters.TEXT
        application.add_handler(CallbackQueryHandler(generate_button, pattern="^generate$"))
        application.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
        
        # Jalankan bot
        logger.info("🤖 Bot sedang berjalan...")
        print("=" * 50)
        print("🤖 Bot Video AI Agnes - 10 Detik")
        print("=" * 50)
        print("✅ Bot berjalan dengan sukses!")
        print("📱 Buka Telegram dan kirim /start ke bot-mu")
        print("⏱️ Durasi video: 10 detik")
        print("📐 Format: 9:16 (Vertical)")
        print("=" * 50)
        print("Tekan Ctrl+C untuk berhenti.")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Error main: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
