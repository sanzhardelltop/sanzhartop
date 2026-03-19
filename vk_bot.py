import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

class VkBot:
    def __init__(self, token):
        self.vk = vk_api.VkApi(token=token)
        self.longpoll = VkLongPoll(self.vk)

    def listen(self):
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                self.handle_message(event)

    def handle_message(self, event):
        if event.text.startswith("/submit"):  # Norm submission
            self.process_submission(event)
        elif event.text.startswith("/report"):  # Bug report
            self.process_bug_report(event)

    def process_submission(self, event):
        # Handle norm submissions here
        response = "Your norm submission has been received and is awaiting approval."
        self.vk.method('messages.send', {'user_id': event.user_id, 'message': response, 'random_id': 0})

    def process_bug_report(self, event):
        # Handle bug reports here
        response = "Your bug report has been received and is under review."
        self.vk.method('messages.send', {'user_id': event.user_id, 'message': response, 'random_id': 0})

if __name__ == '__main__':
    token = 'YOUR_VK_API_TOKEN'  # Replace with your VK API token
    bot = VkBot(token)
    bot.listen()