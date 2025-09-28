# MCP Arduino Server - Sampling Support Documentation

## Overview

The Arduino MCP Server supports dual-mode operation for AI-powered features like WireViz circuit diagram generation from natural language descriptions. This document explains how the server handles both clients with sampling support and those without.

## What is MCP Sampling?

MCP Sampling is a capability where MCP clients can provide LLM (Large Language Model) functionality to MCP servers. This allows servers to request AI completions from the client's underlying model. It's essentially the reverse of the typical flow - instead of the client asking the server for data, the server asks the client to generate content using AI.

## The Dual-Mode Approach

The Arduino MCP Server implements a progressive enhancement strategy:

1. **Always Try Sampling First**: For clients that support sampling, we get AI-generated content
2. **Graceful Fallback**: For clients without sampling, we provide intelligent templates
3. **Never Remove Functionality**: All features work for all clients, just with different levels of sophistication

## Client Compatibility

### Clients WITH Sampling Support
- **Cursor**: Full sampling support ✅
- **VS Code MCP Extension**: Full sampling support ✅
- **Custom MCP Clients**: If they declare and implement sampling ✅

### Clients WITHOUT Sampling Support
- **Claude Desktop (claude-code)**: No sampling support ❌
  - Does not declare sampling capability in handshake
  - Does not implement `sampling/createMessage` endpoint
  - Falls back to intelligent templates

## How WireViz Generation Works

### With Sampling (AI-Powered)
```python
# When client supports sampling:
1. User: "Generate circuit for LED with button"
2. Server → Client: "Please generate WireViz YAML for this description"
3. Client → Server: [AI-generated custom YAML]
4. Server: Renders diagram from AI-generated YAML
```

### Without Sampling (Template-Based)
```python
# When client doesn't support sampling:
1. User: "Generate circuit for LED with button"
2. Server: Detects keywords ("LED", "button")
3. Server: Selects appropriate template
4. Server: Renders diagram from template YAML
```

## Intelligent Template Selection

When sampling isn't available, the server provides smart templates based on keywords:

| Keywords | Template Type | Components Included |
|----------|--------------|-------------------|
| `led` | LED Circuit | Arduino, LED with resistor, connections |
| `motor`, `servo` | Motor Control | Arduino, Servo/Motor, power connections |
| `sensor` | Sensor Circuit | Arduino, Generic sensor, analog/digital inputs |
| `button`, `switch` | Button Input | Arduino, Push button, pull-up resistor |
| `display`, `lcd`, `oled` | Display Circuit | Arduino, I2C display, SDA/SCL connections |
| *(none of above)* | Generic | Arduino, customizable component, basic connections |

## Technical Implementation

### Capability Detection
```python
# Check if client has sampling capability
if hasattr(ctx, 'sample') and callable(ctx.sample):
    try:
        result = await ctx.sample(messages, max_tokens=2000)
        # Use AI-generated content
    except Exception as e:
        # Fall back to templates
```

### FastMCP Context Patch

For Claude Desktop, we've applied a patch to FastMCP to bypass the capability check since Claude Desktop has the underlying capability but doesn't declare it properly:

**Location**: `.venv/lib/python3.11/site-packages/fastmcp/server/context.py`

**Change**: Set `should_fallback = False` to always attempt sampling even when not declared

## Error Handling

The server handles various failure scenarios:

1. **Client doesn't declare sampling**: Use templates
2. **Client declares but doesn't implement**: Catch "Method not found", use templates
3. **Sampling returns empty**: Use templates
4. **Network/timeout errors**: Use templates

## Benefits of This Approach

1. **Universal Compatibility**: Works with ALL MCP clients
2. **Progressive Enhancement**: Better experience for capable clients
3. **Predictable Fallback**: Always produces useful output
4. **No Breaking Changes**: Existing functionality preserved
5. **User-Friendly**: Clear feedback about which mode was used

## Testing

Run the test script to verify template generation:
```bash
python test_wireviz_sampling.py
```

## Future Improvements

1. **Enhanced Templates**: More circuit types and components
2. **Template Customization**: User-defined template library
3. **Hybrid Mode**: Combine templates with partial AI generation
4. **Client Detection**: Better identification of client capabilities
5. **Caching**: Remember which clients support sampling

## Troubleshooting

### "Method not found" Error
- **Cause**: Client doesn't implement sampling endpoint
- **Solution**: Automatic fallback to templates

### Templates Instead of AI Generation
- **Cause**: Client doesn't support sampling
- **Solution**: Working as designed - customize the template YAML manually

### Wrong Template Selected
- **Cause**: Keywords might match multiple templates
- **Solution**: Template selection order prioritizes displays over LEDs

## For Developers

### Adding New Templates

1. Add keyword detection in `_generate_template_yaml()`
2. Create new template method (e.g., `_generate_relay_template()`)
3. Include appropriate components and connections
4. Test with various descriptions

### Debugging Sampling Issues

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Use client debug tools:
```bash
# Check what capabilities the client declared
mcp-arduino-server client_declared_capabilities

# Test sampling support
mcp-arduino-server client_test_sampling
```

## Conclusion

The dual-mode approach ensures that the Arduino MCP Server provides value to all users, regardless of their client's capabilities. Users with sampling-capable clients get AI-powered features, while others get intelligent templates that provide excellent starting points for their circuits.