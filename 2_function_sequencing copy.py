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
from datetime import datetime

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
    with trace.get_tracer(__name__).start_as_current_span("get_city_coords") as span:
        span.set_attribute("function.name", "get_city_coords")
        span.set_attribute("function.city", city)
        print(f"[TRACE] get_city_coords called with city={city}")
        
        if city not in CITY_COORDS:
            result = json.dumps({"error": f"Coordinates for {city} not found"})
            span.set_attribute("function.result", result)
            print(f"[TRACE] get_city_coords returned: {result}")
            return result
            
        lat = CITY_COORDS[city]["lat"]
        lon = CITY_COORDS[city]["lon"]
        result = json.dumps({"lat": lat, "lon": lon})
        span.set_attribute("function.result", result)
        print(f"[TRACE] get_city_coords returned: {result}")
        return result

def fetch_weather(city: str = None, lat: float = None, lon: float = None) -> str:
    with trace.get_tracer(__name__).start_as_current_span("fetch_weather") as span:
        span.set_attribute("function.name", "fetch_weather")
        span.set_attribute("function.city", str(city))
        span.set_attribute("function.lat", str(lat))
        span.set_attribute("function.lon", str(lon))
        print(f"[TRACE] fetch_weather called with city={city}, lat={lat}, lon={lon}")
        
        if city and not (lat and lon):
            if city not in CITY_COORDS:
                result = json.dumps({"error": f"City {city} not supported"})
                span.set_attribute("function.result", result)
                print(f"[TRACE] fetch_weather returned: {result}")
                return result
            lat = CITY_COORDS[city]["lat"]
            lon = CITY_COORDS[city]["lon"]
        
        if not (lat and lon):
            result = json.dumps({"error": "Missing coordinates"})
            span.set_attribute("function.result", result)
            print(f"[TRACE] fetch_weather returned: {result}")
            return result
            
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m&forecast_days=1"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            temps = data.get("hourly", {}).get("temperature_2m", [])
            temp = temps[0] if temps else None
            result = json.dumps({
                "temperature": temp,
                "units": data.get("hourly_units", {}).get("temperature_2m", "unknown")
            })
            span.set_attribute("function.result", result)
            print(f"[TRACE] fetch_weather returned: {result}")
            return result
        except requests.RequestException as e:
            result = json.dumps({"error": str(e)})
            span.set_attribute("function.result", result)
            span.set_status(trace.StatusCode.ERROR)
            span.record_exception(e)
            print(f"[TRACE] fetch_weather returned error: {result}")
            return result

def fetch_air_quality(city: str = None, lat: float = None, lon: float = None) -> str:
    with trace.get_tracer(__name__).start_as_current_span("fetch_air_quality") as span:
        span.set_attribute("function.name", "fetch_air_quality")
        span.set_attribute("function.city", str(city))
        span.set_attribute("function.lat", str(lat))
        span.set_attribute("function.lon", str(lon))
        print(f"[TRACE] fetch_air_quality called with city={city}, lat={lat}, lon={lon}")
        
        if city and not (lat and lon):
            if city not in CITY_COORDS:
                result = json.dumps({"error": f"City {city} not supported"})
                span.set_attribute("function.result", result)
                print(f"[TRACE] fetch_air_quality returned: {result}")
                return result
            lat = CITY_COORDS[city]["lat"]
            lon = CITY_COORDS[city]["lon"]
        
        if not (lat and lon):
            result = json.dumps({"error": "Missing coordinates"})
            span.set_attribute("function.result", result)
            print(f"[TRACE] fetch_air_quality returned: {result}")
            return result
            
        try:
            air_quality_index = 42  # Placeholder value
            result = json.dumps({
                "air_quality_index": air_quality_index,
                "lat": lat,
                "lon": lon
            })
            span.set_attribute("function.result", result)
            print(f"[TRACE] fetch_air_quality returned: {result}")
            return result
        except Exception as e:
            result = json.dumps({"error": str(e)})
            span.set_attribute("function.result", result)
            span.set_status(trace.StatusCode.ERROR)
            span.record_exception(e)
            print(f"[TRACE] fetch_air_quality returned error: {result}")
            return result

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
def get_city_coords_wrapper(city: str) -> str:
    return get_city_coords(city=city)

def fetch_weather_wrapper(city: str = None, lat: float = None, lon: float = None) -> str:
    if city is not None:
        return fetch_weather(city=city)
    elif lat is not None and lon is not None:
        return fetch_weather(lat=lat, lon=lon)
    else:
        return json.dumps({"error": "Missing required parameters"})

def fetch_air_quality_wrapper(city: str = None, lat: float = None, lon: float = None) -> str:
    if city is not None:
        return fetch_air_quality(city=city)
    elif lat is not None and lon is not None:
        return fetch_air_quality(lat=lat, lon=lon)
    else:
        return json.dumps({"error": "Missing required parameters"})

functions_tool = FunctionTool([
    get_city_coords_wrapper,
    fetch_weather_wrapper,
    fetch_air_quality_wrapper
])
toolset = ToolSet()
toolset.add(functions_tool)

def run_agent_with_tracing():
    with tracer.start_as_current_span("agent_run") as main_span:
        main_span.set_attribute("run.type", "weather_query")
        main_span.set_attribute("run.start_time", datetime.now().isoformat())
        
        with project_client:
            # Create an agent with instructions to use the three functions in sequence.
            with tracer.start_as_current_span("agent.create") as span:
                agent = project_client.agents.create_agent(
                    model="gpt-4o-mini",
                    name="weather-agent",
                    instructions="""You are a weather bot. When users ask about weather or air quality,
                    call required functions in required order and respond..
                    """,
                    toolset=toolset
                )
                span.set_attribute("agent.id", agent.id)
                print(f"Created agent, ID: {agent.id}")

            # Start a conversation thread
            with tracer.start_as_current_span("thread.create") as span:
                thread = project_client.agents.create_thread()
                span.set_attribute("thread.id", thread.id)
                print(f"Created thread, ID: {thread.id}")

            # Send a user message
            with tracer.start_as_current_span("message.create") as span:
                message_content = "What are the current temperature and air quality conditions in London? Please provide both pieces of information."
                span.set_attribute("message.content", message_content)
                
                message = project_client.agents.create_message(
                    thread_id=thread.id,
                    role="user",
                    content=message_content
                )
                span.set_attribute("message.id", message.id)
                print(f"Created message, ID: {message.id}")

            # Process the agent run
            print("Processing run...")
            with tracer.start_as_current_span("run.process") as span:
                run = project_client.agents.create_and_process_run(
                    thread_id=thread.id,
                    agent_id=agent.id
                )
                span.set_attribute("run.status", str(run.status))
                print(f"Run finished with status: {run.status}")
                if run.status == "failed":
                    span.set_attribute("run.error", str(run.last_error))
                    print(f"Run failed: {run.last_error}")

            # Retrieve and display conversation messages
            print("\nRetrieving conversation:")
            with tracer.start_as_current_span("messages.retrieve") as span:
                msgs = project_client.agents.list_messages(thread_id=thread.id)
                span.set_attribute("messages.count", len(msgs.data))
                
                for m in msgs.data:
                    role = "User" if m.role == "user" else "Assistant"
                    if m.content:
                        text_content = [c.text.value for c in m.content if hasattr(c, 'text')]
                        if text_content:
                            print(f"{role}: {text_content[0]}")
                            if role == "Assistant":
                                span.set_attribute("assistant.response", text_content[0])

            # Cleanup
            with tracer.start_as_current_span("agent.delete") as span:
                project_client.agents.delete_agent(agent.id)
                print("Deleted agent.")
        
        main_span.set_attribute("run.end_time", datetime.now().isoformat())

if __name__ == "__main__":
    run_agent_with_tracing()
