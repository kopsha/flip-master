import requests


class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id

    def updates(self):
        url = "https://api.telegram.org/bot{token}/getUpdates".format(
            token=self.token,
        )
        response = requests.get(url)
        return response.json()

    def say(self, message):
        url = (
            "https://api.telegram.org/bot{token}/sendMessage?"
            "chat_id={chat_id}&text={message}"
            "&parse_mode=Markdown&disable_web_page_preview=true"
        ).format(token=self.token, chat_id=self.chat_id, message=message)

        response = requests.get(url)
        data = response.json()
        if not data["ok"]:
            print(
                "Notification error {code}: {description}".format(
                    code=data["error_code"],
                    description=data["description"],
                )
            )

        return data
