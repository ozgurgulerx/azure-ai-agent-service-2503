import os
import sys
import json
import requests
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor, ReadableSpan, Span, TracerProvider
from typing import Dict, Any

# -------------------------
# Environment Setup
# -------------------------
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    raise ValueError("PROJECT_CONNECTION_STRING not found in .env or invalid.")

# -------------------------
# Example Function Definitions
# -------------------------
CITY_COORDS = {
    "London": {"lat": 51.5074, "lon": -0.1278},
    "New York": {"lat": 40.7128, "lon": -74.0060},
    "Tokyo": {"lat": 35.6895, "lon": 139.6917}
}

def get_city_coords(city: str) -> str:
    """ Returns coordinates for a given city """
    if city not in CITY_COORDS:
        return json.dumps({"error": f"Coordinates for {city} not found"})
    return json.dumps(CITY_COORDS[city])

def fetch_weather(city: str) -> str:
    """ Fetches weather information based on city name """
    if city not in CITY_COORDS:
        return json.dumps({"error": "City not supported"})
    
    lat, lon = CITY_COORDS[city]["lat"], CITY_COORDS[city]["lon"]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&forecast_days=1"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        temp = data.get("hourly", {}).get("temperature_2m", [None])[0]
        result = {
            "city": city,
            "temperature": temp,
            "units": data.get("hourly_units", {}).get("temperature_2m", "unknown")
        }
        return json.dumps(result)
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})

def fetch_air_quality(lat: float, lon: float) -> str:
    """
    Fetches air quality information using latitude and longitude
    """
    if lat is None or lon is None:
        return json.dumps({"error": "Missing latitude or longitude"})
    
    # In a real implementation, you would call an actual API
    # This is a mock response for demonstration
    return json.dumps({"air_quality_index": 42, "lat": lat, "lon": lon})

# -------------------------
# Custom Span Processor for Additional Attributes
# -------------------------
class CustomAttributeSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context=None):
        if span:
            span.set_attribute("trace_sample.sessionid", "123")
    def on_end(self, span: ReadableSpan):
        pass

# -------------------------
# Tracing Setup (Console Tracing)
# -------------------------
provider = TracerProvider()
trace.set_tracer_provider(provider)
provider.add_span_processor(CustomAttributeSpanProcessor())

# Initialize AI Project Client
project_client = AIProjectClient.from_connection_string(
    conn_str=conn_str,
    credential=DefaultAzureCredential()
)
print("Tracing enabled, ensure OpenTelemetry is configured correctly.")

tracer = trace.get_tracer(__name__)

# -------------------------
# Register Function Tools and Create Agent
# -------------------------
functions_tool = FunctionTool([
    get_city_coords,
    fetch_weather,
    fetch_air_quality
])

toolset = ToolSet()
toolset.add(functions_tool)

def run_agent_with_tracing():
    with tracer.start_as_current_span("weather_bot_run"):
        with project_client:
            # Create an agent
            agent = project_client.agents.create_agent(
                model="gpt-4o-mini",
                name="weather-agent",
                instructions="You are a weather bot. Use your tools to answer weather and air quality queries.",
                toolset=toolset
            )
            print(f"Created agent, ID: {agent.id}")

            # Start a conversation thread
            thread = project_client.agents.create_thread()
            print(f"Created thread, ID: {thread.id}")

            # Send a user message
            message = project_client.agents.create_message(
                thread_id=thread.id,
                role="user",
                content="What are the weather and air quality conditions in London?"
            )
            print(f"Created message, ID: {message.id}")

            # Process the agent run
            print("Processing run...")
            run = project_client.agents.create_and_process_run(
                thread_id=thread.id,
                agent_id=agent.id
            )
            print(f"Run finished with status: {run.status}")
            if run.status == "failed":
                print(f"Run failed: {run.last_error}")

            # Retrieve and display conversation messages
            print("\nRetrieving conversation:")
            msgs = project_client.agents.list_messages(thread_id=thread.id)
            for m in msgs.data:
                role = "User" if m.role == "user" else "Assistant"
                if m.content:
                    text_content = [c.text.value for c in m.content if hasattr(c, 'text')]
                    if text_content:
                        print(f"{role}: {text_content[0]}")

            # Cleanup
            project_client.agents.delete_agent(agent.id)
            print("Deleted agent.")

if __name__ == "__main__":
    run_agent_with_tracing()
