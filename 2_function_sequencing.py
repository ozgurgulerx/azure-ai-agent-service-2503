import os
import sys
import time
import json
import requests
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor, ReadableSpan, Span, TracerProvider
from typing import Callable

# -------------------------
# Environment Setup
# -------------------------
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    raise ValueError("PROJECT_CONNECTION_STRING not found in .env or invalid.")

# -------------------------
# Decorator to trace function name
# -------------------------
def trace_function_name(func: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        span = trace.get_current_span()
        if span:
            span.set_attribute("gen_ai.tool.function_name", func.__name__)
        
        # Debug print statements
        print(f"Calling {func.__name__} with args: {args} and kwargs: {kwargs}")
        
        # Clean kwargs of any unexpected arguments
        # Get the function's parameter names
        import inspect
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())
        
        # Filter kwargs to only include valid parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}
        print(f"Using filtered kwargs: {filtered_kwargs}")
        
        result = func(*args, **filtered_kwargs)
        print(f"Function {func.__name__} returned: {result}")
        return result
    return wrapper

# -------------------------
# Example Function Definitions with Decorator
# -------------------------
CITY_COORDS = {
    "London": {"lat": 51.5074, "lon": -0.1278},
    "New York": {"lat": 40.7128, "lon": -74.0060},
    "Tokyo": {"lat": 35.6895, "lon": 139.6917}
}

@trace_function_name
def get_city_coords(city: str) -> str:
    if city not in CITY_COORDS:
        return json.dumps({"error": f"Coordinates for {city} not found"})
    lat = CITY_COORDS[city]["lat"]
    lon = CITY_COORDS[city]["lon"]
    return json.dumps({"lat": lat, "lon": lon})

@trace_function_name
def fetch_weather(city: str = None, lat: float = None, lon: float = None) -> str:
    # If city is provided, get coordinates from it
    if city and not (lat and lon):
        if city not in CITY_COORDS:
            return json.dumps({"error": f"City {city} not supported"})
        lat = CITY_COORDS[city]["lat"]
        lon = CITY_COORDS[city]["lon"]
    
    # If we don't have valid coordinates, return error
    if not (lat and lon):
        return json.dumps({"error": "Missing coordinates"})
        
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&forecast_days=1"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        temps = data.get("hourly", {}).get("temperature_2m", [])
        temp = temps[0] if temps else None
        return json.dumps({
            "temperature": temp,
            "units": data.get("hourly_units", {}).get("temperature_2m", "unknown")
        })
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})

@trace_function_name
def fetch_air_quality(city: str = None, lat: float = None, lon: float = None) -> str:
    # If city is provided, get coordinates from it
    if city and not (lat and lon):
        if city not in CITY_COORDS:
            return json.dumps({"error": f"City {city} not supported"})
        lat = CITY_COORDS[city]["lat"]
        lon = CITY_COORDS[city]["lon"]
    
    # If we don't have valid coordinates, return error
    if not (lat and lon):
        return json.dumps({"error": "Missing coordinates"})
        
    try:
        air_quality_index = 42  # Placeholder value
        return json.dumps({
            "air_quality_index": air_quality_index,
            "lat": lat,
            "lon": lon
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

# -------------------------
# Custom Span Processor for Additional Attributes
# -------------------------
class CustomAttributeSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context=None):
        if span:
            span.set_attribute("trace_sample.sessionid", "123")
            if span.name == "create_message":
                span.set_attribute("trace_sample.message.context", "abc")
    def on_end(self, span: ReadableSpan):
        pass

# -------------------------
# Tracing Setup (Console Tracing)
# -------------------------
provider = TracerProvider()
trace.set_tracer_provider(provider)
provider.add_span_processor(CustomAttributeSpanProcessor())

project_client = AIProjectClient.from_connection_string(
    conn_str=conn_str,
    credential=DefaultAzureCredential()
)
print("Tracing enabled, ensure OpenTelemetry is configured correctly.")

scenario = os.path.basename(__file__)
tracer = trace.get_tracer(__name__)

# -------------------------
# Register Function Tools and Create Agent
# -------------------------
functions_tool = FunctionTool([get_city_coords, fetch_weather, fetch_air_quality])  # Fix: Use list
toolset = ToolSet()
toolset.add(functions_tool)

def run_agent_with_tracing():
    with tracer.start_as_current_span(scenario):
        with project_client:
            # Create an agent with instructions to use the three functions in sequence.
            agent = project_client.agents.create_agent(
                model="gpt-4o-mini",  # Or use os.environ["MODEL_DEPLOYMENT_NAME"]
                name="weather-agent",
                instructions="""
You are a weather bot. When asked about weather and air quality for a location:
1. Call get_city_coords to get coordinates for the city.
2. Use those coordinates to call fetch_weather and fetch_air_quality.
3. Or, call fetch_weather and fetch_air_quality directly with the city name.
4. Provide a nice summary of the weather and air quality information.
""",
                toolset=toolset
            )
            print(f"Created agent, ID: {agent.id}")

            thread = project_client.agents.create_thread()
            print(f"Created thread, ID: {thread.id}")

            message = project_client.agents.create_message(
                thread_id=thread.id,
                role="user",
                content="What are the weather and air quality conditions in London?"
            )
            print(f"Created message, ID: {message.id}")

            print("Processing run...")
            run = project_client.agents.create_and_process_run(
                thread_id=thread.id,
                agent_id=agent.id
            )
            print(f"Run finished with status: {run.status}")
            if run.status == "failed":
                print(f"Run failed: {run.last_error}")

            print("\nRetrieving conversation:")
            msgs = project_client.agents.list_messages(thread_id=thread.id)
            for m in msgs.data:
                role = "User" if m.role == "user" else "Assistant"
                if m.content:
                    text_content = [c.text.value for c in m.content if hasattr(c, 'text')]
                    if text_content:
                        print(f"{role}: {text_content[0]}")

            project_client.agents.delete_agent(agent.id)
            print("Deleted agent.")

if __name__ == "__main__":
    run_agent_with_tracing()
