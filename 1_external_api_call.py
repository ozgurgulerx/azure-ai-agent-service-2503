import os
import json
import requests
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    raise ValueError("PROJECT_CONNECTION_STRING missing")
open_weather_api_key = os.getenv("OPEN_WEATHER_API_KEY")
if not open_weather_api_key:
    raise ValueError("OPEN_WEATHER_API_KEY missing")

# Get coordinates using OpenWeather Geocoding API
def get_city_coordinates(city: str):
    geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={open_weather_api_key}"
    response = requests.get(geocode_url)
    if response.status_code == 200 and response.json():
        location = response.json()[0]
        return location["lat"], location["lon"]
    return None, None

# User function to fetch weather info from One Call API 3.0
def fetch_weather(location: str) -> str:
    """
    Fetches the weather information for the specified location.

    :param location: City name.
    :return: Weather info as a JSON string.
    """
    lat, lon = get_city_coordinates(location)
    if lat is None or lon is None:
        return json.dumps({"error": "City not found"})
    weather_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units=metric&appid={open_weather_api_key}"
    response = requests.get(weather_url)
    if response.status_code == 200:
        data = response.json()
        current = data.get("current", {})
        result = {
            "city": location,
            "temperature": current.get("temp"),
            "feels_like": current.get("feels_like"),
            "description": current.get("weather", [{}])[0].get("description"),
            "wind_speed": current.get("wind_speed"),
            "humidity": current.get("humidity"),
            "uvi": current.get("uvi")
        }
        return json.dumps(result)
    return json.dumps({"error": "Failed to retrieve weather data"})

# Register user function in a set
user_functions = {fetch_weather}

# Create the tool and toolset from the user functions
functions_tool = FunctionTool(user_functions)
toolset = ToolSet()
toolset.add(functions_tool)

# Create the Azure AI Agent client
project_client = AIProjectClient.from_connection_string(conn_str, DefaultAzureCredential())

# Create an agent with the toolset
print("Creating AI Agent with gpt-4o-mini and function calling...")
agent = project_client.agents.create_agent(
    model="gpt-4o-mini",
    name="weather-agent",
    instructions="You are a weather bot. Use the provided functions to answer weather queries.",
    toolset=toolset
)
print(f"Created agent, ID: {agent.id}")

# Create a conversation thread and send a user message
thread = project_client.agents.create_thread()
print(f"Created thread, ID: {thread.id}")
message = project_client.agents.create_message(
    thread_id=thread.id,
    role="user",
    content="What is the weather like in London?"
)
print(f"Created message, ID: {message.id}")

# Create and process the run (this will trigger the function call)
print("Processing run...")
run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
print(f"Run finished with status: {run.status}")
if run.status == "failed":
    print(f"Run failed: {run.last_error}")

# Retrieve and print conversation messages
print("\nRetrieving conversation:")
messages = project_client.agents.list_messages(thread_id=thread.id)
for msg in messages.data:
    role = "User" if msg.role == "user" else "Assistant"
    if msg.content and hasattr(msg.content[0], 'text'):
        print(f"{role}: {msg.content[0].text.value}")

# Delete the agent once finished
project_client.agents.delete_agent(agent.id)
print("Deleted agent")
