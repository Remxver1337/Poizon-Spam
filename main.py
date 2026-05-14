# Временный код для получения file_id
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

TOKEN = "8255139931:AAFA2Bti_ERq1x1Z_QRyKsPK6IpXZ9bFi7U"

async def get_file_id(update: Update, context):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"file_id:\n`{file_id}`", parse_mode="Markdown")
    elif update.message.document:
        await update.message.reply_text(f"file_id:\n`{update.message.document.file_id}`", parse_mode="Markdown")

app = Application.builder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, get_file_id))
print("Бот запущен. Отправьте ему фото.")
app.run_polling()