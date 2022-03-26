from twilio.rest import Client
import logging


class Notifier:
    def __init__(self, sid: str, token: str, to: str, from_: str):
        if sid == '' or token == '' or to == '' or from_ == '':
            raise ValueError('Not enough args to start notifier')

        self.to = to
        self.from_ = from_
        self.client = Client(sid, token)

    def notify(self, msg: str) -> None:
        """Sends an SMS with the given message to the object's phone number"""
        if self.client is None:
            return

        self.client.messages.create(to=self.to, from_=self.from_, body=msg)
