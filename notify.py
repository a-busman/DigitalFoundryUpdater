from twilio.rest import Client


class Notifier:
    def __init__(self, sid: str, token: str, to: str, from_: str):
        self.sid = sid
        self.token = token
        self.to = to
        self.from_ = from_

        self.client = Client(self.sid, self.to)

    def notify(self, msg: str) -> None:
        """Sends an SMS with the given message to the object's phone number"""
        self.client.messages.create(to=self.to, from_=self.from_, body=msg)
