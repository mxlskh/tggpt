import os
from dotenv import load_dotenv
import openai

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

response = openai.Image.create(
    prompt="A futuristic city skyline at sunset",
    n=1,
    size="512x512"
)

image_url = response["data"][0]["url"]
print("Image URL:", image_url)