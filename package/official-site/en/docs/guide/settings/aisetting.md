# AI / LLM Settings

::: tip Desktop users
This page configures model connections for chat and image understanding. Desktop AI is included in the application; models are downloaded as needed. See [built-in desktop AI](/en/docs/guide/desktop-ai-extension).
:::

## Built-in Connection

TrailSnap includes a built-in AI connection that works out of the box. It uses the MiniCPM-V-4_6-Q4_K_M multimodal model, supporting image content understanding, tag generation, and other visual tasks.

The built-in connection is shown on the **Settings → LLMs and captions (大模型与文案) → LLM connections and tasks** page with a "Built-in" badge. **The built-in connection cannot be deleted; its address and key are managed by the application.**

If you need to use a third-party API, you can add a new connection.

## Adding a Connection

Go to **Settings → LLMs and captions (大模型与文案) → LLM connections and tasks** to add a new LLM connection.

1. Select **Add connection**, choose the OpenAI-compatible API type, and enter its Base URL and API key. Use the OpenAI-compatible endpoint for services such as Ollama.
2. Fetch the model list and add selected models, or add models manually. Each connection must have at least one model.
3. Save the connection, choose default models for chat and analysis, and save the LLM configuration.

Advanced prompts and scheduled captions are on the same page. Scheduling requires administrator access. Face and OCR service addresses and recognition models are under **Settings → Local recognition models (本地识别模型)**.

## AI Chat Configuration

Go to **Settings → LLMs and captions (大模型与文案) → AI chat defaults** to configure the default model used by the AI assistant.

## Smart Analysis Configuration

Go to **Settings → LLMs and captions (大模型与文案) → Smart analysis** to select the connection and model for image content understanding and tag generation. This is a relatively simple task, so a small model is sufficient.

Due to privacy concerns, be cautious when using cloud models from various platforms. Using a locally deployed model is recommended, such as Ollama with `qwen3.5:4b`, or a local LLM service like `vllm`.

```bash
ollama run qwen3.5:4b
```

- Base URL: The API base URL for the vision model, e.g. `http://127.0.0.1:11434/v1`
- API Key: The API key for the vision model. For local Ollama, you can use: `empty`
- Model Name: The vision model name, e.g. `qwen3.5:4b`

### Creating a Processing Task

After configuration, go to **Settings → Background tasks (后台任务) → Smart analysis**, select `Force Redo` or `Run Missing Tasks` to start analyzing photos (to save resources, screenshots are automatically skipped during analysis).

### Viewing Analysis Results

1. Go to **Toolbox → Quality Cleanup** — this shows all AI-analyzed photos sorted by score.
2. Click a photo to open the detail panel, then click the top-right button and select "View AI Analysis Results".
3. On the home page, the "On This Day" module shows photos from past years (if available), sorted by score with AI-generated captions.
