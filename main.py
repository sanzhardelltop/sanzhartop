import os
from flask import Flask

app = Flask(__name__)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Default to 5000 if PORT not set
    app.run(host='0.0.0.0', port=port)
    import os
import re
import time
import traceback
from typing import Optional

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# --- Настройки ---
TOKEN = os.environ.get(
    "VK_TOKEN",
    "vk1.a.yJNtmSw2-G_BeHBvomh_VdgYfjJb_844uFDNBrwSVmcCi1fPUtJ3U2XdPjNyC-FWWqko6bvjBldYpC5dJL9WINOPS16-T_7cW2YEWMHoX1hq8R4uulyqYAvNvFvhZ148C4gjmFgjNZvM0RGz1TZwRGw0lET3TC5wO5916DiS77z7q82CIwFbI_MrGk3qnnHpoopp9vdRZXOA0GjsnwnLBg",
)
OWNER_1 = os.environ.get("VK_OWNER_1", "stepkozdez")
OWNER_0 = os.environ.get("VK_OWNER_0", "lev3438")

owner_cache = {}

def resolve_user_id(owner):
    """Resolve a VK user identifier.

    If owner is numeric (or numeric string), returns int.
    Otherwise, calls VK API to resolve screen name to user id.
    """
    if owner is None:
        return None

    if isinstance(owner, int):
        return owner

    if isinstance(owner, str) and owner.isdigit():
        return int(owner)

    if owner in owner_cache:
        return owner_cache[owner]

    try:
        res = vk.users.get(user_ids=owner)
        if res and isinstance(res, list) and len(res) > 0:
            uid = res[0].get("id")
            owner_cache[owner] = uid
            return uid
    except Exception as e:
        print(f"Ошибка resolve_user_id для {owner}: {e}")

    return None

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

user_data = {}

# Приложения (заявки) хранится в памяти (не сохраняется между перезапусками бота)
# app_id -> application dict
applications = {}
# Индексы для быстрого поиска
applications_by_user = {}  # user_id -> [app_id]
applications_by_owner = {}  # owner_id -> [app_id]
next_application_id = 1

# Срок жизни заявки (на обработку) — 7 дней
APPLICATION_EXPIRY_SECONDS = 7 * 24 * 60 * 60

# Для баг-репортов (отправляется владельцу)
BUG_OWNER = os.environ.get("VK_BUG_OWNER", "sanzhardell")

def make_main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("📄 Отправить норму", color=VkKeyboardColor.PRIMARY)
    kb.add_button("🐞 Нашел баг", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("� Предложение", color=VkKeyboardColor.SECONDARY)
    kb.add_button("📋 Мои заявки", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("ℹ️ Помощь", color=VkKeyboardColor.SECONDARY)
    kb.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


def make_cancel_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button("❌ Отмена", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


def make_owner_response_keyboard(app_id: str):
    # Обычная клавиатура (не inline) работает гарантированно в любых клиентах VK.
    kb = VkKeyboard(one_time=False, inline=False)
    # Кнопки отправляют текст, который мы потом парсим (включаем ID заявки)
    kb.add_button(f"✅ Сделано #{app_id}", color=VkKeyboardColor.POSITIVE)
    kb.add_button(f"❌ Отказано #{app_id}", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


def _parse_owner_response(text: str):
    """Разбираем ответ владельца в формате +<id>, -<id>, или кнопок с ID."""
    if not text:
        return None, None
    text = text.strip()

    # Поддерживаем привычный формат +id / -id
    if text[0] in "+-":
        action = text[0]
        app_id = text[1:].strip()
        return action, app_id

    # Разбор по ключевым словам + ID
    app_id_match = re.search(r"(\d+)", text)
    if not app_id_match:
        return None, None
    app_id = app_id_match.group(1)
    lowered = text.lower()
    if "одобр" in lowered or "✅" in text or "сделано" in lowered:
        return "+", app_id
    if "откл" in lowered or "❌" in text or "отказано" in lowered:
        return "-", app_id
    return None, None

VK_LINK_RE = re.compile(r"https?://(m\.)?vk\.com/(wall(-?\d+_\d+)|club\d+|id\d+)(/.*)?$")


def is_valid_vk_link(text: str) -> bool:
    return bool(VK_LINK_RE.match(text.strip()))


def extract_vk_link(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    # Оставляем только ссылку, если пришло несколько слов
    parts = text.split()
    for part in parts:
        if is_valid_vk_link(part):
            return part
    return None


def _get_status_label(status: str, kind: str = None) -> str:
    if status == "pending":
        return "🟡 На рассмотрении"
    if status == "approved":
        if kind in ["bug", "improvement"]:
            return "🟢 Будет сделано"
        return "✅ Одобрено"
    if status == "rejected":
        if kind in ["bug", "improvement"]:
            return "❌ Отказано"
        return "❌ Отклонено"
    return status


def _format_app_summary(app: dict) -> str:
    app_type = app.get("type")
    status = _get_status_label(app.get("status", "pending"), kind=app_type)
    kind = "Норма" if app_type == "norma" else "Баг" if app_type == "bug" else "Предложение"
    server = app.get("data", {}).get("server")
    server_part = f" ({server})" if server else ""
    return f"[#{app['id']}] {kind}{server_part} — {status}"


def list_applications_for_user(user_id: int) -> str:
    app_ids = applications_by_user.get(user_id, [])
    if not app_ids:
        return "У тебя пока нет заявок."

    lines = ["Твои заявки:"]
    for app_id in app_ids:
        app = applications.get(app_id)
        if not app:
            continue
        lines.append(_format_app_summary(app))
    return "\n".join(lines)


def cleanup_old_applications():
    """Удаляем заявки старше APPLICATION_EXPIRY_SECONDS."""
    now = int(time.time())
    expired = []
    for app_id, app in list(applications.items()):
        if now - app.get("created_at", 0) > APPLICATION_EXPIRY_SECONDS:
            expired.append(app_id)

    for app_id in expired:
        app = applications.pop(app_id, None)
        if not app:
            continue
        user_id = app.get("user_id")
        owner_id = app.get("owner_id")
        if user_id in applications_by_user:
            applications_by_user[user_id] = [x for x in applications_by_user[user_id] if x != app_id]
            if not applications_by_user[user_id]:
                applications_by_user.pop(user_id, None)
        if owner_id in applications_by_owner:
            applications_by_owner[owner_id] = [x for x in applications_by_owner[owner_id] if x != app_id]
            if not applications_by_owner[owner_id]:
                applications_by_owner.pop(owner_id, None)


def list_applications_for_owner(owner_id: int) -> str:
    app_ids = applications_by_owner.get(owner_id, [])
    if not app_ids:
        return "У тебя пока нет назначенных заявок."

    lines = ["Заявки для тебя:"]
    for app_id in app_ids:
        app = applications.get(app_id)
        if not app:
            continue
        lines.append(_format_app_summary(app))
    lines.append("\nЧтобы принять/отклонить, ответь +<id> или -<id>.")
    return "\n".join(lines)


def _create_application(user_id: int, app_type: str, data: dict, owner_id: int) -> dict:
    global next_application_id
    app_id = str(next_application_id)
    next_application_id += 1
    app = {
        "id": app_id,
        "type": app_type,
        "status": "pending",
        "user_id": user_id,
        "owner_id": owner_id,
        "data": data,
        "created_at": int(time.time()),
    }
    applications[app_id] = app
    applications_by_user.setdefault(user_id, []).append(app_id)
    applications_by_owner.setdefault(owner_id, []).append(app_id)
    return app


def _send_app_to_owner(app: dict):
    owner_id = app.get("owner_id")
    if owner_id is None:
        return

    title = "Новая заявка"
    kind = app.get("type")
    if kind == "bug":
        title = "Новый баг-репорт"
    elif kind == "improvement":
        title = "Новое предложение по улучшению"

    info = app.get("data", {})
    if kind == "norma":
        msg = (
            f"{title} от {app.get('user_id')} (ID={app['id']}):\n"
            f"Nick: {info.get('nickname', '(не указано)')}\n"
            f"Должность: {info.get('position', '(не указано)')}\n"
            f"Ссылка: {info.get('proof', '(не указано)')}\n"
            f"Сделано: {info.get('done', '(не указано)')}\n"
            f"Сервер: {info.get('server', '(не указано)')}\n\n"
            "Ответь +<id> или -<id>."
        )
    elif kind == "bug":
        proof = info.get('proof')
        if not proof:
            proof = '(не указано)'

        msg = (
            f"{title} от {app.get('user_id')} (ID={app['id']}):\n"
            f"Что за баг: {info.get('description', '(не указано)')}\n"
            f"Где: {info.get('location', '(не указано)')}\n"
            f"Что хочет сделать: {info.get('desired', '(не указано)')}\n"
            f"Ссылка/скрин: {proof}\n\n"
            "Ответь кнопкой или +<id> / -<id>."
        )
    else:  # improvement
        msg = (
            f"{title} от {app.get('user_id')} (ID={app['id']}):\n"
            f"Что хотите добавить: {info.get('what', '(не указано)')}\n"
            f"Зачем это нужно: {info.get('why', '(не указано)')}\n"
            f"Информация: {info.get('details', '(не указано)')}\n\n"
            "Ответь кнопкой или +<id> / -<id>."
        )

    # Уведомляем основного владельца (BUG_OWNER), если он отличается
    recipients = [owner_id]
    bug_owner_id = resolve_user_id(BUG_OWNER)
    if bug_owner_id and bug_owner_id != owner_id:
        recipients.append(bug_owner_id)

    for rid in set(recipients):
        # Отправляем текст заявки, затем отдельное сообщение с клавиатурой, чтобы клавиатура точно появилась.
        send_message(rid, msg)
        send_message(rid, "Нажми кнопку ниже:", keyboard=make_owner_response_keyboard(app['id']))


def send_message(user_id, message, keyboard=None, attachment=None, forward_messages=None):
    # VK API требует int user_id (или numeric string) — но для бота лучше использовать peer_id.
    try:
        if isinstance(user_id, str) and user_id.isdigit():
            user_id = int(user_id)
    except Exception:
        pass

    # Сохраняем старый user_id в логике (для отладки)
    peer_id = user_id

    kwargs = {"peer_id": peer_id, "message": message, "random_id": get_random_id()}
    if keyboard:
        kwargs["keyboard"] = keyboard
    if attachment:
        kwargs["attachment"] = attachment
    if forward_messages:
        kwargs["forward_messages"] = forward_messages

    # Логирование для отладки (когда заявка не доходит или кнопки не видны)
    if "Новая заявка" in message or "Новый баг-репорт" in message:
        print(
            f"[DEBUG] send_message peer_id={peer_id} keyboard={'yes' if keyboard else 'no'} "
            f"message=({message[:80]}...)"
        )
        print(f"[DEBUG] kwargs={kwargs}")

    try:
        vk.messages.send(**kwargs)
    except Exception as e:
        # Логируем, но не ломаем работу бота
        print(f"Ошибка отправки сообщения peer_id={peer_id}: {e}")

def get_forward_id(event):
    # Попытка найти идентификатор сообщения в разных форматах VkEvent
    if hasattr(event, "message_id") and event.message_id:
        return event.message_id
    if hasattr(event, "message") and isinstance(event.message, dict):
        for key in ("id", "message_id", "conversation_message_id"):
            if key in event.message and event.message[key]:
                return event.message[key]
    if hasattr(event, "object") and isinstance(event.object, dict):
        for key in ("message_id", "id", "conversation_message_id"):
            if key in event.object and event.object[key]:
                return event.object[key]
    # Пробуем raw
    if hasattr(event, "raw") and isinstance(event.raw, dict):
        for key in ("message_id", "id", "conversation_message_id"):
            if key in event.raw and event.raw[key]:
                return event.raw[key]
    return None


def process_event(event):
    try:
        if event.type != VkEventType.MESSAGE_NEW or not event.to_me:
            return

        user_id = event.user_id
        cleanup_old_applications()
        incoming_text = (event.text or "").strip()
        text = incoming_text.lower()

        # --- Старт ---
        if text in ["/start", "/старт", "старт", "start", "начать", "/начать"]:
            send_message(
                user_id,
                "Добро пожаловать!\n\n"
                "Скачать игру: https://t.me/rolls_russia\n"
                "Владелец -- @sanzhardell\n\n"
                "1) Нажми кнопку \"📄 Отправить норму\" или \"🐞 Нашел баг\".\n"
                "2) Заполни форму (несколько вопросов).\n"
                "3) Получишь ответ здесь, и владелец сможет одобрить/отклонить.",
                keyboard=make_main_keyboard(),
            )
            return

        # --- Помощь ---
        if text in ["/help", "help", "помощь", "ℹ️ помощь"]:
            send_message(
                user_id,
                "Я помогу тебе отправить норму, баг-репорт или предложение по улучшению.\n\n"
                "1) Нажми кнопку \"📄 Отправить норму\", \"🐞 Нашел баг\" или \"💡 Предложение\".\n"
                "2) Ответь на вопросы.\n"
                "3) После отправки владелец получит твою заявку и сможет принять решение.\n\n"
                "Для статуса заявок нажми \"📋 Мои заявки\".\n"
                "После одобрения предложения ты получишь 50к донат рублей!",
                keyboard=make_main_keyboard(),
            )
            return

        # --- Мои заявки ---
        if text in ["/myapps", "/myapps", "/мои заявки", "мои заявки", "📋 мои заявки"]:
            send_message(user_id, list_applications_for_user(user_id), keyboard=make_main_keyboard())
            return

        # --- Начало нормы ---
        if text.startswith("/norma") or text in ["📄 отправить норму"]:
            user_data[user_id] = {"step": 1, "type": "norma", "data": {}}
            send_message(
                user_id,
                "1. Ваш Nickname:",
                keyboard=make_cancel_keyboard(),
            )
            return

        # --- Начало бага ---
        if text.startswith("/bug") or text in ["🐞 нашел баг", "нашел баг", "нашёл баг", "баг"]:
            user_data[user_id] = {"step": 1, "type": "bug", "data": {}}
            send_message(
                user_id,
                "1. Краткое описание бага:",
                keyboard=make_cancel_keyboard(),
            )
            return

        # --- Начало предложения по улучшению ---
        if text.startswith("/proposal") or text in ["💡 предложение", "предложение", "предложение по улучшению"]:
            user_data[user_id] = {"step": 1, "type": "improvement", "data": {}}
            send_message(
                user_id,
                "1. Что вы хотите добавить?",
                keyboard=make_cancel_keyboard(),
            )
            return

        # --- Шаги заполнения ---
        if user_id in user_data:
            data = user_data[user_id]
            step = data["step"]
            kind = data.get("type", "norma")

            # Отмена заполнения
            if text in ["/cancel", "cancel", "отмена", "❌ отмена"]:
                send_message(user_id, "Заполнение отменено.", keyboard=make_main_keyboard())
                del user_data[user_id]
                return

            # В любой момент можно посмотреть свои заявки
            if text in ["/myapps", "/myapps", "/мои заявки", "мои заявки", "📋 мои заявки"]:
                send_message(user_id, list_applications_for_user(user_id), keyboard=make_main_keyboard())
                return

            # Норма: собираем поля по шагам
            if kind == "norma":
                if step == 1:
                    data["data"]["nickname"] = incoming_text
                    data["step"] = 2
                    send_message(user_id, "2. Ваша должность:", keyboard=make_cancel_keyboard())
                elif step == 2:
                    data["data"]["position"] = incoming_text
                    data["step"] = 3
                    send_message(user_id, "3. Доказательства (ссылка на пост VK):", keyboard=make_cancel_keyboard())
                elif step == 3:
                    link = extract_vk_link(incoming_text)
                    if not link:
                        send_message(
                            user_id,
                            "Неверная ссылка. Отправь ссылку на пост, например: https://vk.com/wall-123456_7890",
                            keyboard=make_cancel_keyboard(),
                        )
                        return

                    data["data"]["proof"] = link
                    data["step"] = 4
                    send_message(user_id, "4. Что сделали:", keyboard=make_cancel_keyboard())
                elif step == 4:
                    data["data"]["done"] = incoming_text
                    data["step"] = 5
                    send_message(user_id, "5. Сервер (TVER = -1 / PERM = -2):", keyboard=make_cancel_keyboard())
                elif step == 5:
                    server_value = incoming_text.lower()
                    server_map = {
                        "-1": ("TVER", OWNER_0),
                        "tver": ("TVER", OWNER_0),
                        "1": ("TVER", OWNER_0),
                        "-2": ("PERM", OWNER_1),
                        "perm": ("PERM", OWNER_1),
                        "2": ("PERM", OWNER_1),
                    }
                    if server_value not in server_map:
                        send_message(user_id, "Неверный выбор. Напиши -1 (TVER) или -2 (PERM).", keyboard=make_cancel_keyboard())
                        return

                    server_label, owner_raw = server_map[server_value]
                    data["data"]["server"] = server_label

                    owner_id = resolve_user_id(owner_raw)
                    if owner_id is None:
                        print(f"Ошибка: не удалось получить numeric user_id для владельца (owner_raw={owner_raw})")
                        send_message(user_id, "Не удалось отправить заявку — проверь настройки OWNER_0/OWNER_1.")
                    else:
                        app = _create_application(user_id, "norma", data["data"], owner_id)
                        _send_app_to_owner(app)
                        send_message(user_id, "Заявка отправлена ✅", keyboard=make_main_keyboard())

                    del user_data[user_id]
                return

            # Баг-репорт: собираем поля по шагам
            if kind == "bug":
                if step == 1:
                    data["data"]["description"] = incoming_text
                    data["step"] = 2
                    send_message(user_id, "2. Где находится баг?", keyboard=make_cancel_keyboard())
                elif step == 2:
                    data["data"]["location"] = incoming_text
                    data["step"] = 3
                    send_message(user_id, "3. Что вы хотите сделать с этим багом?", keyboard=make_cancel_keyboard())
                elif step == 3:
                    data["data"]["desired"] = incoming_text
                    data["step"] = 4
                    send_message(
                        user_id,
                        "4. Ссылка/скриншот/пост ВК (обязательно) или напиши 'пропустить':",
                        keyboard=make_cancel_keyboard(),
                    )
                elif step == 4:
                    if not incoming_text.strip() or incoming_text.lower() in ["пропустить", "skip", "-", "нет"]:
                        data["data"]["proof"] = ""
                    else:
                        data["data"]["proof"] = incoming_text

                    owner_id = resolve_user_id(BUG_OWNER)
                    if owner_id is None:
                        print(f"Ошибка: не удалось получить numeric user_id для владельца бага (BUG_OWNER={BUG_OWNER})")
                        send_message(user_id, "Не удалось отправить баг-репорт — проверь настройки BUG_OWNER.")
                    else:
                        app = _create_application(user_id, "bug", data["data"], owner_id)
                        _send_app_to_owner(app)
                        send_message(user_id, "Баг-репорт отправлен ✅", keyboard=make_main_keyboard())

                    del user_data[user_id]
                return

            # Предложение по улучшению: собираем поля по шагам
            if kind == "improvement":
                if step == 1:
                    data["data"]["what"] = incoming_text
                    data["step"] = 2
                    send_message(user_id, "2. Как думаете, зачем это нужно?", keyboard=make_cancel_keyboard())
                elif step == 2:
                    data["data"]["why"] = incoming_text
                    data["step"] = 3
                    send_message(user_id, "3. Краткая информация о предложении:", keyboard=make_cancel_keyboard())
                elif step == 3:
                    data["data"]["details"] = incoming_text
                    owner_id = resolve_user_id(BUG_OWNER)
                    if owner_id is None:
                        print(f"Ошибка: не удалось получить numeric user_id для владельца предложений (BUG_OWNER={BUG_OWNER})")
                        send_message(user_id, "Не удалось отправить предложение — проверь настройки BUG_OWNER.")
                    else:
                        app = _create_application(user_id, "improvement", data["data"], owner_id)
                        _send_app_to_owner(app)
                        send_message(
                            user_id,
                            "Предложение отправлено ✅\nЕсли его одобрят, ты получишь 50к донат рублей!",
                            keyboard=make_main_keyboard(),
                        )

                    del user_data[user_id]
                return

        # --- Ответ владельца ---
        if user_id in applications_by_owner:
            # Принимаем +<id> / -<id> или кнопки вида '✅ Одобрить #<id>'
            action, app_id = _parse_owner_response(text)
            if action and not app_id:
                # Если указано только + или -, и у владельца одна активная заявка
                owner_apps = [
                    a
                    for a in applications_by_owner.get(user_id, [])
                    if applications.get(a, {}).get("status") == "pending"
                ]
                if len(owner_apps) == 1:
                    app_id = owner_apps[0]

            app = None
            if app_id and app_id in applications:
                candidate = applications[app_id]
                if candidate.get("owner_id") == user_id:
                    app = candidate

            if app is not None and action in ["+", "-"]:
                status = "approved" if action == "+" else "rejected"
                app["status"] = status
                applicant_id = app.get("user_id")
                if status == "approved":
                    send_message(applicant_id, "Заявка одобрена ✅")
                    send_message(user_id, "Вы одобрили заявку ✅")
                else:
                    send_message(applicant_id, "Заявка отклонена ❌")
                    send_message(user_id, "Вы отклонили заявку ❌")
            else:
                send_message(user_id, "Не удалось найти заявку с таким ID или она уже обработана.")
            return

    except Exception as e:
        print(f"[ERROR] process_event error: {e}")
        traceback.print_exc()
        # Не ломаем цикл - просто игнорируем проблемное событие
        return


def run_bot():
    print("Бот запущен...")
    while True:
        try:
            for event in longpoll.listen():
                process_event(event)
        except Exception as e:
            print(f"Ошибка в longpoll: {e}. Переподключаемся через 5 сек...")
            time.sleep(5)


if __name__ == "__main__":
    # Дополнительный уровень защиты: если что-то упадет в run_bot(), перезапустимся.
    # Используем BaseException, чтобы не завершаться при KeyboardInterrupt/SystemExit.
    while True:
        try:
            run_bot()
        except BaseException as e:
            # Не даём боту выключаться ни при ошибке, ни при Ctrl+C
            print(f"Критическая ошибка, перезапускаю бота через 5 сек: {e}")
            traceback.print_exc()
            time.sleep(5)

