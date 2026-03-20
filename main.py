from flask import Flask, request
from threading import Thread
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

app = Flask(__name__)

@app.route('/')
def home():
    return "VK Bot is running"

def run_flask():
    app.run(port=5000)

def run_vk_bot():
    vk_session = vk_api.VkApi(token='YOUR_TOKEN_HERE')
    longpoll = VkLongPoll(vk_session)
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            print(f'New message: {event.text}')

if __name__ == '__main__':
    Thread(target=run_flask).start()
    run_vk_bot()