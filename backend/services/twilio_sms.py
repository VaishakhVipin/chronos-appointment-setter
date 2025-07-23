import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_ID = os.getenv("TWILIO_ACCOUNT_ID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

client = Client(TWILIO_ACCOUNT_ID, TWILIO_AUTH_TOKEN)

def send_sms(to_number, message, from_number):
    """
    Send an SMS using Twilio.
    Args:
        to_number (str): The recipient's phone number (E.164 format, e.g., +1234567890)
        message (str): The message body
        from_number (str): The Twilio phone number to send from (E.164 format)
    Returns:
        Message SID if successful
    """
    msg = client.messages.create(
        body=message,
        from_=from_number,
        to=to_number
    )
    return msg.sid