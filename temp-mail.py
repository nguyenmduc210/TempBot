import json
import os
import random
import string
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

# ====== CONFIG ======
BOT_TOKEN = "8323833507:AAE98fZd-0Z00FRoSRacYgq7V9QpnW2_Ocw"
DATA_FILE = "mails.json"
MAIL_TM_API = "https://api.mail.tm"

# State cho ConversationHandler (note)
WAITING_NOTE = 1

# ====== STORAGE ======
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_mails(user_id):
    data = load_data()
    return data.get(str(user_id), [])

def set_user_mails(user_id, mails):
    data = load_data()
    data[str(user_id)] = mails
    save_data(data)

# ====== MAIL.TM API ======
def get_domain():
    r = requests.get(f"{MAIL_TM_API}/domains", timeout=15)
    r.raise_for_status()
    domains = r.json().get("hydra:member", [])
    if not domains:
        raise RuntimeError("Không lấy được domain từ mail.tm")
    return domains[0]["domain"]

def rand_str(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def create_account():
    domain = get_domain()
    address = f"{rand_str(10)}@{domain}"
    password = rand_str(14)
    r = requests.post(
        f"{MAIL_TM_API}/accounts",
        json={"address": address, "password": password},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Tạo mail lỗi: {r.status_code} - {r.text}")
    return address, password

def get_token(address, password):
    r = requests.post(
        f"{MAIL_TM_API}/token",
        json={"address": address, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]

def list_messages(token):
    r = requests.get(
        f"{MAIL_TM_API}/messages",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("hydra:member", [])

def get_message_detail(token, msg_id):
    r = requests.get(
        f"{MAIL_TM_API}/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

# ====== UI HELPERS ======
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tạo mail mới", callback_data="new_mail")],
        [InlineKeyboardButton("📬 Danh sách mail", callback_data="list_mails")],
    ])

def mails_list_kb(mails):
    kb = []
    for i, m in enumerate(mails):
        note = f" | {m['note']}" if m.get("note") else ""
        label = f"{m['address']}{note}"
        if len(label) > 60:
            label = label[:57] + "..."
        kb.append([InlineKeyboardButton(label, callback_data=f"open_{i}")])
    kb.append([InlineKeyboardButton("⬅️ Menu chính", callback_data="menu")])
    return InlineKeyboardMarkup(kb)

def mail_detail_kb(idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Check hòm thư", callback_data=f"check_{idx}")],
        [InlineKeyboardButton("📝 Sửa note", callback_data=f"note_{idx}")],
        [InlineKeyboardButton("🗑 Xóa mail", callback_data=f"del_{idx}")],
        [InlineKeyboardButton("⬅️ Quay lại list", callback_data="list_mails")],
    ])

def back_to_mail_kb(idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Quay lại mail", callback_data=f"open_{idx}")],
        [InlineKeyboardButton("📬 Danh sách mail", callback_data="list_mails")],
    ])

# ====== HANDLERS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Temp Mail Bot* (mail.tm)\n\nChọn chức năng:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )

async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("👋 *Temp Mail Bot*\n\nChọn chức năng:",
                              parse_mode="Markdown", reply_markup=main_menu_kb())

async def new_mail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Đang tạo mail...")
    try:
        address, password = create_account()
    except Exception as e:
        await q.edit_message_text(f"❌ Lỗi tạo mail: {e}", reply_markup=main_menu_kb())
        return

    mails = get_user_mails(q.from_user.id)
    mails.append({"address": address, "password": password, "note": ""})
    set_user_mails(q.from_user.id, mails)

    text = (
        f"✅ *Đã tạo mail mới*\n\n"
        f"📧 `{address}`\n"
        f"🔑 `{password}`\n\n"
        f"Đã lưu tự động."
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())

async def list_mails_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mails = get_user_mails(q.from_user.id)
    if not mails:
        await q.edit_message_text("📭 Chưa có mail nào. Hãy tạo mail mới.",
                                  reply_markup=main_menu_kb())
        return
    await q.edit_message_text(
        f"📬 *Danh sách mail* ({len(mails)}):\nChọn mail để xem chi tiết.",
        parse_mode="Markdown",
        reply_markup=mails_list_kb(mails),
    )

async def open_mail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_", 1)[1])
    mails = get_user_mails(q.from_user.id)
    if idx >= len(mails):
        await q.edit_message_text("❌ Không tìm thấy mail.", reply_markup=main_menu_kb())
        return
    m = mails[idx]
    note = m.get("note") or "(chưa có note)"
    text = (
        f"📧 *Mail*: `{m['address']}`\n"
        f"🔑 *Pass*: `{m['password']}`\n"
        f"📝 *Note*: {note}"
    )
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=mail_detail_kb(idx))

async def check_mail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Đang check...")
    idx = int(q.data.split("_", 1)[1])
    mails = get_user_mails(q.from_user.id)
    if idx >= len(mails):
        await q.edit_message_text("❌ Không tìm thấy mail.", reply_markup=main_menu_kb())
        return
    m = mails[idx]
    try:
        token = get_token(m["address"], m["password"])
        msgs = list_messages(token)
    except Exception as e:
        await q.edit_message_text(f"❌ Lỗi check mail: {e}",
                                  reply_markup=back_to_mail_kb(idx))
        return

    if not msgs:
        await q.edit_message_text(
            f"📭 `{m['address']}`\n\nHòm thư trống.",
            parse_mode="Markdown",
            reply_markup=back_to_mail_kb(idx),
        )
        return

    lines = [f"📬 *{m['address']}* — {len(msgs)} thư:\n"]
    for i, msg in enumerate(msgs[:10], 1):
        sender = msg.get("from", {}).get("address", "?")
        subject = msg.get("subject", "(no subject)")
        intro = msg.get("intro", "")
        lines.append(f"*{i}.* ✉️ From: `{sender}`\n   📌 {subject}\n   _{intro}_\n")

    # Lấy chi tiết thư mới nhất
    try:
        detail = get_message_detail(token, msgs[0]["id"])
        body = detail.get("text") or ""
        if body:
            lines.append("\n──── *Nội dung thư mới nhất* ────\n")
            lines.append(body[:1500])
    except Exception:
        pass

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n...(đã cắt)"
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=back_to_mail_kb(idx))

async def del_mail_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Đã xóa")
    idx = int(q.data.split("_", 1)[1])
    mails = get_user_mails(q.from_user.id)
    if idx < len(mails):
        removed = mails.pop(idx)
        set_user_mails(q.from_user.id, mails)
        await q.edit_message_text(f"🗑 Đã xóa `{removed['address']}`",
                                  parse_mode="Markdown",
                                  reply_markup=main_menu_kb())
    else:
        await q.edit_message_text("❌ Không tìm thấy mail.", reply_markup=main_menu_kb())

# ====== NOTE CONVERSATION ======
async def note_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_", 1)[1])
    context.user_data["note_idx"] = idx
    mails = get_user_mails(q.from_user.id)
    current = mails[idx].get("note", "") if idx < len(mails) else ""
    await q.edit_message_text(
        f"📝 Gửi nội dung note cho mail này.\n"
        f"Note hiện tại: _{current or '(trống)'}_\n\n"
        f"Gửi `-` để xóa note.\nGửi /cancel để hủy.",
        parse_mode="Markdown",
    )
    return WAITING_NOTE

async def note_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("note_idx")
    if idx is None:
        return ConversationHandler.END
    mails = get_user_mails(update.effective_user.id)
    if idx >= len(mails):
        await update.message.reply_text("❌ Mail không tồn tại.", reply_markup=main_menu_kb())
        return ConversationHandler.END
    text = update.message.text.strip()
    mails[idx]["note"] = "" if text == "-" else text
    set_user_mails(update.effective_user.id, mails)
    await update.message.reply_text(
        f"✅ Đã cập nhật note cho `{mails[idx]['address']}`",
        parse_mode="Markdown",
        reply_markup=mail_detail_kb(idx),
    )
    return ConversationHandler.END

async def note_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Đã hủy.", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ====== MAIN ======
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    note_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(note_start, pattern=r"^note_\d+$")],
        states={
            WAITING_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, note_receive)],
        },
        fallbacks=[CommandHandler("cancel", note_cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(note_conv)
    app.add_handler(CallbackQueryHandler(menu_cb, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(new_mail_cb, pattern=r"^new_mail$"))
    app.add_handler(CallbackQueryHandler(list_mails_cb, pattern=r"^list_mails$"))
    app.add_handler(CallbackQueryHandler(open_mail_cb, pattern=r"^open_\d+$"))
    app.add_handler(CallbackQueryHandler(check_mail_cb, pattern=r"^check_\d+$"))
    app.add_handler(CallbackQueryHandler(del_mail_cb, pattern=r"^del_\d+$"))

    print("Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()