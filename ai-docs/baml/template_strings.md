# BAML Template Strings

## Version
BAML 0.206.1

## Overview
This document covers the correct syntax and usage of BAML template strings, based on lessons learned during development.

## Critical Syntax Requirements

### Template String References
**CRITICAL**: BAML template strings MUST be called with parentheses syntax:

```baml
// ✅ CORRECT
{{ HardConstraints() }}
{{ ReferenceInstructionsPlatforms() }}
{{ PrintKnownPlatforms(knownPlatforms) }}

// ❌ WRONG - Will show as <macro> tags
{{ HardConstraints }}
{{ ReferenceInstructionsPlatforms }}
{{ PrintKnownPlatforms }}
```

### Common Error Indicators
- Template strings showing as `<macro TemplateName>` tags in final HTTP requests
- Template content not expanding in generated prompts
- Functions working but prompts containing literal macro references

## Correct Usage Examples

### Basic Template String
```baml
template_string HardConstraints() #"
  Hard constraints for the downstream agent:
  - Output JSON only. No prose. No code fences.
  - Conform exactly to **Output schema**. Unknown keys forbidden.
  - Use null for optionals, [] for arrays. Keep numbers numeric.
  - Enums must be valid or use appropriate values.
  - On validation failure, re-emit corrected JSON only.
  - Include one minimal valid example.
"#

function ResearchFunction() -> string {
  client GPT5MiniGeneral
  prompt #"
    Some prompt text
    {{ HardConstraints() }}
    More prompt text
  "#
}
```

### Template String with Parameters
```baml
template_string PrintKnownPlatforms(knownPlatforms: TechPlatforms[]) #"
  KNOWN PLATFORMS (check for duplicates and use for parent_suite_ids references):
  {% for known_platform in knownPlatforms %}
  - ID: {{ known_platform.id }}
    Name: {{ known_platform.name }}
    Description: {{ known_platform.description }}
  {% endfor %}
"#

function ResearchPlatform(platform: TechPlatforms, knownPlatforms: TechPlatforms[]) -> string {
  client GPT5MiniGeneral
  prompt #"
    Platform to research: {{ platform }}
    {{ PrintKnownPlatforms(knownPlatforms) }}
    {{ HardConstraints() }}
  "#
}
```

## Validation

### Testing Template String Expansion
To verify template strings are working correctly:

```python
from baml_client.async_client import b

# Test the function and inspect HTTP request
http_client = getattr(b, '_BamlAsyncClient__http_request', None)
req = await http_client.YourFunction()
body = getattr(req, 'body', None)
if body and hasattr(body, 'text'):
    text_content = body.text()
    
    # Check for proper expansion
    if '<macro' in text_content:
        print('❌ Template strings not expanded - check syntax')
    elif 'Expected template content' in text_content:
        print('✅ Template strings working correctly')
```

### What to Look For
- **Success**: Template content appears in the final prompt
- **Failure**: `<macro TemplateName>` tags in the HTTP request body
- **Partial**: Some template strings work, others don't (check syntax consistency)

## Troubleshooting

### Common Issues
1. **Missing Parentheses**: Most common error - forgetting `()` after template name
2. **Incorrect Parameters**: Mismatched parameter types or names
3. **Syntax Errors**: Malformed template string definitions
4. **Client Not Regenerated**: Changes to template strings require `baml-cli generate`

### Debug Steps
1. Check template string syntax in `baml_src/template_strings/`
2. Verify function calls use `{{ TemplateName() }}` syntax
3. Regenerate BAML client: `baml-cli generate`
4. Test with HTTP request inspection
5. Check BAML CLI version compatibility

## Best Practices

### Template String Design
- Keep template strings focused and single-purpose
- Use descriptive names that indicate their function
- Include parameters for dynamic content
- Add comments explaining complex logic

### Function Integration
- Always use parentheses syntax when calling template strings
- Test template string expansion during development
- Document template string dependencies
- Keep template strings in dedicated files

### Maintenance
- Update template strings when requirements change
- Test after BAML version updates
- Validate template string expansion in CI/CD
- Document template string usage patterns

## Resources

### Official Documentation
- [BAML Template Strings](https://baml.ai/docs) (when available)
- [BAML GitHub Repository](https://github.com/BoundaryML/baml)

### Project-Specific
- Template strings are defined in `baml_src/template_strings/template_strings.baml`
- Used primarily in `baml_src/functions/intake_prompts.baml`
- Generated client code in `baml_client/` (DO NOT EDIT)

---

**Remember**: Always use parentheses syntax `{{ TemplateName() }}` when referencing template strings in BAML functions!
