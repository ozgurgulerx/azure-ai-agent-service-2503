import os
import json
import requests
from dotenv import load_dotenv

# OpenTelemetry imports using the correct package names
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Azure AI Agent Service imports
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, ToolSet
from azure.identity import DefaultAzureCredential

# --- OpenTelemetry Setup ---

# Create a resource for this service
resource = Resource.create({"service.name": "azure-ai-agent-service"})

# Set up the tracer provider with the resource
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Configure the OTLP exporter (adjust endpoint if needed)
otlp_exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

print("OpenTelemetry tracing is configured.")

# --- Azure AI Agent Service Setup ---

# Load environment variables from .env
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    raise ValueError("PROJECT_CONNECTION_STRING not found in .env.")

# Example data and functions
CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "New York": (40.7128, -74.0060),
    "Tokyo": (35.6895, 139.6917)
}

def get_city_coords(city: str) -> str:
    if city not in CITY_COORDS:
        return json.dumps({"error": f"Coordinates for {city} not found"})
    lat, lon = CITY_COORDS[city]
    return json.dumps({"lat": lat, "lon": lon})

def fetch_weather(lat: float, lon: float) -> str:
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
    try:
        air_quality_index = 42  # Placeholder for an actual API
        return json.dumps({"air_quality_index": air_quality_index})
    except Exception as e:
        return json.dumps({"error": str(e)})

# Register functions as tools
functions_tool = FunctionTool({get_city_coords, fetch_weather, fetch_air_quality})
toolset = ToolSet()
toolset.add(functions_tool)

def run_agent_with_tracing():
    # Initialize the Azure AI Agent client
    project_client = AIProjectClient.from_connection_string(
        conn_str=conn_str,
        credential=DefaultAzureCredential()
    )

    # Create an agent with custom instructions
    agent = project_client.agents.create_agent(
        model="gpt-4o-mini",
        name="multi-call-agent",
        instructions="""
You are an assistant that must:
1) Call get_city_coords first to retrieve lat/lon for the user's city.
2) Then call fetch_weather using those coordinates.
3) Finally, call fetch_air_quality using the same coordinates.
""",
        toolset=toolset
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a conversation thread and send a message
    thread = project_client.agents.create_thread()
    print(f"Created thread, ID: {thread.id}")

    message = project_client.agents.create_message(
        thread_id=thread.id,
        role="user",
        content="Hi, I'd like to know the weather and air quality in Tokyo."
    )
    print(f"Created message, ID: {message.id}")

    # Wrap the agent run in an OpenTelemetry span
    with tracer.start_as_current_span("agent-run"):
        run = project_client.agents.create_and_process_run(
            thread_id=thread.id,
            agent_id=agent.id
        )
    print(f"Run finished with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Retrieve and display conversation messages
    msgs = project_client.agents.list_messages(thread_id=thread.id)
    print("\n--- MESSAGES ---")
    for m in msgs.data:
        role = "User" if m.role == "user" else "Assistant"
        content_text = m.content[0].text.value if (m.content and hasattr(m.content[0], 'text')) else ""
        print(f"{role}: {content_text}")

    # Clean up the agent
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent.")

if __name__ == "__main__":
    run_agent_with_tracing()
