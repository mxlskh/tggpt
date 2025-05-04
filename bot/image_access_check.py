import os  # Import the os module to interact with environment variables
from openai import OpenAI  # Import OpenAI SDK
from dotenv import load_dotenv  # Import dotenv to load environment variables from a .env file

# Load environment variables from the .env file (such as your API key)
load_dotenv()

# Initialize the OpenAI client with your API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Generate an image using the OpenAI Image API
# "prompt" defines the scene you want to generate, in this case, a futuristic city skyline at sunset
response = client.Image.create(  # Correct method is Image.create, not images.generate
    prompt="A futuristic city skyline at sunset",  # The prompt that describes the image you want to generate
    size="1024x1024",  # Size of the generated image
    n=1  # The number of images to generate
)

# Print the URL of the generated image (the first image from the response)
print(response['data'][0]['url'])


#Additional Notes:
#API Key: Ensure that your .env file contains your correct OpenAI API key like this:
#OPENAI_API_KEY=your_api_key_here
#Make sure that you have installed the necessary libraries by running:
#pip install openai python-dotenv