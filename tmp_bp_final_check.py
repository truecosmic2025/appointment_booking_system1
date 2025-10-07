import os
from dotenv import load_dotenv
load_dotenv()
from app.integrations.botpenguin_service import sync_booking_to_botpenguin
sync_booking_to_botpenguin('gglvoice12@gmail.com','2025-10-07T12:00:00+05:30','Coach Test')
print('Done')
