import warnings
warnings.filterwarnings('ignore')

import logging
import sqlite3
import json
import time
import random
from datetime import datetime, timedelta
import threading
import re
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

def log_action(action):
    logging.info(action)

# Настройки
TOKEN = 'vk1.a.juJVK1BLRRDdBMVFwfT1xUdhSLZbJE67ze7-0LfEqvwbr4vz7GUSMP4EHGax3fFJA9sqQI3KvSt4L1tJ_OEDeedkoQTgfOqT8TfaxNYOHle1qC3KbANHuhah7sQqGUfHyRHsDoKPZjmxSirE-wLqPpUI4DpRNfBVgqaR4BWCwe8qwJNvyEHeOmoWpkzyut1ZLoE62ezUOAAiiQTTmMBTpA'
OWNER_USERNAMES = ['werentersp7607', 'sanzhardell']

# Инициализация VK API
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
try:
    group_id = vk.groups.getById()[0]['id']
    print(f"Group ID: {group_id}")
except Exception as e:
    print(f"Ошибка получения group_id: {e}")
    exit(1)
longpoll = VkBotLongPoll(vk_session, group_id)
print("Longpoll initialized")

# База данных
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    role INTEGER DEFAULT 0,
    nick TEXT,
    sparks INTEGER DEFAULT 100,
    warns INTEGER DEFAULT 0,
    mutes TEXT,
    bans TEXT,
    marriage INTEGER,
    exes TEXT DEFAULT '[]',
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_message INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    game TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    rules TEXT DEFAULT 'Правила не установлены',
    welcome TEXT DEFAULT 'Добро пожаловать!',
    filter_words TEXT DEFAULT '[]',
    antiflood INTEGER DEFAULT 5,
    slowmode INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS roles (
    priority INTEGER PRIMARY KEY,
    name TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    time INTEGER,
    message TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    question TEXT,
    options TEXT,
    votes TEXT DEFAULT '{}'
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS afk (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    time INTEGER
)''')

conn.commit()

# Добавить недостающие столбцы в chats, если их нет
try:
    cursor.execute('ALTER TABLE chats ADD COLUMN antiflood INTEGER DEFAULT 5')
except:
    pass
try:
    cursor.execute('ALTER TABLE chats ADD COLUMN slowmode INTEGER DEFAULT 0')
except:
    pass

conn.commit()

# Инициализация ролей
def init_roles():
    default_roles = {
        0: 'Участник',
        20: 'Помощник',
        40: 'Модератор',
        60: 'Администратор',
        80: 'Главный администратор',
        100: 'Владелец'
    }
    for priority, name in default_roles.items():
        cursor.execute('INSERT OR IGNORE INTO roles (priority, name) VALUES (?, ?)', (priority, name))
    conn.commit()

init_roles()

# Получение ID владельцев
def get_user_id(username):
    try:
        user = vk.utils.resolveScreenName(screen_name=username)
        return user['object_id'] if user['type'] == 'user' else None
    except:
        return None

OWNER_IDS = [get_user_id(u) for u in OWNER_USERNAMES if get_user_id(u)]

# Функции для работы с БД
def get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone()

def update_user(user_id, **kwargs):
    user = get_user(user_id)
    if not user:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
    for key, value in kwargs.items():
        cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()

def get_role(user_id):
    user = get_user(user_id)
    return user[1] if user else 0

def check_permission(user_id, required):
    return get_role(user_id) >= required or user_id in OWNER_IDS

def parse_user(arg):
    # Парсинг пользователя из упоминания или ID
    if arg.startswith('[id'):
        return int(arg.split('|')[0][4:])
    elif arg.isdigit():
        return int(arg)
    else:
        return None

# Функции для чат-менеджера
def check_filter(message, chat_id):
    cursor.execute('SELECT filter_words FROM chats WHERE chat_id = ?', (chat_id,))
    words = cursor.fetchone()
    if words:
        bad_words = json.loads(words[0])
        for word in bad_words:
            if word.lower() in message.lower():
                return True
    return False

def check_flood(user_id, chat_id):
    user = get_user(user_id)
    if user:
        now = int(time.time())
        last = user[11] if len(user) > 11 else 0
        cursor.execute('SELECT antiflood FROM chats WHERE chat_id = ?', (chat_id,))
        limit_row = cursor.fetchone()
        limit = limit_row[0] if limit_row else 5
        if now - last < 60:
            # Увеличиваем счетчик (добавим поле message_count в users)
            count = user[12] if len(user) > 12 else 0
            count += 1
            update_user(user_id, message_count=count)
            if count > limit:
                return True
        else:
            update_user(user_id, message_count=1, last_message=now)
    return False

def add_exp(user_id, peer_id):
    user = get_user(user_id)
    if user:
        exp = user[9] + random.randint(1, 5)
        level = user[10]
        if exp >= level * 100:
            level += 1
            exp = 0
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] Повысил уровень до {level}!', random_id=random.randint(1, 1000))
        update_user(user_id, exp=exp, level=level)

def check_punishments():
    while True:
        now = datetime.now().timestamp()
        cursor.execute('SELECT user_id, mutes FROM users WHERE mutes IS NOT NULL')
        for row in cursor.fetchall():
            mutes = json.loads(row[1])
            if mutes['until'] < now:
                update_user(row[0], mutes=None)
        cursor.execute('SELECT user_id, bans FROM users WHERE bans IS NOT NULL')
        for row in cursor.fetchall():
            bans = json.loads(row[1])
            if bans['until'] < now:
                update_user(row[0], bans=None)
        time.sleep(60)

# Запуск потока для снятия наказаний
threading.Thread(target=check_punishments, daemon=True).start()

# Обработчики команд
def handle_command(event, command, args, peer_id):
    # Безопасно извлекаем user_id/message_id из события, если они есть
    message_id = None
    user_id = None
    if hasattr(event, 'object') and isinstance(event.object, dict):
        message = event.object.get('message', {})
        if isinstance(message, dict):
            user_id = message.get('from_id')
            message_id = message.get('id')

    chat_id = peer_id - 2000000000 if peer_id > 2000000000 else None

    print(f"Handling command: {command} by {user_id}")  # Отладка

    # Участник (0)
    if command == '/start':
        vk.messages.send(peer_id=peer_id, message='Бот Limit активирован в беседе!', random_id=random.randint(1, 1000))

    elif command == '/help':
        help_text = '''
🤖 Бот Limit - Команды:

👤 Команды Участника (0): /start /help /ping /stats /mybans /staff /quit /roles /rules /id /online /apply /ai /anon /getnick /nick /nicklist /nonicks /promo /remind /report

🛠 Помощник (20): /baninfo /getwarn /mutelist /warnlist /muteinfo /fornick /banlist

⚖ Модератор (40): /mute /unmute /warn /unwarn /kick /del /pin /unpin /zov /prewarn /preunwarn /removenick /setnick

🏛 Админ (60): /ban /unban /setrole /removerole /gmute /gunmute /gremovenick /gsetnick

👑 Гл. Админ (80): /createrole /deleterole /access /gm /sync /filter /chatdata /config /gban /gkick /grole /gunban /gwarn /gunwarn /kickdog

🏰 Владелец (100): /deactivate

🎭 RP: /breast /hug /iznas /kiss /mitet /spank

🎮 Игры: /profile /top /pay /marriage /marriages /divorce /mymarriage /exes

🎲 Новые команды: /clear /slowmode /rps /guess /quote /fact /poll /vote /afk /userinfo /toplevel
        '''
        vk.messages.send(peer_id=peer_id, message=help_text, random_id=random.randint(1, 1000))

    elif command == '/ping':
        vk.messages.send(peer_id=peer_id, message='Pong!', random_id=random.randint(1, 1000))

    elif command == '/stats':
        user = get_user(user_id)
        if user:
            msg = f'Роль: {user[1]}\nНик: {user[2] or "Нет"}\nИскры: {user[3]}\nПредупреждения: {user[4]}'
        else:
            msg = 'Статистика не найдена'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/mybans':
        user = get_user(user_id)
        bans = json.loads(user[6]) if user and user[6] else None
        if bans:
            msg = f'Бан до: {datetime.fromtimestamp(bans["until"]).strftime("%Y-%m-%d %H:%M")}\nПричина: {bans["reason"]}'
        else:
            msg = 'У вас нет банов'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/staff':
        cursor.execute('SELECT user_id, role FROM users WHERE role >= 20')
        staff = cursor.fetchall()
        msg = 'Администрация:\n' + '\n'.join([f'[id{u[0]}|ID {u[0]}] - Роль {u[1]}' for u in staff])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/quit':
        vk.messages.removeChatUser(chat_id=chat_id, user_id=user_id)
        vk.messages.send(peer_id=peer_id, message='Вы покинули беседу', random_id=random.randint(1, 1000))

    elif command == '/roles':
        print("Executing /roles")
        cursor.execute('SELECT priority, name FROM roles')
        roles = cursor.fetchall()
        msg = 'Роли:\n' + '\n'.join([f'{r[0]} - {r[1]}' for r in roles])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/rules':
        cursor.execute('SELECT rules FROM chats WHERE chat_id = ?', (chat_id,))
        rules = cursor.fetchone()
        msg = rules[0] if rules else 'Правила не установлены'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/id':
        vk.messages.send(peer_id=peer_id, message=f'Ваш ID: {user_id}', random_id=random.randint(1, 1000))

    elif command == '/online':
        # Получить онлайн участников (упрощенно)
        members = vk.messages.getConversationMembers(peer_id=peer_id)
        online = [m['member_id'] for m in members['items'] if m.get('online')]
        msg = f'Онлайн: {len(online)} участников'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/apply':
        vk.messages.send(peer_id=peer_id, message='Заявка отправлена администрации', random_id=random.randint(1, 1000))

    elif command == '/ai':
        vk.messages.send(peer_id=peer_id, message='ИИ временно не работает', random_id=random.randint(1, 1000))

    elif command == '/anon':
        if args:
            msg = ' '.join(args)
            vk.messages.send(peer_id=peer_id, message=f'Аноним: {msg}', random_id=random.randint(1, 1000))

    elif command == '/getnick':
        if args:
            target_id = parse_user(args[0])
            user = get_user(target_id)
            nick = user[2] if user else 'Нет'
            vk.messages.send(peer_id=peer_id, message=f'Ник: {nick}', random_id=random.randint(1, 1000))

    elif command == '/nicklist':
        cursor.execute('SELECT user_id, nick FROM users WHERE nick IS NOT NULL')
        nicks = cursor.fetchall()
        msg = 'Ники:\n' + '\n'.join([f'[id{u[0]}| ] - {u[1]}' for u in nicks])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/nonicks':
        cursor.execute('SELECT user_id FROM users WHERE nick IS NULL')
        nonicks = cursor.fetchall()
        msg = 'Без ников:\n' + '\n'.join([f'[id{u[0]}| ]' for u in nonicks])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/promo':
        vk.messages.send(peer_id=peer_id, message='Промокод активирован', random_id=random.randint(1, 1000))

    elif command == '/remind':
        if len(args) >= 2:
            time_str = args[0]
            message = ' '.join(args[1:])
            # Упрощенно, добавить в reminders
            cursor.execute('INSERT INTO reminders (user_id, time, message) VALUES (?, ?, ?)', (user_id, int(time.time()) + 60, message))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message='Напоминание установлено', random_id=random.randint(1, 1000))

    elif command == '/report':
        if args:
            report = ' '.join(args)
            vk.messages.send(peer_id=peer_id, message='Обращение отправлено администрации', random_id=random.randint(1, 1000))

    # Помощник (20)
    elif command == '/baninfo' and check_permission(user_id, 20):
        if args:
            target_id = parse_user(args[0])
            user = get_user(target_id)
            bans = json.loads(user[6]) if user and user[6] else None
            msg = f'Бан: {bans}' if bans else 'Нет бана'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/getwarn' and check_permission(user_id, 20):
        if args:
            target_id = parse_user(args[0])
            user = get_user(target_id)
            warns = user[4] if user else 0
            vk.messages.send(peer_id=peer_id, message=f'Предупреждения: {warns}', random_id=random.randint(1, 1000))

    elif command == '/mutelist' and check_permission(user_id, 20):
        cursor.execute('SELECT user_id, mutes FROM users WHERE mutes IS NOT NULL')
        mutes = cursor.fetchall()
        msg = 'Замьюченные:\n' + '\n'.join([f'[id{u[0]}| ] - {u[1]}' for u in mutes])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/warnlist' and check_permission(user_id, 20):
        cursor.execute('SELECT user_id, warns FROM users WHERE warns > 0')
        warns = cursor.fetchall()
        msg = 'Предупреждения:\n' + '\n'.join([f'[id{u[0]}| ] - {u[1]}' for u in warns])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/muteinfo' and check_permission(user_id, 20):
        if args:
            target_id = parse_user(args[0])
            user = get_user(target_id)
            mutes = json.loads(user[5]) if user and user[5] else None
            msg = f'Мут: {mutes}' if mutes else 'Нет мута'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/fornick' and check_permission(user_id, 20):
        if args:
            nick = ' '.join(args)
            cursor.execute('SELECT user_id FROM users WHERE nick = ?', (nick,))
            user = cursor.fetchone()
            msg = f'Пользователь: [id{user[0]}| ]' if user else 'Не найден'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/banlist' and check_permission(user_id, 20):
        cursor.execute('SELECT user_id, bans FROM users WHERE bans IS NOT NULL')
        bans = cursor.fetchall()
        msg = 'Забаненные:\n' + '\n'.join([f'[id{u[0]}| ] - {u[1]}' for u in bans])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    # Модератор (40)
    elif command == '/mute' and check_permission(user_id, 40):
        if len(args) >= 2:
            target_id = parse_user(args[0])
            minutes = int(args[1])
            reason = ' '.join(args[2:]) if len(args) > 2 else 'Не указана'
            if target_id:
                mute_until = (datetime.now() + timedelta(minutes=minutes)).timestamp()
                update_user(target_id, mutes=json.dumps({'until': mute_until, 'reason': reason}))
                vk.messages.send(peer_id=peer_id, message=f'Замьючен на {minutes} мин. Причина: {reason}', random_id=random.randint(1, 1000))

    elif command == '/unmute' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(target_id, mutes=None)
                vk.messages.send(peer_id=peer_id, message='Размьючен', random_id=random.randint(1, 1000))

    elif command == '/warn' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            reason = ' '.join(args[1:]) if len(args) > 1 else 'Не указана'
            if target_id:
                user = get_user(target_id)
                warns = user[4] + 1 if user else 1
                update_user(target_id, warns=warns)
                vk.messages.send(peer_id=peer_id, message=f'Предупреждение. Всего: {warns}. Причина: {reason}', random_id=random.randint(1, 1000))

    elif command == '/unwarn' and check_permission(user_id, 40):
        if len(args) >= 2:
            target_id = parse_user(args[0])
            num = int(args[1])
            if target_id:
                user = get_user(target_id)
                warns = max(0, user[4] - num) if user else 0
                update_user(target_id, warns=warns)
                vk.messages.send(peer_id=peer_id, message=f'Снято {num} предупреждений', random_id=random.randint(1, 1000))

    elif command == '/kick' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            reason = ' '.join(args[1:]) if len(args) > 1 else 'Не указана'
            if target_id:
                vk.messages.removeChatUser(chat_id=chat_id, user_id=target_id)
                vk.messages.send(peer_id=peer_id, message=f'Исключен. Причина: {reason}', random_id=random.randint(1, 1000))

    elif command == '/del' and check_permission(user_id, 40):
        if message_id:
            vk.messages.delete(message_ids=[message_id])
            vk.messages.send(peer_id=peer_id, message='Сообщение удалено', random_id=random.randint(1, 1000))

    elif command == '/pin' and check_permission(user_id, 40):
        if message_id:
            vk.messages.pin(peer_id=peer_id, message_id=message_id)
            vk.messages.send(peer_id=peer_id, message='Закреплено', random_id=random.randint(1, 1000))

    elif command == '/unpin' and check_permission(user_id, 40):
        vk.messages.unpin(peer_id=peer_id)
        vk.messages.send(peer_id=peer_id, message='Откреплено', random_id=random.randint(1, 1000))

    elif command == '/zov' and check_permission(user_id, 40):
        vk.messages.send(peer_id=peer_id, message='@all Участники, внимание!', random_id=random.randint(1, 1000))

    elif command == '/prewarn' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            reason = ' '.join(args[1:]) if len(args) > 1 else 'Не указана'
            vk.messages.send(peer_id=peer_id, message=f'[id{target_id}| ] Устное предупреждение. Причина: {reason}', random_id=random.randint(1, 1000))

    elif command == '/preunwarn' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{target_id}| ] Устное предупреждение снято', random_id=random.randint(1, 1000))

    elif command == '/removenick' and check_permission(user_id, 40):
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(target_id, nick=None)
                vk.messages.send(peer_id=peer_id, message='Ник удален', random_id=random.randint(1, 1000))

    elif command == '/nick':
        nick = ' '.join(args)
        if nick:
            update_user(user_id, nick=nick)
            vk.messages.send(peer_id=peer_id, message=f'Ваш ник установлен: {nick}', random_id=random.randint(1, 1000))
        else:
            vk.messages.send(peer_id=peer_id, message='Укажите ник', random_id=random.randint(1, 1000))

    elif command == '/setnick' and check_permission(user_id, 40):
        if len(args) >= 2:
            target_id = parse_user(args[0])
            nick = ' '.join(args[1:])
            if target_id:
                update_user(target_id, nick=nick)
                vk.messages.send(peer_id=peer_id, message=f'Ник установлен: {nick}', random_id=random.randint(1, 1000))

    # Админ (60)
    elif command == '/ban' and check_permission(user_id, 60):
        if len(args) >= 2:
            target_id = parse_user(args[0])
            days = int(args[1])
            reason = ' '.join(args[2:]) if len(args) > 2 else 'Не указана'
            if target_id:
                ban_until = (datetime.now() + timedelta(days=days)).timestamp()
                update_user(target_id, bans=json.dumps({'until': ban_until, 'reason': reason}))
                vk.messages.removeChatUser(chat_id=chat_id, user_id=target_id)
                vk.messages.send(peer_id=peer_id, message=f'Забанен на {days} дней. Причина: {reason}', random_id=random.randint(1, 1000))
                log_action(f'Ban: {target_id} by {user_id} for {days} days, reason: {reason}')

    elif command == '/unban' and check_permission(user_id, 60):
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(target_id, bans=None)
                vk.messages.send(peer_id=peer_id, message='Разбанен', random_id=random.randint(1, 1000))

    elif command == '/setrole' and check_permission(user_id, 60):
        if len(args) >= 2:
            target_id = parse_user(args[0])
            role = int(args[1])
            if target_id:
                update_user(target_id, role=role)
                vk.messages.send(peer_id=peer_id, message=f'Роль установлена: {role}', random_id=random.randint(1, 1000))

    elif command == '/removerole' and check_permission(user_id, 60):
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(target_id, role=0)
                vk.messages.send(peer_id=peer_id, message='Роль снята', random_id=random.randint(1, 1000))

    # Гл. Админ (80)
    elif command == '/createrole' and check_permission(user_id, 80):
        if len(args) >= 2:
            priority = int(args[0])
            name = ' '.join(args[1:])
            cursor.execute('INSERT INTO roles (priority, name) VALUES (?, ?)', (priority, name))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message=f'Роль создана: {name} ({priority})', random_id=random.randint(1, 1000))

    elif command == '/deleterole' and check_permission(user_id, 80):
        if args:
            priority = int(args[0])
            cursor.execute('DELETE FROM roles WHERE priority = ?', (priority,))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message='Роль удалена', random_id=random.randint(1, 1000))

    elif command == '/access' and check_permission(user_id, 80):
        vk.messages.send(peer_id=peer_id, message='Настройка доступа (заглушка)', random_id=random.randint(1, 1000))

    elif command == '/gm' and check_permission(user_id, 80):
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(target_id, role=100)  # Иммунитет
                vk.messages.send(peer_id=peer_id, message='Иммунитет установлен', random_id=random.randint(1, 1000))

    elif command == '/sync' and check_permission(user_id, 80):
        vk.messages.send(peer_id=peer_id, message='Синхронизировано', random_id=random.randint(1, 1000))

    elif command == '/filter' and check_permission(user_id, 80):
        vk.messages.send(peer_id=peer_id, message='Фильтр настроен', random_id=random.randint(1, 1000))

    elif command == '/chatdata' and check_permission(user_id, 80):
        vk.messages.send(peer_id=peer_id, message=f'Информация о чате: ID {chat_id}', random_id=random.randint(1, 1000))

    elif command == '/config' and check_permission(user_id, 80):
        vk.messages.send(peer_id=peer_id, message='Конфигурация изменена', random_id=random.randint(1, 1000))

    # Владелец (100)
    elif command == '/deactivate' and check_permission(user_id, 100):
        # Деактивация
        vk.messages.send(peer_id=peer_id, message='Беседа деактивирована', random_id=random.randint(1, 1000))

    # RP
    elif command == '/breast':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] прикоснулся к груди [id{target_id}| ] 💋', random_id=random.randint(1, 1000))

    elif command == '/hug':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] обнял [id{target_id}| ] 🤗', random_id=random.randint(1, 1000))

    elif command == '/iznas':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] надругался над [id{target_id}| ] 😈', random_id=random.randint(1, 1000))

    elif command == '/kiss':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] поцеловал [id{target_id}| ] 😘', random_id=random.randint(1, 1000))

    elif command == '/mitet':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] сделал приятно [id{target_id}| ] 😏', random_id=random.randint(1, 1000))

    elif command == '/spank':
        if args:
            target_id = parse_user(args[0])
            vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] шлёпнул по попе [id{target_id}| ] 🍑', random_id=random.randint(1, 1000))

    # Игры
    elif command == '/profile':
        user = get_user(user_id)
        msg = f'Профиль: Искры {user[3] if user else 0}'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/top':
        cursor.execute('SELECT user_id, sparks FROM users ORDER BY sparks DESC LIMIT 10')
        top = cursor.fetchall()
        msg = 'Топ по искрам:\n' + '\n'.join([f'{i+1}. [id{u[0]}| ] - {u[1]}' for i, u in enumerate(top)])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/pay':
        if len(args) >= 2:
            target_id = parse_user(args[0])
            amount = int(args[1])
            user = get_user(user_id)
            if user and user[3] >= amount:
                update_user(user_id, sparks=user[3] - amount)
                target = get_user(target_id)
                update_user(target_id, sparks=(target[3] if target else 0) + amount)
                vk.messages.send(peer_id=peer_id, message=f'Передано {amount} искр', random_id=random.randint(1, 1000))
            else:
                vk.messages.send(peer_id=peer_id, message='Недостаточно искр', random_id=random.randint(1, 1000))

    elif command == '/marriage':
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(user_id, marriage=target_id)
                update_user(target_id, marriage=user_id)
                vk.messages.send(peer_id=peer_id, message='Предложение брака отправлено!', random_id=random.randint(1, 1000))

    elif command == '/marriages':
        cursor.execute('SELECT user_id, marriage FROM users WHERE marriage IS NOT NULL')
        marriages = cursor.fetchall()
        msg = 'Браки:\n' + '\n'.join([f'[id{u[0]}| ] + [id{u[1]}| ]' for u in marriages])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/divorce':
        if args:
            target_id = parse_user(args[0])
            if target_id:
                update_user(user_id, marriage=None)
                update_user(target_id, marriage=None)
                vk.messages.send(peer_id=peer_id, message='Развод оформлен', random_id=random.randint(1, 1000))

    elif command == '/mymarriage':
        user = get_user(user_id)
        partner = user[7] if user else None
        msg = f'Ваш партнер: [id{partner}| ]' if partner else 'Не женаты'
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/exes':
        if args:
            target_id = parse_user(args[0])
            user = get_user(target_id)
            exes = json.loads(user[8]) if user and user[8] else []
            msg = f'Бывшие: {", ".join([str(e) for e in exes])}'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    # Новые улучшенные команды
    elif command == '/clear' and check_permission(user_id, 40):
        count = int(args[0]) if args and args[0].isdigit() else 10
        # Удалить последние сообщения (упрощенно, VK не позволяет массово удалять)
        vk.messages.send(peer_id=peer_id, message=f'Удалено {count} сообщений (симуляция)', random_id=random.randint(1, 1000))

    elif command == '/slowmode' and check_permission(user_id, 60):
        seconds = int(args[0]) if args and args[0].isdigit() else 0
        cursor.execute('UPDATE chats SET slowmode = ? WHERE chat_id = ?', (seconds, chat_id))
        conn.commit()
        vk.messages.send(peer_id=peer_id, message=f'Slowmode установлен: {seconds} сек', random_id=random.randint(1, 1000))

    elif command == '/rps':
        choices = ['камень', 'ножницы', 'бумага']
        user_choice = args[0].lower() if args else None
        if user_choice in choices:
            bot_choice = random.choice(choices)
            if user_choice == bot_choice:
                result = 'Ничья!'
            elif (user_choice == 'камень' and bot_choice == 'ножницы') or (user_choice == 'ножницы' and bot_choice == 'бумага') or (user_choice == 'бумага' and bot_choice == 'камень'):
                result = 'Ты выиграл!'
            else:
                result = 'Ты проиграл!'
            vk.messages.send(peer_id=peer_id, message=f'Твой выбор: {user_choice}\nМой: {bot_choice}\n{result}', random_id=random.randint(1, 1000))
        else:
            vk.messages.send(peer_id=peer_id, message='Выбери: камень, ножницы, бумага', random_id=random.randint(1, 1000))

    elif command == '/guess':
        if not args:
            number = random.randint(1, 100)
            # Сохранить в сессии (упрощенно, в БД)
            update_user(user_id, game=json.dumps({'type': 'guess', 'number': number}))
            vk.messages.send(peer_id=peer_id, message='Угадай число от 1 до 100!', random_id=random.randint(1, 1000))
        else:
            guess = int(args[0])
            user = get_user(user_id)
            game = json.loads(user[9]) if user and user[9] else None  # Предположим поле game
            if game and game['type'] == 'guess':
                if guess == game['number']:
                    vk.messages.send(peer_id=peer_id, message='Угадал! 🎉', random_id=random.randint(1, 1000))
                    update_user(user_id, game=None)
                elif guess < game['number']:
                    vk.messages.send(peer_id=peer_id, message='Больше!', random_id=random.randint(1, 1000))
                else:
                    vk.messages.send(peer_id=peer_id, message='Меньше!', random_id=random.randint(1, 1000))
            else:
                vk.messages.send(peer_id=peer_id, message='Начни игру /guess', random_id=random.randint(1, 1000))

    elif command == '/quote':
        quotes = [
            "Жизнь - это то, что с тобой происходит, пока ты строишь другие планы. - Джон Леннон",
            "Будь собой; все остальные роли уже заняты. - Оскар Уайлд",
            "Секрет успеха - постоянство цели. - Бенджамин Дизраэли"
        ]
        quote = random.choice(quotes)
        vk.messages.send(peer_id=peer_id, message=f'Цитата: {quote}', random_id=random.randint(1, 1000))

    elif command == '/fact':
        facts = [
            "Дельфины спят с одним открытым глазом.",
            "Медузы состоят на 95% из воды.",
            "Слон - единственное животное, которое не может прыгать."
        ]
        fact = random.choice(facts)
        vk.messages.send(peer_id=peer_id, message=f'Факт: {fact}', random_id=random.randint(1, 1000))

    elif command == '/poll' and check_permission(user_id, 40):
        if len(args) >= 3:
            question = args[0]
            options = args[1:]
            cursor.execute('INSERT INTO polls (chat_id, question, options) VALUES (?, ?, ?)', (chat_id, question, json.dumps(options)))
            conn.commit()
            poll_id = cursor.lastrowid
            msg = f'Опрос: {question}\n' + '\n'.join([f'{i+1}. {opt}' for i, opt in enumerate(options)]) + f'\nГолосуй: /vote {poll_id} [номер]'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/vote':
        if len(args) >= 2:
            poll_id = int(args[0])
            option = int(args[1]) - 1
            cursor.execute('SELECT * FROM polls WHERE id = ? AND chat_id = ?', (poll_id, chat_id))
            poll = cursor.fetchone()
            if poll:
                votes = json.loads(poll[4])
                votes[str(user_id)] = option
                cursor.execute('UPDATE polls SET votes = ? WHERE id = ?', (json.dumps(votes), poll_id))
                conn.commit()
                vk.messages.send(peer_id=peer_id, message='Голос учтен!', random_id=random.randint(1, 1000))

    elif command == '/afk':
        reason = ' '.join(args) if args else 'AFK'
        cursor.execute('INSERT OR REPLACE INTO afk (user_id, reason, time) VALUES (?, ?, ?)', (user_id, reason, int(time.time())))
        conn.commit()
        vk.messages.send(peer_id=peer_id, message=f'AFK: {reason}', random_id=random.randint(1, 1000))

    elif command == '/userinfo':
        target_id = parse_user(args[0]) if args else user_id
        user = get_user(target_id)
        if user:
            msg = f'ID: {user[0]}\nРоль: {user[1]}\nНик: {user[2] or "Нет"}\nИскры: {user[3]}\nУровень: {user[10] if len(user) > 10 else 1}'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    # Новые стандартные команды
    elif command == '/setwelcome' and check_permission(user_id, 80):
        if args:
            welcome = ' '.join(args)
            cursor.execute('UPDATE chats SET welcome = ? WHERE chat_id = ?', (welcome, chat_id))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message='Приветствие установлено', random_id=random.randint(1, 1000))

    elif command == '/setrules' and check_permission(user_id, 80):
        if args:
            rules = ' '.join(args)
            cursor.execute('UPDATE chats SET rules = ? WHERE chat_id = ?', (rules, chat_id))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message='Правила установлены', random_id=random.randint(1, 1000))

    elif command == '/addfilter' and check_permission(user_id, 80):
        if args:
            word = args[0]
            cursor.execute('SELECT filter_words FROM chats WHERE chat_id = ?', (chat_id,))
            words = json.loads(cursor.fetchone()[0])
            words.append(word)
            cursor.execute('UPDATE chats SET filter_words = ? WHERE chat_id = ?', (json.dumps(words), chat_id))
            conn.commit()
            vk.messages.send(peer_id=peer_id, message=f'Слово "{word}" добавлено в фильтр', random_id=random.randint(1, 1000))

    elif command == '/removefilter' and check_permission(user_id, 80):
        if args:
            word = args[0]
            cursor.execute('SELECT filter_words FROM chats WHERE chat_id = ?', (chat_id,))
            words = json.loads(cursor.fetchone()[0])
            if word in words:
                words.remove(word)
                cursor.execute('UPDATE chats SET filter_words = ? WHERE chat_id = ?', (json.dumps(words), chat_id))
                conn.commit()
                vk.messages.send(peer_id=peer_id, message=f'Слово "{word}" удалено из фильтра', random_id=random.randint(1, 1000))

    elif command == '/dice':
        result = random.randint(1, 6)
        vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] бросил кубик: {result}', random_id=random.randint(1, 1000))

    elif command == '/coin':
        result = 'Орёл' if random.choice([True, False]) else 'Решка'
        vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] подбросил монету: {result}', random_id=random.randint(1, 1000))

    elif command == '/level':
        user = get_user(user_id)
        if user:
            msg = f'Уровень: {user[10]}, Опыт: {user[9]}/{user[10]*100}'
            vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

    elif command == '/toplevel':
        cursor.execute('SELECT user_id, level, exp FROM users ORDER BY level DESC, exp DESC LIMIT 10')
        top = cursor.fetchall()
        msg = 'Топ по уровню:\n' + '\n'.join([f'{i+1}. [id{u[0]}| ] - Ур. {u[1]}, Опыт {u[2]}' for i, u in enumerate(top)])
        vk.messages.send(peer_id=peer_id, message=msg, random_id=random.randint(1, 1000))

# Основной цикл
try:
    print("Starting longpoll listen...")
    for event in longpoll.listen():
        print(f"Event received: {event.type}")
        if event.type == VkBotEventType.MESSAGE_NEW:
            text = event.object['message']['text']
            peer_id = event.object['message']['peer_id']
            user_id = event.object['message']['from_id']
            chat_id = peer_id - 2000000000 if peer_id > 2000000000 else None
            print(f"Новое сообщение: {text} от {user_id} в {peer_id}")  # Отладка

            # Проверка на мут
            user = get_user(user_id)
            if user and user[5]:  # mutes
                mutes = json.loads(user[5])
                if mutes['until'] > time.time():
                    continue  # Игнорировать сообщение

            # Проверка AFK
            cursor.execute('SELECT reason FROM afk WHERE user_id = ?', (user_id,))
            afk = cursor.fetchone()
            if afk:
                cursor.execute('DELETE FROM afk WHERE user_id = ?', (user_id,))
                conn.commit()
                vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] вернулся! Был AFK: {afk[0]}', random_id=random.randint(1, 1000))

            # Проверка упоминаний AFK
            for mention in re.findall(r'\[id(\d+)\|', text):
                mention_id = int(mention)
                cursor.execute('SELECT reason FROM afk WHERE user_id = ?', (mention_id,))
                afk_mention = cursor.fetchone()
                if afk_mention:
                    vk.messages.send(peer_id=peer_id, message=f'[id{mention_id}| ] AFK: {afk_mention[0]}', random_id=random.randint(1, 1000))

            # Фильтр слов
            if chat_id and check_filter(text, chat_id):
                vk.messages.delete(message_ids=[event.object['message']['id']])
                vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] Сообщение удалено за запрещенные слова', random_id=random.randint(1, 1000))
                continue

            # Антифлуд
            if chat_id and check_flood(user_id, chat_id):
                # Мут за флуд
                mute_until = (datetime.now() + timedelta(minutes=5)).timestamp()
                update_user(user_id, mutes=json.dumps({'until': mute_until, 'reason': 'Флуд'}))
                vk.messages.send(peer_id=peer_id, message=f'[id{user_id}| ] Замьючен за флуд на 5 минут', random_id=random.randint(1, 1000))
                continue

            # Slowmode
            cursor.execute('SELECT slowmode FROM chats WHERE chat_id = ?', (chat_id,))
            slow = cursor.fetchone()
            if slow and slow[0] > 0:
                if user and time.time() - user[11] < slow[0]:
                    continue  # Игнорировать

            # Добавление опыта
            add_exp(user_id, peer_id)

            if text.startswith('/'):
                parts = text.split()
                command = parts[0].lower()
                args = parts[1:]
                try:
                    handle_command(event, command, args, peer_id)
                except Exception as e:
                    print(f"Ошибка в handle_command: {e}")
                    log_action(f"Ошибка в handle_command: {e}")

        elif event.type == VkBotEventType.CHAT_UPDATE:
            # Приветствие при вступлении
            if 'action' in event.object and event.object['action']['type'] == 'chat_invite_user':
                new_user_id = event.object['action']['member_id']
                chat_id = event.object['chat_id']
                peer_id = 2000000000 + chat_id
                cursor.execute('SELECT welcome FROM chats WHERE chat_id = ?', (chat_id,))
                welcome = cursor.fetchone()
                if welcome:
                    vk.messages.send(peer_id=peer_id, message=welcome[0].replace('{user}', f'[id{new_user_id}| ]'), random_id=random.randint(1, 1000))
except Exception as e:
    print(f"Ошибка в основном цикле: {e}")
    log_action(f"Ошибка в основном цикле: {e}")
