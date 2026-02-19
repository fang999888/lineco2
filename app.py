import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests

# 載入環境變數
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# LINE 設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# DeepSeek 設定
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SYSTEM_PROMPT = """你是一位碳管理專家，專注於提供具體的排放係數和計算方式。
請根據使用者提供的行業、製程、排放源，回答以下格式：

【範疇】______
【類別】______
【係數】______ (含單位，例如 0.495 kg CO2e/度)
【來源】______
【公式】______

回答要簡潔，只給重點，不要多餘說明。"""

@app.route("/", methods=["GET"])
def home():
    return "LINE Carbon Bot is running."

# 重要：這裡必須指定 methods=['POST']
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    reply_token = event.reply_token

    if user_message.lower() == 'help':
        reply_text = "請輸入格式：\n行業 製程 排放源\n例如：鋼鐵業 電弧爐 用電"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_text))
        return

    parts = user_message.split()
    if len(parts) == 2:
        industry, source = parts
        process = "一般"
    elif len(parts) == 3:
        industry, process, source = parts
    else:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="格式錯誤，請輸入：行業 製程 排放源"))
        return

    result = query_emission(industry, process, source)
    line_bot_api.reply_message(reply_token, TextSendMessage(text=result))

def query_emission(industry, process, source):
    if not DEEPSEEK_API_KEY:
        return "錯誤：DeepSeek API 金鑰未設定"

    prompt = f"行業：{industry}\n製程：{process}\n排放源：{source}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return f"查詢失敗（錯誤碼：{response.status_code}）"
    except Exception as e:
        logger.error(f"Exception: {e}")
        return "查詢過程發生錯誤。"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
