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
    raise ValueError("PROJECT_CONNECTION_STRING not found in .env.")

# 1) Example data and functions
CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "New York": (40.7128, -74.0060),
    "Tokyo": (35.6895, 139.6917)
}

def get_city_coords(city: str) -> str:
    """Retrieve latitude and longitude for a given city."""
    if city not in CITY_COORDS:
        return json.dumps({"error": f"Coordinates for {city} not found"})
    lat, lon = CITY_COORDS[city]
    return json.dumps({"lat": lat, "lon": lon})

def fetch_weather(lat: float, lon: float) -> str:
    """Fetch weather data for a given latitude and longitude."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&forecast_days=1"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            temps = data.get("hourly", {}).get("temperature_2m", [])
            temp = temps[0] if temps else None
            return json.dumps({
                "temperature": temp,
                "units": data.get("hourly_units", {}).get("temperature_2m", "unknown")
            })
        else:
            return json.dumps({"error": "Weather API call failed"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def fetch_air_quality(lat: float, lon: float) -> str:
    """Fetch air quality data (simulated response)."""
    try:
        air_quality_index = 42  # Placeholder for actual API
        return json.dumps({"air_quality_index": air_quality_index})
    except Exception as e:
        return json.dumps({"error": str(e)})

# 2) Register functions as tools
functions_tool = FunctionTool({get_city_coords, fetch_weather, fetch_air_quality})
toolset = ToolSet()
toolset.add(functions_tool)

def main():
    # 3) Initialize Azure AI Agent Client
    project_client = AIProjectClient.from_connection_string(
        conn_str=conn_str,
        credential=DefaultAzureCredential()
    )

    # 4) Create an agent with function sequencing constraints
    agent = project_client.agents.create_agent(
        model="gpt-4o-mini",
        name="multi-call-agent",
        instructions="""
You are an assistant that must:
1) Always call get_city_coords first to get lat/lon for the user's city.
2) Then call fetch_weather using the lat/lon.
3) If the user also wants air quality info, call fetch_air_quality with the same lat/lon.
Ensure that no function is skipped and results are aggregated in a structured response.
""",
        toolset=toolset
    )
    print(f"Created agent, ID: {agent.id}")

    # 5) Create a conversation thread and user message
    thread = project_client.agents.create_thread()
    print(f"Created thread, ID: {thread.id}")

    message = project_client.agents.create_message(
        thread_id=thread.id,
        role="user",
        content="Hi, I'd like to know the weather and air quality in Tokyo."
    )
    print(f"Created message, ID: {message.id}")

    # 6) Process a run
    print("Processing run...")
    run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # 7) Retrieve and log run steps
    run_steps = project_client.agents.list_run_steps(thread_id=thread.id, run_id=run.id)
    print("\n--- RUN STEPS ---")
    for i, step in enumerate(run_steps.data, start=1):
        print(f"Step {i}: Type - {step.type}")
        if hasattr(step, "tool_calls") and step.tool_calls:
            for tool_call in step.tool_calls:
                print(f"  Function Name: {tool_call.name}")
                print(f"  Arguments:    {tool_call.arguments}")
                print(f"  Response:     {tool_call.response}")
        print("-"*40)

    # 8) Retrieve and display conversation messages
    print("\n--- MESSAGES ---")
    msgs = project_client.agents.list_messages(thread_id=thread.id)
    for m in msgs.data:
        role = "User" if m.role == "user" else "Assistant"
        content_text = m.content[0].text.value if (m.content and hasattr(m.content[0], 'text')) else ""
        print(f"{role}: {content_text}")

    # 9) Clean up agent
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent.")

if __name__ == "__main__":
    main()
