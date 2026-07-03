#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
import time
import base64
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler
from telegram.ext import filters as Filters

# ========== KONFIGURASI ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN')
AGNES_API_KEY = os.environ.get('AGNES_API_KEY', 'sk-xxxxxxxxxxxx')
AGNES_API_URL = "https://apihub.agnes-ai.com"

# ========== LOGGING ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== FUNGSI BANTUAN ==========
def find_video_url(data, depth=0):
    if depth > 10:
        return None
    if isinstance(data, dict):
        for key in ['video_url', 'url', 'video', 'download_url', 'output', 'result', 'data']:
            if key in data:
                value = data[key]
                if isinstance(value, str) and ('http' in value) and ('.mp4' in value.lower() or 'video' in value.lower()):
                    return value
                if isinstance(value, dict):
                    result = find_video_url(value, depth + 1)
                    if result:
                        return result
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and ('http' in item) and ('.mp4' in item.lower() or 'video' in item.lower()):
                            return item
                        result = find_video_url(item, depth + 1)
                        if result:
                            return result
        for key, value in data.items():
            if isinstance(value, str) and ('http' in value) and ('.mp4' in value.lower() or 'video' in value.lower()):
                return value
            result = find_video_url(value, depth + 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_video_url(item, depth + 1)
            if result:
                return result
    return None

# ========== FUNGSI GENERATE VIDEO ==========
def generate_video(prompt, image_path, model="agnes-video-v2.0", duration=5, width=1152, height=768):
    logger.info("Membaca gambar...")
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"Gambar berhasil dibaca ({len(image_data)} bytes)")
    except Exception as e:
        logger.error(f"Gagal membaca gambar: {e}")
        return {"error": f"Gagal membaca gambar: {str(e)}"}
    
    logger.info("Mengirim request ke Agnes API...")
    url = f"{AGNES_API_URL}/v1/videos"
    headers = {
        'Authorization': f'Bearer {AGNES_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': model,
        'prompt': prompt,
        'image': image_base64,
        'duration': duration,
        'height': height,
        'width': width
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=120)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response dari Agnes: {result}")
        if result.get('error'):
            error_msg = result['error'].get('message', 'Unknown error')
            return {"error": f"Agnes API error: {error_msg}"}
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

def poll_video_result(video_id, max_wait=420, interval=5):
    logger.info(f"Mulai polling untuk video_id: {video_id}")
    url = f"{AGNES_API_URL}/agnesapi?video_id={video_id}"
    headers = {'Authorization': f'Bearer {AGNES_API_KEY}'}
    start_time = time.time()
    last_status = None
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 404:
                if last_status != 'waiting':
                    logger.info("Video belum siap (404), menunggu...")
                    last_status = 'waiting'
                time.sleep(interval)
                continue
            response.raise_for_status()
            result = response.json()
            status = result.get('status')
            logger.info(f"Status video: {status}")
            last_status = status
            if result.get('error'):
                error_msg = result['error'].get('message', 'Unknown error')
                return {"error": f"Agnes API error: {error_msg}"}
            if status == 'completed':
                logger.info(f"Response lengkap: {json.dumps(result, indent=2)[:500]}...")
                video_url = (
                    result.get('video_url') or 
                    result.get('url') or 
                    result.get('video') or
                    result.get('download_url') or
                    result.get('data', {}).get('video_url') or
                    result.get('data', {}).get('url') or
                    result.get('output', {}).get('video_url') or
                    result.get('result', {}).get('video_url')
                )
                if not video_url:
                    video_url = find_video_url(result)
                    logger.info(f"URL ditemukan via recursive search: {video_url}")
                if video_url:
                    logger.info(f"✅ Video selesai: {video_url}")
                    return {"success": True, "video_url": video_url}
                else:
                    logger.error(f"Tidak ada URL dalam response: {json.dumps(result, indent=2)}")
                    return {"error": "Video selesai tapi tidak ada URL"}
            elif status in ['failed', 'error']:
                msg = result.get('message', 'Unknown error')
                return {"error": f"Video gagal: {msg}"}
            elif status in ['queued', 'processing', 'pending', 'running', 'in_progress']:
                progress = result.get('progress', 0)
                logger.info(f"Status: {status}, Progress: {progress}%")
                time.sleep(interval)
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
    return {"error": "⏰ Timeout - Video membutuhkan waktu lebih lama dari 5 menit"}

# ========== HANDLER BOT ==========
def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🎬 Buat Video", callback_data="generate")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "👋 Halo! Selamat datang di AI Video Generator Bot!\n\n"
        "📌 Cara penggunaan:\n"
        "1. Upload foto\n"
        "2. Kirim deskripsi video\n"
        "3. Pilih model, ukuran, durasi\n"
        "4. Tunggu 3-5 menit\n\n"
        "Klik tombol di bawah untuk mulai:",
        reply_markup=reply_markup
    )

def generate_button(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📤 Kirimkan **foto** dulu, lalu kirimkan **deskripsi** videonya.\n\n"
        "Contoh deskripsi: 'anjing berlari di pantai, sunset'"
    )

def help_button(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📖 **Panduan Lengkap:**\n\n"
        "1️⃣ Kirim foto\n"
        "2️⃣ Kirim deskripsi\n"
        "3️⃣ Pilih Ukuran:\n"
        "   - 9:16 (TikTok/Reels/IG Story)\n"
        "   - 16:9 (YouTube/Facebook)\n"
        "   - 1:1 (Instagram Feed)\n"
        "4️⃣ Pilih Durasi: 5 / 10 / 15 detik\n"
        "5️⃣ Tunggu 3-5 menit\n"
        "6️⃣ Video akan muncul!\n\n"
        "⚠️ Kuota harian terbatas (gratis)"
    )

def handle_photo(update, context):
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
    if not context.user_data.get('photo_received'):
        update.message.reply_text("⚠️ Kirimkan foto dulu ya!")
        return
    prompt = update.message.text
    context.user_data['prompt'] = prompt
    keyboard = [
        [InlineKeyboardButton("📱 9:16 TikTok/Reels/IG", callback_data="ratio_9:16")],
        [InlineKeyboardButton("📺 16:9 YouTube/FB/Landscape", callback_data="ratio_16:9")],
        [InlineKeyboardButton("📷 1:1 Instagram Feed", callback_data="ratio_1:1")],
        [InlineKeyboardButton("⏱️ 5 detik", callback_data="dur_5")],
        [InlineKeyboardButton("⏱️ 10 detik", callback_data="dur_10")],
        [InlineKeyboardButton("⏱️ 15 detik", callback_data="dur_15")],
        [InlineKeyboardButton("🚀 GENERATE SEKARANG!", callback_data="generate_now")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    model_display = context.user_data.get('model_display', 'Agnes Video 2.0')
    ratio_display = context.user_data.get('ratio_display', 'Belum pilih')
    dur_status = context.user_data.get('duration', 'Belum pilih')
    update.message.reply_text(
        f"📝 **Prompt:** {prompt[:150]}...\n\n"
        f"📌 **Pilihan Anda:**\n"
        f"🎯 Model: {model_display}\n"
        f"📐 Ukuran: {ratio_display}\n"
        f"⏱️ Durasi: {dur_status}\n\n"
        "**Pilih opsi di bawah, lalu klik GENERATE!**",
        reply_markup=reply_markup
    )

def button_callback(update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    if 'model' not in context.user_data:
        context.user_data['model'] = "agnes-video-v2.0"
        context.user_data['model_display'] = "Agnes Video 2.0"
    if data == "ratio_9:16":
        context.user_data['ratio'] = "9:16"
        context.user_data['ratio_display'] = "9:16 (TikTok/Reels/IG)"
        context.user_data['width'] = 1088
        context.user_data['height'] = 1920
    elif data == "ratio_16:9":
        context.user_data['ratio'] = "16:9"
        context.user_data['ratio_display'] = "16:9 (YouTube/FB)"
        context.user_data['width'] = 1920
        context.user_data['height'] = 1088
    elif data == "ratio_1:1":
        context.user_data['ratio'] = "1:1"
        context.user_data['ratio_display'] = "1:1 (Instagram Feed)"
        context.user_data['width'] = 1088
        context.user_data['height'] = 1088
    elif data == "dur_5":
        context.user_data['duration'] = 5
    elif data == "dur_10":
        context.user_data['duration'] = 10
    elif data == "dur_15":
        context.user_data['duration'] = 15
    elif data == "generate_now":
        required = ['ratio', 'duration']
        if not all(k in context.user_data for k in required):
            query.edit_message_text(
                "⚠️ **Pilih dulu semua opsi:**\n"
                "- Ukuran (9:16 / 16:9 / 1:1)\n"
                "- Durasi (5 / 10 / 15 detik)"
            )
            return
        generate_video_process(query, context)
        return
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('ratio') == '9:16' else '⬜'} 9:16 TikTok/Reels/IG", 
            callback_data="ratio_9:16"
        )],
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('ratio') == '16:9' else '⬜'} 16:9 YouTube/FB/Landscape", 
            callback_data="ratio_16:9"
        )],
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('ratio') == '1:1' else '⬜'} 1:1 Instagram Feed", 
            callback_data="ratio_1:1"
        )],
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('duration') == 5 else '⬜'} 5 detik", 
            callback_data="dur_5"
        )],
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('duration') == 10 else '⬜'} 10 detik", 
            callback_data="dur_10"
        )],
        [InlineKeyboardButton(
            f"{'✅' if context.user_data.get('duration') == 15 else '⬜'} 15 detik", 
            callback_data="dur_15"
        )],
        [InlineKeyboardButton("🚀 GENERATE SEKARANG!", callback_data="generate_now")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    ratio_display = context.user_data.get('ratio_display', 'Belum pilih')
    dur_status = context.user_data.get('duration', 'Belum pilih')
    query.edit_message_text(
        f"📝 **Prompt:** {context.user_data.get('prompt', '')[:150]}...\n\n"
        f"📌 **Pilihan Anda:**\n"
        f"🎯 Model: Agnes Video 2.0\n"
        f"📐 Ukuran: {ratio_display}\n"
        f"⏱️ Durasi: {dur_status}\n\n"
        "**Pilih opsi di bawah, lalu klik GENERATE!**",
        reply_markup=reply_markup
    )

def generate_video_process(query, context):
    query.edit_message_text(
        "🎬 Sedang membuat video...\n"
        "Mohon tunggu 3-5 menit.\n"
        "⏳ Jangan kirim pesan lain sampai selesai!"
    )
    try:
        model = context.user_data.get('model', 'agnes-video-v2.0')
        duration = context.user_data.get('duration', 5)
        width = context.user_data.get('width', 1152)
        height = context.user_data.get('height', 768)
        prompt = context.user_data.get('prompt', '')
        image_path = context.user_data.get('photo_path')
        ratio_display = context.user_data.get('ratio_display', '9:16')
        result = generate_video(
            prompt=prompt,
            image_path=image_path,
            model=model,
            duration=duration,
            width=width,
            height=height
        )
        if os.path.exists(image_path):
            os.remove(image_path)
        context.user_data.clear()
        if result.get('success'):
            video_url = result.get('video_url')
            keyboard = [[InlineKeyboardButton("📥 Download Video", url=video_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.message.reply_video(
                video_url,
                caption="🎉 **Video selesai!**\n\n"
                        f"📝 Prompt: {prompt[:100]}...\n"
                        f"🎯 Model: Agnes Video 2.0\n"
                        f"📐 Ukuran: {ratio_display}\n"
                        f"⏱️ Durasi: {duration} detik\n\n"
                        "Klik tombol di bawah untuk download.",
                reply_markup=reply_markup
            )
        else:
            error_msg = result.get('error', 'Unknown error')
            query.message.reply_text(
                f"❌ Gagal membuat video:\n{error_msg}\n\n"
                "Coba lagi nanti atau gunakan deskripsi yang berbeda."
            )
    except Exception as e:
        logger.error(f"Error generate: {e}")
        query.message.reply_text(f"❌ Terjadi error:\n{str(e)}")

def cancel(update, context):
    if context.user_data.get('photo_path'):
        try:
            if os.path.exists(context.user_data['photo_path']):
                os.remove(context.user_data['photo_path'])
        except:
            pass
    context.user_data.clear()
    update.message.reply_text("🔄 Proses dibatalkan.")

# ========== MAIN ==========
def main():
    try:
        updater = Updater(token=BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("cancel", cancel))
        dp.add_handler(MessageHandler(Filters.PHOTO, handle_photo))
        dp.add_handler(MessageHandler(Filters.TEXT & ~Filters.COMMAND, handle_text))
        dp.add_handler(CallbackQueryHandler(generate_button, pattern="^generate$"))
        dp.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
        dp.add_handler(CallbackQueryHandler(button_callback))
        logger.info("🤖 Bot sedang berjalan...")
        print("🤖 Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error main: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
