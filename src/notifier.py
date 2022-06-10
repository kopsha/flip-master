import requests


class TelegramNotifier:
    def __init__(self, token, owner_id):
        self.token = token
        self.owner_id = owner_id

    def say(self, message):
        url = (
            "https://api.telegram.org/bot{token}/sendMessage?"
            "chat_id={chat_id}&text={message}"
            "&parse_mode=Markdown&disable_web_page_preview=true"
        ).format(token=self.token, chat_id=self.owner_id, message=message)

        response = requests.get(url)
        data = response.json()
        if not data["ok"]:
            print(
                "Notification error",
                data["error_code"],
                "->",
                data["description"],
            )

        return data
