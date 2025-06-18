# -*- coding: utf-8 -*-

# -------------------------------------------------------------------
#          بوت إعادة نشر الوظائف - إصدار جاهز للنشر
# -------------------------------------------------------------------
#  هذا الإصدار آمن للنشر على الاستضافة، حيث يقرأ المعلومات
#  الحساسة من متغيرات البيئة بدلاً من كتابتها مباشرة.
# -------------------------------------------------------------------

import logging
import json
import random
import os
import sys
from datetime import timedelta, datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- الإعدادات الأساسية (سيتم قراءتها من متغيرات البيئة) ---

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID_STR = os.environ.get("ADMIN_USER_ID")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID")

# التحقق من وجود المتغيرات الأساسية
if not all([BOT_TOKEN, ADMIN_USER_ID_STR, TARGET_CHANNEL_ID]):
    logging.error("خطأ: بعض متغيرات البيئة غير موجودة (BOT_TOKEN, ADMIN_USER_ID, TARGET_CHANNEL_ID).")
    sys.exit(1)

try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
except ValueError:
    logging.error("خطأ: قيمة ADMIN_USER_ID يجب أن تكون رقماً صحيحاً.")
    sys.exit(1)


# --- إعدادات إضافية (يمكن تركها كما هي) ---

# تحديد مسار قاعدة البيانات بناءً على بيئة التشغيل (للتوافق مع Render)
DATA_DIR = os.environ.get('RENDER_DISK_PATH', '.')
JOBS_DB_FILE = os.path.join(DATA_DIR, "scheduled_jobs.json")

RANDOM_HOUR_START = 9
RANDOM_HOUR_END = 23
POSTING_DURATION_DAYS = 14
# -----------------------------------------------------------


# إعداد تسجيل الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_jobs():
    """تحميل الوظائف المجدولة من ملف JSON."""
    logger.info(f"Loading jobs from: {JOBS_DB_FILE}")
    try:
        with open(JOBS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_jobs(jobs_data):
    """حفظ الوظائف المجدولة في ملف JSON."""
    logger.info(f"Saving jobs to: {JOBS_DB_FILE}")
    try:
        with open(JOBS_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(jobs_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to save jobs file: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة ترحيبية عند بدء المحادثة مع البوت."""
    await update.message.reply_text(
        "أهلاً بك! أنا بوت إعادة نشر الوظائف.\n\n"
        "الأوامر المتاحة للمسؤول:\n"
        "/feature [نص الوظيفة] - لنشر وظيفة فوراً وجدولتها.\n"
        "/listjobs - لعرض قائمة الوظائف ومواعيد النشر القادمة.\n"
        "/stopjob [ID] - لإيقاف نشر وظيفة مجدولة."
    )


async def feature_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إضافة وظيفة مميزة، نشرها فوراً، وحساب جدول زمني دقيق لإعادة النشر."""
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return

    command_entity = next((e for e in update.message.entities if e.type == 'bot_command'), None)
    if not command_entity or not update.message.text:
        await update.message.reply_text("حدث خطأ في قراءة نص الوظيفة.")
        return
        
    job_text = update.message.text[command_entity.length:].strip()
    if not job_text:
        await update.message.reply_text("الرجاء إرسال نص الوظيفة مع الأمر.")
        return

    try:
        await context.bot.send_message(
            chat_id=TARGET_CHANNEL_ID, 
            text=job_text, 
            disable_web_page_preview=True
        )
        logger.info(f"تم نشر الوظيفة الجديدة ({update.message.message_id}) فوراً في القناة.")
    except Exception as e:
        logger.error(f"فشل النشر الفوري للوظيفة ({update.message.message_id}): {e}")
        await update.message.reply_text(f"⚠️ فشل النشر الفوري في القناة. يرجى التحقق من صلاحيات البوت. الخطأ: {e}")
        return

    job_id = str(update.message.message_id)
    jobs_data = load_jobs()
    repost_schedule = []
    today = datetime.now()
    for i in range(1, POSTING_DURATION_DAYS):
        schedule_day = today + timedelta(days=i)
        random_hour = random.randint(RANDOM_HOUR_START, RANDOM_HOUR_END)
        random_minute = random.randint(0, 59)
        schedule_dt = schedule_day.replace(hour=random_hour, minute=random_minute, second=0, microsecond=0)
        repost_schedule.append(schedule_dt.strftime('%Y-%m-%d %H:%M:%S'))

    jobs_data[job_id] = {
        "text": job_text,
        "repost_schedule": sorted(repost_schedule),
        "status": "active"
    }
    save_jobs(jobs_data)

    await update.message.reply_text(
        f"✅ تم نشر الوظيفة وجدولة إعادة نشرها بنجاح!\n"
        f"استخدم /listjobs لمعرفة مواعيد النشر القادمة."
    )


async def list_active_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قائمة بالوظائف النشطة مع عرض جميع مواعيد النشر القادمة."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return

    jobs_data = load_jobs()
    active_jobs_messages = []
    for job_id, job_info in jobs_data.items():
        if job_info.get("status") == "active" and job_info.get("repost_schedule"):
            short_id = job_id[:6]
            schedule_list = job_info["repost_schedule"]
            schedule_display_list = [f"- {dt}" for dt in schedule_list]
            schedule_text = "\n".join(schedule_display_list)
            
            if not schedule_list:
                 schedule_text = "لا توجد مواعيد متبقية."

            message_part = (
                f"ID: {short_id}\n"
                f"النص: {job_info['text'][:50]}...\n"
                f"مواعيد إعادة النشر القادمة:\n{schedule_text}"
            )
            active_jobs_messages.append(message_part)

    if not active_jobs_messages:
        response_message = "لا توجد وظائف نشطة قيد إعادة النشر حالياً."
    else:
        response_message = "الوظائف قيد إعادة النشر حالياً:\n\n" + "\n---\n".join(active_jobs_messages)
    
    await update.message.reply_text(response_message)


async def stop_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف وظيفة مجدولة باستخدام الـ ID الخاص بها."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    
    if not context.args:
        await update.message.reply_text("الرجاء تحديد ID الوظيفة التي تريد إيقافها.\nمثال: /stopjob 123456")
        return

    short_id_to_stop = context.args[0]
    jobs_data = load_jobs()
    job_found = False
    for job_id, job_info in jobs_data.items():
        if job_id.startswith(short_id_to_stop) and job_info.get("status") == "active":
            job_info["status"] = "stopped"
            job_found = True
            save_jobs(jobs_data)
            await update.message.reply_text(f"✅ تم إيقاف إعادة نشر الوظيفة ذات الـ ID: {short_id_to_stop}.")
            logger.info(f"تم إيقاف الوظيفة {job_id} بواسطة المسؤول.")
            break
            
    if not job_found:
        await update.message.reply_text(f"لم يتم العثور على وظيفة نشطة بالـ ID: {short_id_to_stop}.")


async def check_and_repost_jobs(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تتحقق كل دقيقة من وجود وظائف حان وقت إعادة نشرها."""
    logger.debug("Running job checker...")
    now = datetime.now()
    jobs_data = load_jobs()
    data_changed = False

    for job_id, job_info in list(jobs_data.items()):
        if job_info.get("status") == "active" and job_info.get("repost_schedule"):
            if not job_info["repost_schedule"]:
                continue
                
            next_repost_str = job_info["repost_schedule"][0]
            next_repost_dt = datetime.strptime(next_repost_str, '%Y-%m-%d %H:%M:%S')

            if now >= next_repost_dt:
                logger.info(f"Found job {job_id} to repost at {next_repost_dt}.")
                try:
                    await context.bot.send_message(
                        chat_id=TARGET_CHANNEL_ID,
                        text=job_info["text"],
                        disable_web_page_preview=True
                    )
                    logger.info(f"تمت إعادة نشر الوظيفة {job_id} بنجاح.")
                    
                    job_info["repost_schedule"].pop(0)
                    if not job_info["repost_schedule"]:
                        job_info["status"] = "expired"
                        logger.info(f"انتهت جميع مواعيد إعادة نشر الوظيفة {job_id}.")
                    
                    data_changed = True

                except Exception as e:
                    logger.error(f"فشل إعادة نشر الوظيفة {job_id}: {e}")

    if data_changed:
        save_jobs(jobs_data)


def main() -> None:
    """الدالة الرئيسية لتشغيل البوت وإعداد المهام المجدولة."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    job_queue = application.job_queue
    job_queue.run_repeating(check_and_repost_jobs, interval=60, first=10)
    logger.info("تم جدولة مراقب الوظائف ليعمل كل 60 ثانية.")

    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("feature", feature_job))
    application.add_handler(CommandHandler("listjobs", list_active_jobs))
    application.add_handler(CommandHandler("stopjob", stop_job))

    print("البوت قيد التشغيل... (بنمط الجدولة الدقيقة)")
    application.run_polling()


if __name__ == "__main__":
    main()
