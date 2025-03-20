import os
import json
import requests
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential

# Load environment variables (only need the Azure connection string)
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    raise ValueError("PROJECT_CONNECTION_STRING not found in .env.")

# A simple mapping from city names to coordinates
CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "New York": (40.7128, -74.0060),
    "Tokyo": (35.6895, 139.6917)
}

# Function to fetch weather using Open‑Meteo API
def fetch_weather(city: str) -> str:
    if city not in CITY_COORDS:
        return json.dumps({"error": "City not supported"})
    lat, lon = CITY_COORDS[city]
    # Simple API call with 4 parameters: latitude, longitude, hourly parameter, forecast days.
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&forecast_days=1"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        # For demonstration, grab the first hourly temperature value.
        hourly = data.get("hourly", {})
        temps = hourly.get("temperature_2m", [])
        temp = temps[0] if temps else None
        return json.dumps({
            "city": city,
            "temperature": temp,
            "units": data.get("hourly_units", {}).get("temperature_2m", "unknown")
        })
    else:
        return json.dumps({"error": "Failed to retrieve weather data"})

# Register the function in a toolset
functions_tool = FunctionTool({fetch_weather})
toolset = ToolSet()
toolset.add(functions_tool)

# Initialize the Azure AI Agent client
project_client = AIProjectClient.from_connection_string(conn_str, DefaultAzureCredential())

# Create an agent with function calling capability
print("Creating AI Agent with gpt-4o-mini and function calling...")
agent = project_client.agents.create_agent(
    model="gpt-4o-mini",
    name="weather-agent",
    instructions="You are a weather bot. Use your tools to answer weather queries.",
    toolset=toolset
)
print(f"Created agent, ID: {agent.id}")

# Start a conversation thread
thread = project_client.agents.create_thread()
print(f"Created thread, ID: {thread.id}")

# Send a user message asking for weather in London
message = project_client.agents.create_message(
    thread_id=thread.id,
    role="user",
    content="What is the weather like in London?"
)
print(f"Created message, ID: {message.id}")

# Process the run (this triggers the function call)
print("Processing run...")
run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
print(f"Run finished with status: {run.status}")
if run.status == "failed":
    print(f"Run failed: {run.last_error}")

# Retrieve and display conversation messages
print("\nRetrieving conversation:")
msgs = project_client.agents.list_messages(thread_id=thread.id)
for m in msgs.data:
    role = "User" if m.role == "user" else "Assistant"
    if m.content and hasattr(m.content[0], 'text'):
        print(f"{role}: {m.content[0].text.value}")

# Clean up: Delete the agent when done
project_client.agents.delete_agent(agent.id)
print("Deleted agent")
