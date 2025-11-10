---
title: config (logging / environment variables)
---

Various settings are configurable via environment variables.

| Setting | Environment Variable | Description | Default |
| ------- | -------------------- | ----------- | ------- |
| Logging Level | `BAML_LOG` | The logging level to use (`INFO`, `DEBUG`, `TRACE`, `WARN`, `ERROR`, `OFF`) | `INFO` |
| Text / JSON Mode | `BAML_LOG_JSON` | Whether to log in JSON format or human-readable format (`1`, `0`) | `0` |
| Max Log Chunk Size | `BAML_LOG_MAX_MESSAGE_LENGTH` | How large of a prompt / response will be logged (`0` for no limit) | `64000` |
| Log Color Mode | `BAML_LOG_COLOR_MODE` | Whether to color the log output (`auto`, `always`, `never`) | `auto` |

Setting can also be modified via functions in `baml_client.config`.


<Tabs>
  <Tab title="python" language="python">
  ```python
  from baml_client.config import set_from_env, set_log_level, 
                                 set_log_json_mode, set_log_max_message_length,
                                 get_log_level, reset_baml_env_vars
  ```

  ### set_log_level

  Environment variable: `BAML_LOG`

  ```python
  def set_log_level(level: "INFO" | "DEBUG" | "TRACE" | "WARN" | "ERROR" | "OFF"):
    ...
  ```
  
  ### set_log_json_mode

  Environment variable: `BAML_LOG_JSON`

  Switches the log output between JSON and human-readable format.

  ```python
  def set_log_json_mode(enable: bool):
  ```

  ### set_log_max_message_length

  `0` for unlimited

  Environment variable: `BAML_LOG_MAX_MESSAGE_LENGTH`

  ```python
  def set_log_max_message_length(length: int):
  ```

  ### get_log_level

  ```python
  def get_log_level() -> "INFO" | "DEBUG" | "TRACE" | "WARN" | "ERROR" | "OFF":
  ```

  ### reset_baml_env_vars
  <Warning>
  `reset_baml_env_vars` is deprecated and is safe to remove, since environment variables are now lazily loaded on each function call
  </Warning>

  Resets the environment variables to the values in the provided dictionary.
  Will also reset any logging related environment variables to those passed in (if set explicitly).

  ```python
  def reset_baml_env_vars(env: Dict[str, str]):
  ```
  </Tab>

  <Tab title="typescript" language="typescript">
  ```typescript
  import { setLogLevel, setLogJsonMode, 
           setLogMaxMessageLength, getLogLevel,
           resetBamlEnvVars } from '@/baml_client/config';
  ```

  ### setLogLevel
  Environment variable: `BAML_LOG`

  ```typescript
  setLogLevel(level: "INFO" | "DEBUG" | "TRACE" | "WARN" | "ERROR" | "OFF"): void;
  ```

  ### setLogJsonMode
  Environment variable: `BAML_LOG_JSON`

  Switches the log output between JSON and human-readable format.

  ```typescript
  setLogJsonMode(enable: boolean): void;
  ``` 

  ### setLogMaxMessageLength
  Environment variable: `BAML_LOG_MAX_MESSAGE_LENGTH`

  `0` for unlimited
  ```typescript
  setLogMaxMessageLength(length: number): void;
  ```

  ### getLogLevel

  ```typescript
  getLogLevel(): "INFO" | "DEBUG" | "TRACE" | "WARN" | "ERROR" | "OFF";
  ```

  ### resetBamlEnvVars

  Resets the environment variables to the values in the provided dictionary.
  Will also reset any logging related environment variables to those passed in (if set explicitly).

  ```typescript
  resetBamlEnvVars(env: Record<string, string | undefined>): void;
  ```  
  
  </Tab>
  <Tab title="ruby" language="ruby">
```ruby
# not implemented yet
# please use environment variables instead
```
  </Tab>
</Tabs>

<hr />
## Setting Environment Variables

### In the VSCode Playground

Once you open a `.baml` file in VSCode, you should see a small button over every BAML function: `Open Playground`. Then you should be able to set environment variables in the settings tab.

<img src="file:e1bf2438-a5df-40a8-a624-4155fc921360" alt="VSCode Code Lens" />

Or type `BAML Playground` in the VSCode Command Bar (`CMD + Shift + P` or `CTRL + Shift + P`) to open the playground.

### For Boundary Studio Integration

To send logs and traces to Boundary Studio, you need to set the `BOUNDARY_API_KEY` environment variable. This key is provided when you create an API key in your Boundary Studio dashboard.

<Tabs>
  <Tab title="Next.js" language="typescript">
    ```bash
    # .env.local
    BOUNDARY_API_KEY=your_api_key_here
    ```
  </Tab>
  <Tab title="Express.js" language="typescript">
    ```bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ```
  </Tab>
  <Tab title="Flask" language="python">
    ```bash
    # .env
    BOUNDARY_API_KEY=your_api_key_here
    ```
  </Tab>
  <Tab title="Rails" language="ruby">
    ```yaml
    # config/application.yml
    BOUNDARY_API_KEY: your_api_key_here
    ```
  </Tab>
</Tabs>

### For Your App (Default)

BAML will do its best to load environment variables from your program. Any of the following strategies for setting env vars are compatible with BAML:

- Setting them in your shell before running your program
- In your `Dockerfile`
- In your `next.config.js`
- In your Kubernetes manifest
- From `secrets-store.csi.k8s.io`
- From a secrets provider such as [Infisical](https://infisical.com/) / [Doppler](https://www.doppler.com/)
- From a `.env` file (using `dotenv` CLI)
- Using account credentials for ephemeral token generation (e.g., Vertex AI Auth Tokens)
- `python-dotenv` package in Python or `dotenv` package in Node.js

```bash
export MY_SUPER_SECRET_API_KEY="..."
python my_program_using_baml.py
```

<Tabs>
  <Tab title="python" language="python">

    ```python
    from dotenv import load_dotenv
    from baml_client import b

    load_dotenv()
    ```
  </Tab>
  <Tab title="typescript" language="typescript">

    ```typescript
    import dotenv from 'dotenv'
    import { b } from './baml_client'

    dotenv.config()
    ```
  </Tab>
  <Tab title="ruby" language="ruby">
    ```ruby
    require 'dotenv/load'
    require 'baml_client'
    ```
  </Tab>
</Tabs>

