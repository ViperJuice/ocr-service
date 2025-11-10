# OCR Service - Web Interface

A modern, dark-themed web interface for the OCR Service API with real-time chat-based interaction powered by BAML (Boundary ML) for intelligent prompt management.

## Features

- 🎨 **Dark Theme UI** - Beautiful Obsidian/BetterStack-inspired dark theme
- 💬 **Chat Interface** - Natural language commands for document processing
- 🤖 **BAML Orchestration** - AI-powered intent classification and tool calling with o4-mini reasoning
- 🔄 **Streaming Refactoring** - Real-time prompt optimization for complex formatting requests
- 📄 **Multi-Format Display** - View results as Markdown, JSON, or plain text
- 📊 **Real-Time Progress** - SSE-powered live progress monitoring
- 🎯 **Cross-Page Formatting** - "Format pages 8-20 like page 3" with intelligent refactoring
- 🔁 **Fallback Strategies** - Multi-model fallback with retry policies for reliability
- 📥 **Export Options** - Download results locally or save to Google Drive

## Tech Stack

- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript
- **Styling**: TailwindCSS
- **Prompting**: BAML (Boundary ML)
- **State**: Zustand + TanStack Query
- **Components**: Custom + Radix UI primitives
- **Chat**: React-based with command parsing
- **Code Display**: Monaco Editor

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- OCR Service backend running on port 8000

### Installation

1. **Install dependencies**:

```bash
cd web
npm install
```

2. **Configure environment**:

```bash
# Copy the example env file
cp .env.local.example .env.local

# Edit .env.local and set your API URL (default: http://localhost:8000)
```

3. **Generate BAML client** (if you modify prompts):

```bash
npm run baml:generate
```

### Development

1. **Start the backend**:

```bash
# In the project root
cd /home/jenner/code/ocr-service
source .venv/bin/activate
./scripts/start_api.sh
```

2. **Start the frontend** (in a new terminal):

```bash
cd /home/jenner/code/ocr-service/web
npm run dev
```

3. **Open your browser**:

```
http://localhost:3000
```

## Usage

### Basic Workflow

1. **Upload a file**: Drag and drop a PDF or image into the drop zone
2. **Give commands**: Type natural language commands in the chat:
   - "Parse the whole document"
   - "Parse page 5"
   - "Parse pages 10-20"
   - "Show as JSON"
3. **Watch progress**: Real-time progress updates appear automatically
4. **View results**: Results display in the right panel with formatting
5. **Export**: Download or save results

### Chat Commands

The chat interface supports natural language commands:

| Command | Action |
|---------|--------|
| "Parse the whole document" | Process all pages |
| "Parse page 5" | Process only page 5 |
| "Parse pages 1-10" | Process pages 1 through 10 |
| "Parse front matter on page 1" | Extract metadata from page 1 |
| "Use page 3 as example" | Mark page 3 as reference |
| "Parse pages 5-20 using page 3 style" | Apply page 3's settings to pages 5-20 |
| "Show as markdown/json/text" | Change output format |
| "Download result" | Download the processed document |

### BAML Orchestration

The application uses BAML for intelligent command orchestration with AI-powered tool calling. The system automatically:

1. **Classifies user intent** (START_OCR_JOB, CHECK_STATUS, GET_RESULTS, etc.)
2. **Extracts parameters** from natural language (DPI, format, page ranges)
3. **Refactors complex prompts** with reasoning (e.g., "format pages 8-20 like page 3")
4. **Generates API call sequences** with proper dependencies
5. **Validates parameters** before execution

**Core BAML Functions** (`baml_src/main.baml`):

- `HandleUserMessage`: Main orchestration (returns intent, parameters, tool calls)
- `RefactorUserPromptForOCR`: Prompt refactoring with o4-mini reasoning
- `ClassifyUserIntent`: Fast intent classification with Claude Haiku 4.5
- `ExtractJobParameters`: Parameter extraction from natural language
- `GenerateToolCallSequence`: API call generation
- `ValidateJobParameters`: Parameter validation

**Model Strategy:**
- **Primary**: Claude Haiku 4.5 (fast structured tasks), o4-mini (reasoning)
- **Fallback**: Claude Sonnet 4.5, GPT-4o Mini
- **Retry**: Exponential backoff with 3-5 retries

### Customizing BAML

1. **Edit prompts**: Modify `baml_src/main.baml`
2. **Regenerate client**:

```bash
npm run baml:generate
```

3. **Restart dev server**: Changes apply immediately

**What you can customize:**
- Retry policies (StandardRetry, AggressiveRetry)
- Client fallback strategies (ReasoningClient, FastStructuredClient)
- Function prompts and role instructions
- Data types and validation rules
- Model selection (o4-mini, Claude models, GPT models)

## Project Structure

```
web/
├── app/
│   ├── layout.tsx         # Root layout with dark theme
│   ├── page.tsx           # Main application page
│   ├── providers.tsx      # Query provider
│   └── globals.css        # Global styles & dark theme
├── components/
│   ├── FileDropZone.tsx   # File upload component
│   ├── ChatMessage.tsx    # Individual chat message
│   ├── MessageList.tsx    # Chat message list
│   ├── ChatInput.tsx      # Chat input field
│   ├── ResultViewer.tsx   # Multi-format result display
│   └── ProgressMonitor.tsx # Real-time progress tracker
├── lib/
│   ├── api-client.ts      # FastAPI client wrapper
│   ├── baml-wrapper.ts    # BAML integration layer
│   ├── types.ts           # TypeScript types
│   ├── utils.ts           # Utility functions
│   ├── command-parser.ts  # Chat command parsing (deprecated, now uses BAML)
│   └── storage.ts         # LocalStorage helpers
├── hooks/
│   └── useOcrJob.ts       # OCR job lifecycle hook
├── baml_src/
│   └── main.baml          # BAML prompt definitions
└── baml_client/           # Generated BAML TypeScript client
```

## Configuration

### Environment Variables

Create a `.env.local` file with the following:

```bash
# Required for BAML orchestration models
OPENAI_API_KEY=sk-...              # For o4-mini and GPT-4o Mini
ANTHROPIC_API_KEY=sk-ant-...       # For Claude Haiku 4.5 and Sonnet 4.5

# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000

# Optional: Google OAuth for Drive export
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

See `.env.example` for a template.

### Tailwind Theme

Dark theme colors are defined in `tailwind.config.ts`:

- Background: `#0D0D0D`, `#1A1A1A`
- Surface: `#2D2D2D`
- Primary: `#8B5CF6` (purple)
- Accent: `#6366F1` (blue)
- Text: `#F5F5F5`, `#E5E5E5`

## API Integration

The frontend communicates with the FastAPI backend via:

- **REST API**: File upload, job submission, result retrieval
- **SSE (Server-Sent Events)**: Real-time progress updates
- **CORS**: Pre-configured for `localhost:3000`

## Troubleshooting

### Backend not responding

- Ensure the backend is running on port 8000
- Check `NEXT_PUBLIC_API_URL` in `.env.local`
- Verify CORS is enabled in backend settings

### BAML errors

```bash
# Regenerate BAML client
npx @boundaryml/baml generate

# Check baml_src/main.baml for syntax errors
```

### TypeScript errors

```bash
# Clean and rebuild
rm -rf .next
npm run dev
```

## Scripts

```json
{
  "dev": "next dev",                    // Start dev server
  "build": "next build",                 // Build for production
  "start": "next start",                 // Start production server
  "lint": "next lint",                   // Run ESLint
  "baml:generate": "npx @boundaryml/baml generate"  // Generate BAML client
}
```

## Development Tips

1. **Hot Reload**: Both Next.js and BAML support hot reload during development
2. **TypeScript**: Use the generated types from `lib/types.ts` for API responses
3. **BAML Functions**: All BAML functions are available via `bamlPrompts` wrapper
4. **Styling**: Use Tailwind utility classes + custom dark theme classes
5. **Components**: Keep components small and focused for maintainability

## Deployment

### Vercel (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Environment Variables for Production

- Set `NEXT_PUBLIC_API_URL` to your production API URL
- Configure Google OAuth credentials if using Drive export
- Enable analytics/monitoring as needed

## Contributing

1. Follow the existing code style
2. Update BAML prompts for new features
3. Add types to `lib/types.ts`
4. Test with both light and dark themes
5. Ensure accessibility (ARIA labels, keyboard nav)

## License

Same as parent OCR Service project.

## Support

For issues or questions:
- Check the main project README
- Review API documentation at `/docs`
- File an issue in the repository

---

**Built with** ❤️ **using Next.js, TypeScript, and BAML**
