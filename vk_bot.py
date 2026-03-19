import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from datetime import datetime, timedelta
import json
import os
import re
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

ADMINS = {'lev3438': 'TVER', 'stepkozdez': 'PERM', 'sanzhardell': 'BUGS'}
TOKEN = 'vk1.a.yJNtmSw2-G_BeHBvomh_VdgYfjJb_844uFDNBrwSVmcCi1fPUtJ3U2XdPjNyC-FWWqko6bvjBldYpC5dJL9WINOPS16-T_7cW2YEWMHoX1hq8R4uulyqYAvNvFvhZ148C4gjmFgjNZvM0RGz1TZwRGw0lET3TC5wO5916DiS77z7q82CIwFbI_MrGk3qnnHpoopp9vdRZXOA0GjsnwnLBg'
vk = vk_api.VkApi(token=TOKEN)
api = vk.get_api()
longpoll = VkLongPoll(vk)
DATA_FILE = 'bot_data.json'
user_states = {}
submissions = {'norms': [], 'bugs': []}
submission_counter = 0

def load_data():
    global submissions, submission_counter
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            submissions = data.get('submissions', {'norms': [], 'bugs': []})
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
    save_data()

def get_main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('Отправить норму', color=VkKeyboardColor.POSITIVE)
    kb.add_button('Нашел баг', color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button('Мои заявки', color=VkKeyboardColor.PRIMARY)
    kb.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def get_approval_keyboard():
    kb = VkKeyboard(one_time=True)
    kb.add_button('✅ Одобрить', color=VkKeyboardColor.POSITIVE)
    kb.add_button('❌ Отклонить', color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

def send_message(user_id, message, keyboard=None):
    api.messages.send(user_id=user_id, message=message, keyboard=keyboard, random_id=0)

def validate_vk_link(link):
    pattern = r'(https?://)?(www\.)?vk\.com/\S+|https://vk\.com/wall\d+_\d+'
    return re.match(pattern, link) is not None

def start_norm_submission(user_id):
    user_states[user_id] = {'type': 'norm', 'step': 1, 'data': {}}
    send_message(user_id, '📋 Начнем заполнение анкеты нормы!\n\n1️⃣ Введите ваш никнейм:')

def handle_norm_step(user_id, text):
    state = user_states[user_id]
    if state['step'] == 1:
        state['data']['nickname'] = text
        state['step'] = 2
        send_message(user_id, '2️⃣ Введите вашу должность:')
    elif state['step'] == 2:
        state['data']['position'] = text
        state['step'] = 3
        send_message(user_id, '3️⃣ Опишите проделанную работу:')
    elif state['step'] == 3:
        state['data']['work'] = text
        state['step'] = 4
        send_message(user_id, '4️⃣ Отправьте доказательства (ссылка на пост ВК или фото):')
    elif state['step'] == 4:
        if validate_vk_link(text):
            state['data']['proof'] = text
            state['step'] = 5
            send_message(user_id, '5️⃣ Выберите ваш сервер:\n1 - TVER\n2 - PERM\n\nВведите номер (1 или 2):')
        else:
            send_message(user_id, '❌ Некорректная ссылка! Отправьте ссылку на пост ВК (например: https://vk.com/wall...)')
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
            send_message(user_id, f'✅ Заявка №{submission_counter} отправлена на рассмотрение!\n\nСтатус: На рассмотрении')
            admin_id = 'lev3438' if server == 'TVER' else 'stepkozdez'
            admin_msg = f"📬 Новая заявка №{submission_counter} на норму:\n\n"
            admin_msg += f"👤 Никнейм: {state['data']['nickname']}\n"
            admin_msg += f"💼 Должность: {state['data']['position']}\n"
            admin_msg += f"📝 Работа: {state['data']['work']}\n"
            admin_msg += f"🔗 Доказательства: {state['data']['proof']}\n"
            admin_msg += f"🗺️ Сервер: {server}"
            send_message(admin_id, admin_msg, get_approval_keyboard())
            del user_states[user_id]
        else:
            send_message(user_id, '❌ Введите 1 или 2!')

def start_bug_report(user_id):
    user_states[user_id] = {'type': 'bug', 'step': 1, 'data': {}}
    send_message(user_id, '🐛 Начнем заполнение отчета о баге!\n\n1️⃣ Что за баг:')

def handle_bug_step(user_id, text):
    state = user_states[user_id]
    if state['step'] == 1:
        state['data']['bug_description'] = text
        state['step'] = 2
        send_message(user_id, '2️⃣ Где находится баг:')
    elif state['step'] == 2:
        state['data']['bug_location'] = text
        state['step'] = 3
        send_message(user_id, '3️⃣ Доказательства (ссылка на ВК или фото; чтобы пропустить напишите -):\n\nДоказательства:')
    elif state['step'] == 3:
        if text == '-':
            state['data']['proof'] = 'Не предоставлены'
        else:
            if validate_vk_link(text):
                state['data']['proof'] = text
            else:
                send_message(user_id, '❌ Некорректная ссылка! Отправьте ссылку на пост ВК или введите -')
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
        send_message(user_id, f'✅ Баг №{submission_counter} отправлен на рассмотрение!\n\nСтатус: На рассмотрении')
        admin_msg = f"🐛 Новый отчет о баге №{submission_counter}:\n\n"
        admin_msg += f"❓ Баг: {state['data']['bug_description']}\n"
        admin_msg += f"📍 Место: {state['data']['bug_location']}\n"
        admin_msg += f"🔗 Доказательства: {state['data']['proof']}"
        send_message('sanzhardell', admin_msg, get_approval_keyboard())
        del user_states[user_id]

def show_my_requests(user_id):
    my_norms = [n for n in submissions['norms'] if n['user_id'] == user_id]
    my_bugs = [b for b in submissions['bugs'] if b['user_id'] == user_id]
    message = '📋 Ваши заявки:\n\n'
    if my_norms:
        message += '📝 НОРМЫ:\n'
        for norm in my_norms:
            message += f"  №{norm['id']} - {norm['status']}\n"
    if my_bugs:
        message += '\n🐛 БАГИ:\n'
        for bug in my_bugs:
            message += f"  №{bug['id']} - {bug['status']}\n"
    if not my_norms and not my_bugs:
        message = '📋 У вас нет заявок'
    send_message(user_id, message, get_main_keyboard())

def show_help(user_id):
    help_text = '''📚 СПРАВКА ПО ИСПОЛЬЗОВАНИЮ БОТА:\n\n✅ ОТПРАВИТЬ НОРМУ:\n1. Выберите кнопку "Отправить норму"\n2. Заполните форму:\n   - Никнейм\n   - Должность\n   - Проделанная работа\n   - Доказательства (ссылка на пост ВК)\n   - Выберите сервер (1-TVER, 2-PERM)\n3. Заявка отправится основателю сервера\n4. Проверьте статус в "Мои заявки"\n\n🐛 НАШЕЛ БАГ:\n1. Выберите кнопку "Нашел баг"\n2. Заполните форму:\n   - Описание бага\n   - Место нахождения\n   - Доказательства (опционально, введите -)\n3. Заявка отправится модератору\n4. Проверьте статус в "Мои заявки"\n\n📋 МОИ ЗАЯВКИ:\n- Просмотрите все ваши заявки и их статусы\n- Статусы: На рассмотрении, Одобрена, Отклонена\n- Заявки удаляются через 7 дней\n\nСтатусы:\n✅ Одобрена - заявка принята\n❌ Отклонена - заявка отклонена\n⏳ На рассмотрении - ожидание решения''' 
    send_message(user_id, help_text, get_main_keyboard())

load_data()

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text
        cleanup_old_submissions()
        if user_id in user_states:
            state_type = user_states[user_id]['type']
            if state_type == 'norm':
                handle_norm_step(user_id, text)
            elif state_type == 'bug':
                handle_bug_step(user_id, text)
        elif text == 'Отправить норму':
            start_norm_submission(user_id)
        elif text == 'Нашел баг':
            start_bug_report(user_id)
        elif text == 'Мои заявки':
            show_my_requests(user_id)
        elif text == 'Помощь':
            show_help(user_id)
        elif text == '/start':
            send_message(user_id, '👋 Добро пожаловать в бот управления нормами и багами!', get_main_keyboard())
        elif user_id == 'lev3438' or user_id == 'stepkozdez' or user_id == 'sanzhardell':
            if text == '✅ Одобрить':
                send_message(user_id, 'Заявка одобрена!')
                for norm in submissions['norms']:
                    if norm['status'] == 'На рассмотрении':
                        norm['status'] = 'Одобрена'
                        send_message(norm['user_id'], '✅ Ваша заявка одобрена!')
                save_data()
                break
            elif text == '❌ Отклонить':
                send_message(user_id, 'Заявка отклонена.')
                for norm in submissions['norms']:
                    if norm['status'] == 'На рассмотрении':
                        norm['status'] = 'Отклонена'
                        send_message(norm['user_id'], '❌ Ваша заявка отклонена.')
                save_data()
                break
        else:
            send_message(user_id, '👋 Используйте меню ниже для навигации', get_main_keyboard())