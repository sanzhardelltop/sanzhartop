import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from datetime import datetime, timedelta
import json
import os
import re
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# Администраторы (числовой VK ID)
ADMINS = {
    837981973: 'TVER',   # Основатель TVER
    522894540: 'PERM',   # Основатель PERM
    314950036: 'BUGS'    # Модератор багов
}

TOKEN = 'vk1.a.yJNtmSw2-G_BeHBvomh_VdgYfjJb_844uFDNBrwSVmcCi1fPUtJ3U2XdPjNyC-FWWqko6bvjBldYpC5dJL9WINOPS16-T_7cW2YEWMHoX1hq8R4uulyqYAvNvFvhZ148C4gjmFgjNZvM0RGz1TZwRGw0lET3TC5wO5916DiS77z7q82CIwFbI_MrGk3qnnHpoopp9vdRZXOA0GjsnwnLBg'

vk = vk_api.VkApi(token=TOKEN)
api = vk.get_api()
longpoll = VkLongPoll(vk)

DATA_FILE = 'bot_data.json'
user_states = {}
submissions = {'norms': [], 'bugs': [], 'suggestions': []}
submission_counter = 0
last_submitted_id = {}

# ----------------------
# Работа с данными
# ----------------------
def load_data():
    global submissions, submission_counter
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            submissions = data.get('submissions', {'norms': [], 'bugs': [], 'suggestions': []})
            submission_counter = data.get('counter', 0)
    cleanup_old_submissions()

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({'submissions': submissions, 'counter': submission_counter}, f, ensure_ascii=False)

def cleanup_old_submissions():
    global submissions
    now = datetime.now()
    submissions['norms'] = [n for n in submissions['norms'] if (datetime.fromisoformat(n['timestamp']) + timedelta(days=7)) > now]
    submissions['bugs'] = [b for b in submissions['bugs'] if (datetime.fromisoformat(b['timestamp']) + timedelta(days=7)) > now]
    submissions['suggestions'] = [s for s in submissions['suggestions'] if (datetime.fromisoformat(s['timestamp']) + timedelta(days=7)) > now]
    save_data()

# ----------------------
# Клавиатуры
# ----------------------
def get_main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('📄 Отправить норму', color=VkKeyboardColor.POSITIVE)
    kb.add_button('🐞 Нашел баг', color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button('💡 Предложение', color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button('📋 Мои заявки', color=VkKeyboardColor.PRIMARY)
    kb.add_button('❓ Помощь', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_cancel_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button('❌ Отмена', color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

def get_approval_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button('✅ Одобрить', color=VkKeyboardColor.POSITIVE)
    kb.add_button('❌ Отклонить', color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

# ----------------------
# Утилиты
# ----------------------
def send_message(user_id, message, keyboard=None):
    api.messages.send(user_id=user_id, message=message, keyboard=keyboard, random_id=0)

def validate_vk_link(link):
    pattern = r'(https?://)?(www\.)?vk\.com/\S+|https://vk\.com/wall\d+_\d+'
    return re.match(pattern, link) is not None

def cancel_submission(user_id):
    if user_id in user_states:
        del user_states[user_id]
        send_message(user_id, '❌ Ввод отменен. Вы вернулись в главное меню.', get_main_keyboard())
    else:
        send_message(user_id, 'Вы не начали заполнение формы.', get_main_keyboard())

# =======================
# НОРМЫ
# =======================
def start_norm_submission(user_id):
    user_states[user_id] = {'type': 'norm', 'step': 1, 'data': {}}
    send_message(user_id, '📋 Начнем заполнение анкеты нормы!\n\n1️⃣ Введите ваш никнейм:', get_cancel_keyboard())

def handle_norm_step(user_id, text):
    if text == '❌ Отмена':
        cancel_submission(user_id)
        return
    state = user_states[user_id]
    if state['step'] == 1:
        state['data']['nickname'] = text
        state['step'] = 2
        send_message(user_id, '2️⃣ Введите вашу должность:', get_cancel_keyboard())
    elif state['step'] == 2:
        state['data']['position'] = text
        state['step'] = 3
        send_message(user_id, '3️⃣ Опишите проделанную работу:', get_cancel_keyboard())
    elif state['step'] == 3:
        state['data']['work'] = text
        state['step'] = 4
        send_message(user_id, '4️⃣ Отправьте доказательства (ссылка на пост ВК или фото):', get_cancel_keyboard())
    elif state['step'] == 4:
        if validate_vk_link(text):
            state['data']['proof'] = text
            state['step'] = 5
            send_message(user_id, '5️⃣ Выберите ваш сервер:\n1 - TVER\n2 - PERM\n\nВведите номер (1 или 2):', get_cancel_keyboard())
        else:
            send_message(user_id, '❌ Некорректная ссылка! Отправьте ссылку на пост ВК.', get_cancel_keyboard())
    elif state['step'] == 5:
        if text in ['1', '2']:
            server = 'TVER' if text == '1' else 'PERM'
            state['data']['server'] = server
            global submission_counter
            submission_counter += 1
            submission = {
                'id': submission_counter,
                'user_id': user_id,
                'type': 'norm',
                'status': 'На рассмотрении',
                'timestamp': datetime.now().isoformat(),
                'data': state['data']
            }
            submissions['norms'].append(submission)
            save_data()
            send_message(user_id, f'✅ Заявка №{submission_counter} отправлена на рассмотрение!\n\nСтатус: На рассмотрении', get_main_keyboard())
            # Отправка администратору
            admin_id = 837981973 if server == 'TVER' else 522894540
            admin_msg = f"📬 Новая заявка №{submission_counter} на норму:\n\n👤 Никнейм: {state['data']['nickname']}\n💼 Должность: {state['data']['position']}\n📝 Работа: {state['data']['work']}\n🔗 Доказательства: {state['data']['proof']}\n🗺️ Сервер: {server}"
            send_message(admin_id, admin_msg, get_approval_keyboard())
            last_submitted_id[admin_id] = submission_counter
            del user_states[user_id]
        else:
            send_message(user_id, '❌ Введите 1 или 2!', get_cancel_keyboard())

# =======================
# БАГИ
# =======================
def start_bug_report(user_id):
    user_states[user_id] = {'type': 'bug', 'step': 1, 'data': {}}
    send_message(user_id, '🐛 Начнем заполнение отчета о баге!\n\n1️⃣ Что за баг:', get_cancel_keyboard())

def handle_bug_step(user_id, text):
    if text == '❌ Отмена':
        cancel_submission(user_id)
        return
    state = user_states[user_id]
    if state['step'] == 1:
        state['data']['bug_description'] = text
        state['step'] = 2
        send_message(user_id, '2️⃣ Где находится баг:', get_cancel_keyboard())
    elif state['step'] == 2:
        state['data']['bug_location'] = text
        state['step'] = 3
        send_message(user_id, '3️⃣ Доказательства (ссылка на ВК или фото; чтобы пропустить напишите -):', get_cancel_keyboard())
    elif state['step'] == 3:
        if text == '-':
            state['data']['proof'] = 'Не предоставлены'
        elif validate_vk_link(text):
            state['data']['proof'] = text
        else:
            send_message(user_id, '❌ Некорректная ссылка! Введите ссылку на пост ВК или -', get_cancel_keyboard())
            return
        global submission_counter
        submission_counter += 1
        submission = {
            'id': submission_counter,
            'user_id': user_id,
            'type': 'bug',
            'status': 'На рассмотрении',
            'timestamp': datetime.now().isoformat(),
            'data': state['data']
        }
        submissions['bugs'].append(submission)
        save_data()
        send_message(user_id, f'✅ Баг №{submission_counter} отправлен на рассмотрение!\n\nСтатус: На рассмотрении', get_main_keyboard())
        admin_id = 314950036
        admin_msg = f"🐛 Новый отчет о баге №{submission_counter}:\n\n❓ Баг: {state['data']['bug_description']}\n📍 Место: {state['data']['bug_location']}\n🔗 Доказательства: {state['data']['proof']}"
        send_message(admin_id, admin_msg, get_approval_keyboard())
        last_submitted_id[admin_id] = submission_counter
        del user_states[user_id]

# =======================
# ПРЕДЛОЖЕНИЯ
# =======================
def start_suggestion(user_id):
    user_states[user_id] = {'type': 'suggestion', 'step': 1, 'data': {}}
    send_message(user_id, '💡 Начнем заполнение предложения по обновлению!\n\n1️⃣ Введите ваш никнейм:', get_cancel_keyboard())

def handle_suggestion_step(user_id, text):
    if text == '❌ Отмена':
        cancel_submission(user_id)
        return
    state = user_states[user_id]
    if state['step'] == 1:
        state['data']['nickname'] = text
        state['step'] = 2
        send_message(user_id, '2️⃣ Ваше предложение (краткое описание):', get_cancel_keyboard())
    elif state['step'] == 2:
        state['data']['suggestion'] = text
        state['step'] = 3
        send_message(user_id, '3️⃣ Введите дату и подпись:', get_cancel_keyboard())
    elif state['step'] == 3:
        state['data']['datetime'] = text
        global submission_counter
        submission_counter += 1
        submission = {
            'id': submission_counter,
            'user_id': user_id,
            'type': 'suggestion',
            'status': 'На рассмотрении',
            'timestamp': datetime.now().isoformat(),
            'data': state['data']
        }
        submissions['suggestions'].append(submission)
        save_data()
        send_message(user_id, f'✅ Ваше предложение №{submission_counter} успешно отправлено!', get_main_keyboard())
        admin_id = 314950036
        admin_msg = f"💡 НОВОЕ ПРЕДЛОЖЕНИЕ №{submission_counter}\n\n👤 Никнейм: {state['data']['nickname']}\n📝 Предложение: {state['data']['suggestion']}\n📅 Дата и время: {state['data']['datetime']}"
        send_message(admin_id, admin_msg, get_approval_keyboard())
        last_submitted_id[admin_id] = submission_counter
        del user_states[user_id]

# =======================
# Основной цикл
# =======================
load_data()
for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text.strip()
        cleanup_old_submissions()

        if text == '❌ Отмена':
            cancel_submission(user_id)
            continue

        if user_id in user_states:
            state_type = user_states[user_id]['type']
            if state_type == 'norm':
                handle_norm_step(user_id, text)
            elif state_type == 'bug':
                handle_bug_step(user_id, text)
            elif state_type == 'suggestion':
                handle_suggestion_step(user_id, text)
        elif text == '📄 Отправить норму':
            start_norm_submission(user_id)
        elif text == '🐞 Нашел баг':
            start_bug_report(user_id)
        elif text == '💡 Предложение':
            start_suggestion(user_id)
        elif text == '📋 Мои заявки':
            show_my_requests(user_id)
        elif text == '❓ Помощь':
            show_help(user_id)
        elif text.lower() in ['/start', 'start', 'старт', '/старт', 'начать', '/начать']:
            send_message(user_id, '👋 Добро пожаловать в бот управления нормами и багами!', get_main_keyboard())
