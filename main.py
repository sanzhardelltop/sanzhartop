from flask import Flask
import os

app = Flask(__name__)

# Bind to 0.0.0.0 with environment variables for VK bot
VK_TOKEN = os.getenv('VK_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')

@app.route('/')
def hello():
    return 'Hello, VK!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)