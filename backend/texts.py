"""Uzbek Latin copy shared by the bot and the API."""

from html import escape

from backend.constants import EXTENSION_PRICE_UZS, PREMIUM_DAYS, PREMIUM_PRICE_UZS
from backend.utils.formatting import as_utc, format_duration, format_uzs

A = "\u2018"  # Uzbek Latin modifier apostrophe

BTN_UPLOAD = "✉️ Fayl yuborish"
BTN_FILES = "📁 Mening fayllarim"
BTN_BALANCE = "👤 Hisobim"
BTN_PREMIUM = f"💎 Obuna / To{A}lov"
BTN_REFERRAL = "👥 Referal"
BTN_PAYMENT = f"💳 To{A}lov"
BTN_HELP = "ℹ️ Yordam"
BTN_ADMIN = "👑 Admin panel"
BTN_CARD = "💳 Karta orqali"
BTN_BACK = "⬅️ Orqaga"

RECEIPT_ACCEPTED = (
    f"📥 To{A}lov chekingiz qabul qilindi.\n\n"
    f"⏳ To{A}lovni tekshirish 30 daqiqagacha yoki undan ko{A}proq vaqt olishi mumkin.\n\n"
    "Tasdiqlangach, sizga avtomatik xabar yuboramiz."
)


def access_pill(subscription_status: str, expires_at, now) -> str:
    expires = as_utc(expires_at)
    remaining = expires - as_utc(now)
    date = expires.strftime("%d.%m.%Y")
    seconds = int(remaining.total_seconds())
    if seconds <= 0 or subscription_status == "expired":
        return "Obuna muddati tugagan"
    days = seconds // 86400
    left = f"{days} kun" if days >= 1 else format_duration(remaining)
    phrase = f"{left} qoldi ({date} gacha)"
    if subscription_status == "trial":
        return f"Bepul sinov: {phrase}"
    if subscription_status == "active":
        return f"Premium: {phrase}"
    return phrase


def payment_card_text(card_number: str, card_name: str) -> str:
    if not card_number or not card_name:
        return f"To{A}lov kartasi hozir sozlanmagan. Administrator bilan bog{A}laning."
    return (
        f"🏦 Karta orqali to{A}lov\n\n"
        "💎 Oylik obuna:\n"
        f"{format_uzs(PREMIUM_PRICE_UZS)} / {PREMIUM_DAYS} kun\n\n"
        "⏰ 1 kun fayl uzaytirish:\n"
        f"{format_uzs(EXTENSION_PRICE_UZS)}\n\n"
        "💳 Karta:\n"
        f"{card_number}\n\n"
        f"👤 {card_name}\n\n"
        f"To{A}lovdan so{A}ng chek (skrinshot)ni shu chatga yuboring.\n\n"
        "Admin tasdiqlaydi."
    )


def welcome_text(name: str, subscription_status: str, expires_at, now) -> str:
    return (
        f"👋 Salom, {escape(name)}!\n\n"
        "Bu bot istalgan hajmdagi faylni yuklab, sizga xavfsiz link beradi. "
        "Linkni yuborsangiz, qabul qiluvchi faylni Telegram ichida yuklab oladi.\n\n"
        f"🎁 {access_pill(subscription_status, expires_at, now)}\n\n"
        "Boshlash uchun pastdagi tugmani bosing 👇"
    )


def balance_text(balance_uzs: int) -> str:
    return f"💰 Balans:\n{format_uzs(balance_uzs)}\n\nBalans fayl muddatini uzaytirish uchun ishlatiladi."


def premium_text(subscription_status: str, expires_at, now) -> str:
    return (
        "💎 Premium\n\n"
        f"Narxi: {format_uzs(PREMIUM_PRICE_UZS)} / {PREMIUM_DAYS} kun.\n"
        f"Qolgan vaqtga {PREMIUM_DAYS} kun qo‘shiladi. "
        "Muddat tugagan bo‘lsa, yangi 30 kun hozirdan boshlanadi.\n\n"
        f"🎁 {access_pill(subscription_status, expires_at, now)}"
    ).replace("‘", A)


def card_charge_text(amount: int, card_number: str, card_name: str) -> str:
    card = f"{card_number} {card_name}".strip()
    if not card_number or not card_name:
        card = f"To{A}lov kartasi hozir sozlanmagan. Administrator bilan bog{A}laning."
    return (
        f"💳 Karta orqali to{A}lov\n\n"
        f"Summa: {format_uzs(amount)}\n\n"
        f"{card}\n\n"
        f"To{A}lovdan so{A}ng chek (skrinshot)ni shu chatga yuboring — admin tasdiqlaydi."
    )


def account_text(telegram_id: int, subscription_status: str, expires_at, now, invited: int, files: int, balance_uzs: int) -> str:
    return (
        "👤 Hisobim\n\n"
        f"ID: {telegram_id}\n"
        f"🎁 {access_pill(subscription_status, expires_at, now)}\n"
        f"Taklif qilinganlar: {invited}\n"
        f"Fayllaringiz: {files}\n"
        f"💰 Balans: {format_uzs(balance_uzs)}"
    )


def file_ready_text(name: str, size_text: str, share_url: str, page_url: str, gofile_url: str, promo_username: str = "") -> str:
    gofile = gofile_url or "—"
    text = (
        "<b>✅ Fayl tayyor!</b>\n\n"
        f"📄 {escape(name)} ({escape(size_text)})\n\n"
        "🔗 Telegram ichida ochiladigan link:\n"
        f"{escape(share_url)}\n\n"
        "💻 Kompyuterda ochish:\n"
        f"{escape(page_url)}\n\n"
        "🌐 Gofile: "
        f"{escape(gofile)}\n\n"
        "Birinchi linkni yuboring — qabul qiluvchi faylni Telegram ichida yuklab oladi."
    )
    if promo_username:
        text += (
            "\n\n🚀 Katta fayllarni oson yuboring!\n"
            "Istalgan hajmdagi faylni yuklab, xavfsiz link oling — tez va qulay.\n"
            f"👉 https://t.me/{escape(promo_username)}"
        )
    return text


def referral_text(invited: int, bonus_days: int, link: str) -> str:
    return (
        "👥 Referal\n\n"
        "🎁 Har bir yangi odam uchun:\n"
        "+1 kun\n\n"
        "👤 Taklif qilinganlar:\n"
        f"{invited} ta\n\n"
        "🎁 Olingan bonus:\n"
        f"{bonus_days} kun\n\n"
        "🔗 Sizning referal havolangiz:\n\n"
        f"{link}"
    )


def help_text() -> str:
    return (
        "ℹ️ Yordam\n\n"
        "📤 Fayl yuklash\n"
        "Mini ilovani oching va faylni tanlang. Katta fayl server xotirasiga to‘liq yig‘ilmaydi "
        "va GoFile xizmatiga oqim orqali yuboriladi.\n\n"
        "⏳ Fayl muddati\n"
        "Har bir yangi fayl 24 soat saqlanadi. Muddat tugagach fayl yopiladi.\n\n"
        "⏰ Uzaytirish\n"
        f"1 kun qo‘shish narxi {format_uzs(EXTENSION_PRICE_UZS)}. "
        "Yangi vaqt qolgan muddat ustiga qo‘shiladi, 24 soatga qaytarilmaydi.\n\n"
        "💎 Premium\n"
        f"{format_uzs(PREMIUM_PRICE_UZS)} / {PREMIUM_DAYS} kun. "
        "Agar obuna hali tugamagan bo‘lsa, 30 kun shu muddatga qo‘shiladi.\n\n"
        "🆓 Bepul muddat\n"
        "Yangi foydalanuvchi bir marta 7 kun oladi.\n\n"
        "👥 Referal\n"
        "Har bir yangi odam uchun +1 kun. Bonus mavjud tugash sanasiga qo‘shiladi.\n\n"
        "💰 Hamyon\n"
        "Balans faqat fayl uzaytirish uchun sarflanadi.\n\n"
        "💳 To‘lov\n"
        "Kartaga o‘ting va chek skrinshotini shu chatga yuboring. "
        "To‘lov admin ko‘rib chiqquncha kutilish holatida turadi. "
        "30 daqiqa faqat taxminiy ko‘rib chiqish vaqti — to‘lov o‘zi bekor bo‘lmaydi.\n\n"
        "👑 Tasdiqlash\n"
        "To‘lovni faqat administrator tasdiqlaydi yoki rad etadi. Avtomatik to‘lov yo‘q.\n\n"
        "Savol bo‘lsa, shu botga yozing."
    ).replace("‘", A)


def insufficient_balance(current: int, required: int, short: int) -> str:
    return (
        "❌ Balansingiz yetarli emas.\n\n"
        f"💰 Joriy balans: {format_uzs(current)}\n"
        f"⏰ Kerak: {format_uzs(required)}\n"
        f"➕ Yetishmayapti: {format_uzs(short)}"
    )


def extend_confirm(price: int, balance: int) -> str:
    return (
        "⏰ Faylni 1 kunga uzaytirish\n\n"
        f"💰 Narx: {format_uzs(price)}\n"
        f"💳 Balans: {format_uzs(balance)}"
    )


def upload_success(name: str, size_text: str) -> str:
    return (
        "✅ Fayl muvaffaqiyatli yuklandi!\n\n"
        "📄 Fayl:\n"
        f"{name}\n\n"
        "📦 Hajmi:\n"
        f"{size_text}\n\n"
        "⏳ Amal qilish muddati:\n"
        "24 soat"
    )


def wallet_topup_approved(added: int, balance: int) -> str:
    return (
        "✅ Balansingiz to‘ldirildi!\n\n"
        "💰 Qo‘shildi:\n"
        f"{format_uzs(added)}\n\n"
        "💳 Joriy balans:\n"
        f"{format_uzs(balance)}"
    ).replace("‘", A)


def premium_approved() -> str:
    return (
        "✅ To‘lovingiz tasdiqlandi!\n\n"
        "💎 Premium obuna faollashtirildi.\n\n"
        "➕ 30 kun qo‘shildi."
    ).replace("‘", A)


def payment_rejected() -> str:
    return (
        "❌ To‘lovingiz rad etildi.\n\n"
        "Agar bu xato bo‘lsa, qayta chek yuboring."
    ).replace("‘", A)


def storage_warning(percent: int) -> str:
    return f"⚠️ Storage ogohlantirish\n\nStorage foydalanish {percent}% ga yetdi."


def storage_blocked() -> str:
    return (
        "🛑 Yangi fayl yuklash vaqtincha to‘xtatildi.\n\n"
        "Storage xavfsizlik limiti yetdi."
    ).replace("‘", A)


def delete_confirm() -> str:
    return "⚠️ Faylni o‘chirishni tasdiqlaysizmi?".replace("‘", A)


def referral_reward_notice(remaining) -> str:
    return (
        "🎁 Yangi referal!\n\n"
        "+1 kun qo‘shildi.\n"
        f"⏳ Qolgan vaqt: {format_duration(remaining)}"
    ).replace("‘", A)


UPLOAD_ERROR = "❌ Faylni yuklashda xatolik yuz berdi."
SUBSCRIPTION_REQUIRED = (
    "Obuna muddati tugagan. Fayl yuklash uchun Premium oling yoki referal orqali kun qo‘shing."
).replace("‘", A)
CHOOSE_PAYMENT = f"Avval to{A}lov turini va summani tanlang."
MSG_FILE_NOT_FOUND = "Fayl topilmadi."
MSG_FILE_EXPIRED = "Fayl muddati tugagan."
CONFIRM_REQUIRED = "Tasdiqlash kerak."
UPLOAD_STOPPED = storage_blocked()
FILE_TOO_LARGE = "Fayl hajmi ruxsat etilgan chegaradan katta."
GOFILE_NOT_CONFIGURED = "Fayl saqlash xizmati hozir sozlanmagan."
