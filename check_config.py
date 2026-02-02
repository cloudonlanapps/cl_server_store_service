import sys
from pathlib import Path

# Add tests directory to path
sys.path.append(str(Path("tests").absolute()))

try:
    from conftest import IntegrationConfig
    print("Class found")
    print(f"Fields: {IntegrationConfig.__fields__.keys()}")
    inst = IntegrationConfig(username="a", password="b")
    print(f"Instance mqtt_url: {inst.mqtt_url}")
except Exception as e:
    print(f"Error: {e}")
