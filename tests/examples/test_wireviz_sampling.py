#!/usr/bin/env python3
"""
Test script for WireViz sampling functionality

This tests the dual-mode approach:
1. Clients with sampling support get AI-generated diagrams
2. Clients without sampling get intelligent templates
"""

import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


async def test_wireviz_generation():
    """Test WireViz generation with different descriptions"""

    # Import the necessary components
    from src.mcp_arduino_server.components.wireviz import WireViz
    from src.mcp_arduino_server.config import ArduinoServerConfig

    # Create config and component
    config = ArduinoServerConfig()
    wireviz = WireViz(config)

    # Test descriptions
    test_cases = [
        {
            "description": "Arduino with LED on pin 9",
            "expected_template": "led"
        },
        {
            "description": "Connect a servo motor to Arduino pin D9",
            "expected_template": "motor"
        },
        {
            "description": "Temperature sensor connected to analog pin A0",
            "expected_template": "sensor"
        },
        {
            "description": "Push button with pull-up resistor on D2",
            "expected_template": "button"
        },
        {
            "description": "I2C OLED display connected to Arduino",
            "expected_template": "display"  # Contains 'oled' which triggers display template
        },
        {
            "description": "Generic circuit with resistors and capacitors",
            "expected_template": "generic"
        }
    ]

    print("\n" + "="*60)
    print("TESTING WIREVIZ TEMPLATE GENERATION")
    print("="*60 + "\n")

    for test in test_cases:
        print(f"Test: {test['description']}")
        print(f"Expected template type: {test['expected_template']}")

        # Generate template (simulating no sampling available)
        yaml_content = wireviz._generate_template_yaml(test['description'])

        # Check if the right template was selected
        if test['expected_template'] == 'led' and 'LED' in yaml_content:
            print("✅ LED template correctly selected")
        elif test['expected_template'] == 'motor' and 'Servo' in yaml_content:
            print("✅ Motor/Servo template correctly selected")
        elif test['expected_template'] == 'sensor' and 'Sensor' in yaml_content:
            print("✅ Sensor template correctly selected")
        elif test['expected_template'] == 'button' and 'Button' in yaml_content:
            print("✅ Button template correctly selected")
        elif test['expected_template'] == 'display' and 'I2C Display' in yaml_content:
            print("✅ Display template correctly selected")
        elif test['expected_template'] == 'generic' and 'Component1' in yaml_content:
            print("✅ Generic template correctly selected")
        else:
            print("❌ Template selection might be incorrect")

        print("-" * 40)

    print("\n" + "="*60)
    print("TEMPLATE GENERATION TEST COMPLETE")
    print("="*60)

    print("\nKey Insights:")
    print("• Templates are selected based on keywords in the description")
    print("• Each template provides a good starting point for common circuits")
    print("• Users can customize the YAML for their specific needs")
    print("• When sampling IS available, AI will generate custom YAML")


if __name__ == "__main__":
    asyncio.run(test_wireviz_generation())
