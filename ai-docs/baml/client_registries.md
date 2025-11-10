---
title: Client Registry
---

If you need to modify the model / parameters for an LLM client at runtime, you can modify the `ClientRegistry` for any specified function.

<Tabs>

<Tab title="Python" language="python">

```python
import os
from baml_py import ClientRegistry

async def run():
    cr = ClientRegistry()
    # Creates a new client
    cr.add_llm_client(name='MyAmazingClient', provider='openai', options={
        "model": "gpt-4o",
        "temperature": 0.7,
        "api_key": os.environ.get('OPENAI_API_KEY')
    })
    
    # Creates a client using the OpenAI Responses API
    cr.add_llm_client(name='MyResponsesClient', provider='openai-responses', options={
        "model": "gpt-4.1",
        "api_key": os.environ.get('OPENAI_API_KEY')
    })
    
    # Sets MyAmazingClient as the primary client
    cr.set_primary('MyAmazingClient')

    # ExtractResume will now use MyAmazingClient as the calling client
    res = await b.ExtractResume("...", { "client_registry": cr })
```

</Tab>

<Tab title="TypeScript" language="typescript">
```typescript
import { ClientRegistry } from '@boundaryml/baml'

async function run() {
    const cr = new ClientRegistry()
    // Creates a new client
    cr.addLlmClient('MyAmazingClient', 'openai', {
        model: "gpt-4o",
        temperature: 0.7,
        api_key: process.env.OPENAI_API_KEY
    })
    
    // Creates a client using the OpenAI Responses API
    cr.addLlmClient('MyResponsesClient', 'openai-responses', {
        model: "gpt-4.1",
        api_key: process.env.OPENAI_API_KEY
    })
    
    // Sets MyAmazingClient as the primary client
    cr.setPrimary('MyAmazingClient')

    // ExtractResume will now use MyAmazingClient as the calling client
    const res = await b.ExtractResume("...", { clientRegistry: cr })
}
```
</Tab>

<Tab title="Ruby" language="ruby">

```ruby
require_relative "baml_client/client"

def run
  cr = Baml::ClientRegistry.new

  # Creates a new client
  cr.add_llm_client(
    'MyAmazingClient',
    'openai',
    {
      model: 'gpt-4o',
      temperature: 0.7,
      api_key: ENV['OPENAI_API_KEY']
    }
  )

  # Creates a client using the OpenAI Responses API
  cr.add_llm_client(
    'MyResponsesClient',
    'openai-responses',
    {
      model: 'gpt-4.1',
      api_key: ENV['OPENAI_API_KEY']
    }
  )

  # Sets MyAmazingClient as the primary client
  cr.set_primary('MyAmazingClient')

  # ExtractResume will now use MyAmazingClient as the calling client
  res = Baml.Client.extract_resume(input: '...', baml_options: { client_registry: cr })
end

# Call the asynchronous function
run
```
</Tab>

<Tab title="Go" language="go">

```go
package main

import (
    "context"
    "fmt"
    "os"
    
    "github.com/boundaryml/baml"
)

func main() {
    ctx := context.Background()
    
    // Create a client registry
    cr := baml.NewClientRegistry()
    
    // Creates a new client
    err := cr.AddLLMClient("MyAmazingClient", "openai", map[string]interface{}{
        "model":       "gpt-4o",
        "temperature": 0.7,
        "api_key":     os.Getenv("OPENAI_API_KEY"),
    })
    if err != nil {
        panic(fmt.Sprintf("Failed to add client: %v", err))
    }
    
    // Creates a client using the OpenAI Responses API
    err = cr.AddLLMClient("MyResponsesClient", "openai-responses", map[string]interface{}{
        "model":   "gpt-4.1",
        "api_key": os.Getenv("OPENAI_API_KEY"),
    })
    if err != nil {
        panic(fmt.Sprintf("Failed to add responses client: %v", err))
    }
    
    // Sets MyAmazingClient as the primary client
    cr.SetPrimary("MyAmazingClient")
    
    // ExtractResume will now use MyAmazingClient as the calling client
    res, err := baml.ExtractResume(ctx, "...", b.WithClientRegistry(cr))
    if err != nil {
        panic(fmt.Sprintf("Failed to extract resume: %v", err))
    }
    
    fmt.Printf("Result: %+v\n", res)
}
```
</Tab>

<Tab title="OpenAPI" language="openapi">

The API supports passing client registry as a field on `__baml_options__` in the request body.

Example request body:

```json
{
    "resume": "Vaibhav Gupta",
    "__baml_options__": {
        "client_registry": {
            "clients": [
                {
                    "name": "OpenAI",
                    "provider": "openai",
                    "retry_policy": null,
                    "options": {
                        "model": "gpt-4o-mini",
                        "api_key": "sk-..."
                    }
                },
                {
                    "name": "OpenAIResponses",
                    "provider": "openai-responses",
                    "retry_policy": null,
                    "options": {
                        "model": "gpt-4.1",
                        "api_key": "sk-..."
                    }
                }
            ],
            "primary": "OpenAI"
        }
    }
}
```

```sh
curl -X POST http://localhost:2024/call/ExtractResume \
    -H 'Content-Type: application/json' -d @body.json
```

</Tab>

</Tabs>

## ClientRegistry Interface

<Tip>
    Note: `ClientRegistry` is imported from `baml_py` in Python and `@boundaryml/baml` in TypeScript, not `baml_client`.

    As we mature `ClientRegistry`, we will add a more type-safe and ergonomic interface directly in `baml_client`. See [Github issue #766](https://github.com/BoundaryML/baml/issues/766).
</Tip>

Methods use `snake_case` in Python and `camelCase` in TypeScript.

### add_llm_client / addLlmClient
A function to add an LLM client to the registry.

<ParamField
    path="name"
    type="string"
    required
>
    The name of the client.

    <Warning>
    Using the exact same name as a client also defined in .baml files overwrites the existing client whenever the ClientRegistry is used.
    </Warning>
</ParamField>

<ParamField path="provider" type="string" required>
This configures which provider to use. The provider is responsible for handling the actual API calls to the LLM service. The provider is a required field.

The configuration modifies the URL request BAML runtime makes.

| Provider Name    | Docs                                                         | Notes                                                      |
| ---------------- | ------------------------------------------------------------ | ---------------------------------------------------------- |
| `anthropic`      | [Anthropic](/ref/llm-client-providers/anthropic)             | Supports [/v1/messages](https://docs.anthropic.com/en/api/messages) endpoint                       |
| `aws-bedrock`    | [AWS Bedrock](/ref/llm-client-providers/aws-bedrock)         | Supports [Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) and [ConverseStream](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) endpoint |
| `google-ai`      | [Google AI](/ref/llm-client-providers/google-ai-gemini)      | Supports Google AI's [generateContent](https://ai.google.dev/api/generate-content) and [streamGenerateContent](https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent) endpoints |
| `vertex-ai`      | [Vertex AI](/ref/llm-client-providers/google-vertex)         | Supports Vertex's [generateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent) and [streamGenerateContent](https://cloud.google.com/vertex-ai/docs/reference/rest/v1/projects.locations.publishers.models/streamGenerateContent) endpoints |
| `openai`         | [OpenAI](/ref/llm-client-providers/open-ai)                  | Supports [/chat/completions](https://platform.openai.com/docs/api-reference/chat) endpoint                  |
| `openai-responses` | [OpenAI Responses API](/ref/llm-client-providers/open-ai-responses-api) | Supports OpenAI's most advanced [/responses](https://platform.openai.com/docs/api-reference/responses) endpoint |
| `azure-openai`   | [Azure OpenAI](/ref/llm-client-providers/open-ai-from-azure) | Supports Azure's [/chat/completions](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions) endpoint                  |
| `openai-generic` | [OpenAI (generic)](/ref/llm-client-providers/openai-generic) | Any other provider that supports OpenAI's `/chat/completions` endpoint |


A non-exhaustive list of providers you can use with `openai-generic`:

| Inference Provider | Docs |
| -------------- | -------------- |
| Azure AI Foundary | [Azure AI Foundary](/ref/llm-client-providers/azure-ai-foundary) |
| Groq | [Groq](/ref/llm-client-providers/groq) |
| Hugging Face | [Hugging Face](/ref/llm-client-providers/huggingface) |
| Keywords AI | [Keywords AI](/ref/llm-client-providers/keywordsai) |
| Litellm | [Litellm](/ref/llm-client-providers/litellm) |
| LM Studio | [LM Studio](/ref/llm-client-providers/lmstudio) |
| Ollama | [Ollama](/ref/llm-client-providers/ollama) |
| OpenRouter | [OpenRouter](/ref/llm-client-providers/openrouter) |
| TogetherAI | [TogetherAI](/ref/llm-client-providers/together) |
| Unify AI | [Unify AI](/ref/llm-client-providers/unify) |
| vLLM | [vLLM](/ref/llm-client-providers/vllm) |


We also have some special providers that allow composing clients together:
| Provider Name  | Docs                             | Notes                                                      |
| -------------- | -------------------------------- | ---------------------------------------------------------- |
| `fallback`     | [Fallback](/ref/llm-client-strategies/fallback)             | Used to chain models conditional on failures               |
| `round-robin`  | [Round Robin](/ref/llm-client-strategies/round-robin)       | Used to load balance                                       |

</ParamField>

<ParamField path="options" type="dict[str, Any]" required>
These vary per provider. Please see provider specific documentation for more
information. Generally they are pass through options to the POST request made
to the LLM.
</ParamField>



<ParamField path="retry_policy" type="string">
The name of a retry policy that is already defined in a .baml file. See [Retry Policies](/ref/llm-client-strategies/retry-policy).
</ParamField>

### set_primary / setPrimary
This sets the client for the function to use. (i.e. replaces the `client` property in a function)

<ParamField
    path="name"
    type="string"
    required
>
    The name of the client to use.

    This can be a new client that was added with `add_llm_client` or an existing client that is already in a .baml file.
</ParamField>
