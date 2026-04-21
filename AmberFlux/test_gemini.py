import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents="Say hello in one word."
    )
    print("SUCCESS! Response:", response.text)
except Exception as e:
    print("FAILED:", type(e).__name__, "-", e)