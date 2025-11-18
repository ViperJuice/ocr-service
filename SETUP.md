# OCR Service - Development Setup Guide

Complete guide for setting up the OCR service on a new development machine (laptop, remote workstation, etc).

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Clone Repository](#clone-repository)
3. [Database Setup (Supabase)](#database-setup-supabase)
4. [Docker Containers (OCR Models)](#docker-containers-ocr-models)
5. [Python Environment](#python-environment)
6. [Frontend Setup](#frontend-setup)
7. [Configuration](#configuration)
8. [Running the Service](#running-the-service)
9. [Verification](#verification)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software
- **Python 3.11+** (tested with 3.11)
- **UV** (Python package manager) - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker & Docker Compose** (for OCR model containers)
- **Node.js 18+** and **npm** (for frontend)
- **Git**
- **PostgreSQL client** (optional, for debugging database)

### Hardware Requirements
- **GPU**: NVIDIA GPU with 16GB+ VRAM recommended (for DeepSeek-OCR + Qwen3-VL)
  - DeepSeek-OCR: ~8GB VRAM
  - Qwen3-VL: ~8GB VRAM
- **RAM**: 16GB+ system RAM
- **Storage**: 20GB+ free disk space (models are large)

### NVIDIA GPU Setup (Linux)
```bash
# Install NVIDIA drivers
sudo ubuntu-drivers autoinstall

# Install NVIDIA Container Toolkit (for Docker GPU access)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify GPU access
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

---

## Clone Repository

```bash
cd ~/code  # or your preferred projects directory
git clone https://github.com/YOUR_USERNAME/ocr-service.git
cd ocr-service
```

---

## Database Setup (Supabase)

The service uses **Supabase** (PostgreSQL + Realtime + Auth). You have two options:

### Option A: Supabase Cloud (Recommended for Laptop)
1. **Create Project**: Go to [supabase.com](https://supabase.com) → Create new project
2. **Copy Credentials**: From project settings → API → Copy:
   - Project URL (e.g., `https://xyz.supabase.co`)
   - `anon` public key
   - `service_role` secret key (for backend)
3. **Run Migrations**: Apply database schema
   ```bash
   # Install Supabase CLI
   npm install -g supabase

   # Link project (replace with your project ref)
   supabase link --project-ref your-project-ref

   # Push migrations
   supabase db push
   ```

4. **Verify Tables**: Check that these tables exist in your Supabase dashboard:
   - `jobs` - Job tracking
   - `page_results` - Per-page OCR/merge results
   - `job_events` - Audit trail
   - `streams` - Phase 4 streaming tokens (single mutable row)

### Option B: Local Supabase (Docker)
```bash
# Install Supabase CLI
npm install -g supabase

# Start local Supabase (PostgreSQL + Auth + Realtime)
supabase start

# Apply migrations
supabase db push

# Get local credentials (displayed after 'supabase start')
# API URL: http://localhost:54321
# anon key: eyJhbGc...
# service_role key: eyJhbGc...
```

**Note**: Local Supabase uses ports:
- PostgreSQL: `54322`
- API: `54321`
- Studio (dashboard): `54323`

### Database Schema Reference
Key tables and their purpose:
- **`jobs`**: Job metadata (status, progress, model, file_id, etc.)
- **`page_results`**: OCR and merge text per page (upserted during processing)
- **`job_events`**: Audit trail (job_created, ocr_page_completed, merge_page_completed)
- **`streams`**: Phase 4 streaming architecture (single row per job+page with snapshot updates)

---

## Docker Containers (OCR Models)

The service uses two Docker containers for OCR models:
- **DeepSeek-OCR**: Port 8001 (OCR extraction)
- **Qwen3-VL**: Port 8002 (OCR merging/refinement)

### Build Containers
```bash
# DeepSeek-OCR container
cd docker/deepseek-ocr
docker build -t deepseek-ocr .

# Qwen3-VL container
cd ../qwen-vl
docker build -t qwen-vl .
```

**Build time**: 10-20 minutes (downloads ~10GB models)

### Start Containers
```bash
# Start both containers (GPU required)
docker start deepseek-ocr qwen-vl

# OR start individually
docker run -d --name deepseek-ocr --gpus all -p 8001:8001 deepseek-ocr
docker run -d --name qwen-vl --gpus all -p 8002:8002 qwen-vl
```

### Verify Containers
```bash
# Check container status
docker ps | grep -E "deepseek-ocr|qwen-vl"

# Check GPU allocation
docker exec deepseek-ocr nvidia-smi
docker exec qwen-vl nvidia-smi

# Test DeepSeek-OCR health
curl http://localhost:8001/health

# Test Qwen3-VL health
curl http://localhost:8002/health
```

**Expected output**: Both should return `{"status": "ok"}`

---

## Python Environment

### Install UV (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env  # Add UV to PATH
```

### Setup Python Environment
```bash
cd ocr-service

# Create virtual environment with Python 3.11
uv venv --python 3.11

# Activate environment
source .venv/bin/activate

# Install dependencies (from pyproject.toml)
uv sync

# Verify installation
uv pip list | grep -E "fastapi|supabase|pytorch"
```

### Install BAML (Optional - for NLP command parsing)
```bash
# BAML is already included in dependencies
# Verify it's installed
uv pip show baml-py
```

---

## Frontend Setup

The web UI is a Next.js 15 app with BAML integration.

```bash
cd web

# Install dependencies
npm install

# Install Tailwind CSS (if needed)
npx tailwindcss init -p

# Generate BAML types (TypeScript)
npx @boundaryml/baml generate

# Verify BAML client
ls -la baml_client/  # Should contain generated TypeScript types
```

---

## Configuration

### Environment Variables

Create `.env` in project root:
```bash
# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co  # or http://localhost:54321 for local
SUPABASE_KEY=your-service-role-key-here
SUPABASE_ANON_KEY=your-anon-key-here

# OCR Model Containers
DEEPSEEK_URL=http://localhost:8001/v1
QWEN_URL=http://localhost:8002/v1

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# File Storage
INPUT_DIR=./data/input
OUTPUT_DIR=./data/output
UPLOAD_DIR=./data/uploads

# Processing Defaults
DEFAULT_MODEL=deepseek-ocr  # or qwen3-vl
DEFAULT_PROMPT_TYPE=markdown
DEFAULT_PAGE_BATCH_SIZE=8  # Pages per GPU batch
```

### Frontend Environment

Create `web/.env.local`:
```bash
# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000

# Supabase (Frontend - uses anon key)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

### Create Data Directories
```bash
mkdir -p data/input data/output data/uploads
```

### Test PDFs (Optional)
Place test PDFs in `data/input/`:
```bash
# Example: DeepSeek_OCR_paper.pdf (22 pages)
# Download from: [DeepSeek OCR paper URL]
```

---

## Running the Service

### Backend API
```bash
# From project root
source .venv/bin/activate

# Start FastAPI server
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --log-level info

# OR with auto-reload (development)
uv run uvicorn src.api.main:app --reload --port 8000
```

**Server starts at**: `http://localhost:8000`

### Frontend (Next.js)
```bash
cd web

# Development mode (with hot reload)
npm run dev

# Production build + start
npm run build
npm start
```

**Frontend starts at**: `http://localhost:3000`

---

## Verification

### 1. Check Backend Health
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "database": "connected", "models": {...}}
```

### 2. Upload Test PDF
```bash
PDF_PATH="data/input/DeepSeek_OCR_paper.pdf"

# Upload file
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/process/upload" \
  -F "file=@$PDF_PATH")

echo $RESPONSE
# Expected: {"file_id": "uuid-here", "filename": "DeepSeek_OCR_paper.pdf"}
```

### 3. Submit OCR Job
```bash
FILE_ID="your-file-id-from-step-2"

# Submit job
JOB_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/process/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"file_id\": \"$FILE_ID\", \"use_merge_streaming\": true}")

echo $JOB_RESPONSE
# Expected: {"job_id": "uuid-here", "status": "queued"}
```

### 4. Monitor Job Progress
```bash
JOB_ID="your-job-id-from-step-3"

# Poll job status
while true; do
  curl -s "http://localhost:8000/api/v1/process/jobs/$JOB_ID" | \
    python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Status: {d[\"status\"]} | Progress: {d[\"progress_pct\"]}% | Pages: {d[\"pages_completed\"]}/{d[\"total_pages\"]} | Stage: {d[\"current_stage\"]}')"
  sleep 3
done
```

### 5. Test Frontend
1. Open `http://localhost:3000` in browser
2. Upload a PDF
3. Submit job
4. Watch real-time streaming progress (via Supabase Realtime)

---

## Troubleshooting

### GPU Issues
**Problem**: `RuntimeError: CUDA out of memory`

**Solutions**:
- Reduce `DEFAULT_PAGE_BATCH_SIZE` in `.env` (try 4 or 2)
- Stop one model container to free VRAM
- Use smaller model (Qwen3-VL uses less VRAM than DeepSeek-OCR)

### Database Connection Failed
**Problem**: `supabase.exceptions.APIError: Connection refused`

**Solutions**:
- Check Supabase URL in `.env` (must include `https://`)
- Verify service_role key is correct (not anon key)
- For local Supabase: Ensure `supabase start` is running

### Port Already in Use
**Problem**: `Address already in use: 0.0.0.0:8000`

**Solutions**:
```bash
# Find process using port 8000
lsof -ti:8000

# Kill process
lsof -ti:8000 | xargs kill -9

# OR use different port
uv run uvicorn src.api.main:app --port 8001
```

### Docker Containers Not Starting
**Problem**: Containers exit immediately after `docker start`

**Solutions**:
```bash
# Check container logs
docker logs deepseek-ocr
docker logs qwen-vl

# Common issues:
# - GPU not detected: Verify nvidia-container-toolkit installed
# - Model download failed: Re-run docker build
# - Port conflict: Check if 8001/8002 are free
```

### BAML Import Errors
**Problem**: `ModuleNotFoundError: No module named 'baml_client'`

**Solutions**:
```bash
# Regenerate BAML types
cd web
npx @boundaryml/baml generate

# Verify generated files exist
ls -la baml_client/
```

### Slow OCR Processing
**Problem**: Pages take >10 seconds each

**Solutions**:
- Check GPU utilization: `nvidia-smi`
- Increase batch size: `DEFAULT_PAGE_BATCH_SIZE=16` (if VRAM allows)
- Use DeepSeek-OCR only (faster than Qwen3-VL merge)
- Check CPU bottleneck: `htop`

---

## Development Workflow

### Typical Development Session
```bash
# 1. Start database (if local)
supabase start

# 2. Start Docker containers
docker start deepseek-ocr qwen-vl

# 3. Start backend API
source .venv/bin/activate
uv run uvicorn src.api.main:app --reload

# 4. Start frontend (new terminal)
cd web && npm run dev

# 5. Code changes...
# - Backend: Auto-reloads via uvicorn --reload
# - Frontend: Hot reload via Next.js
# - Database: Apply migrations with `supabase db push`
```

### Database Migrations
When adding new tables/columns:
```bash
# Create migration file
supabase migration new your_migration_name

# Edit: supabase/migrations/YYYYMMDD_your_migration_name.sql

# Apply migration
supabase db push
```

### Running Tests
```bash
# Backend tests
uv run pytest tests/ -v

# Frontend tests
cd web && npm test
```

---

## Production Deployment

### Backend (FastAPI)
```bash
# Use production ASGI server (Gunicorn + Uvicorn workers)
gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Frontend (Next.js)
```bash
cd web
npm run build
npm start  # Runs production server on port 3000
```

### Environment Variables (Production)
- Use **Supabase Cloud** (not local)
- Set `API_HOST=0.0.0.0` and `API_PORT=80` (or behind reverse proxy)
- Use strong `SUPABASE_KEY` (rotate regularly)
- Enable HTTPS (nginx, Caddy, or Cloudflare)

---

## Additional Resources

- **Supabase Docs**: https://supabase.com/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Next.js Docs**: https://nextjs.org/docs
- **BAML Docs**: https://docs.boundaryml.com
- **UV Docs**: https://docs.astral.sh/uv

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│  - File upload UI                                            │
│  - Real-time job progress (Supabase Realtime)               │
│  - BAML command parsing                                      │
│  - Result viewer                                             │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP (port 3000)
┌──────────────────▼──────────────────────────────────────────┐
│                   Backend API (FastAPI)                      │
│  - Job orchestration                                         │
│  - Database operations (Supabase)                            │
│  - SSE streaming (phase 4)                                   │
│  - File management                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┬───────────────┐
        │                     │               │
┌───────▼────────┐   ┌────────▼──────┐  ┌────▼─────────────┐
│  DeepSeek-OCR  │   │   Qwen3-VL    │  │  Supabase Cloud  │
│  (Docker)      │   │   (Docker)    │  │  - PostgreSQL    │
│  Port 8001     │   │   Port 8002   │  │  - Realtime      │
│  GPU: 8GB VRAM │   │   GPU: 8GB    │  │  - Auth          │
└────────────────┘   └───────────────┘  └──────────────────┘
```

### Processing Pipeline
1. **Upload**: User uploads PDF → `/api/v1/process/upload`
2. **Job Creation**: Backend creates job in database
3. **OCR Stage** (0-60% progress):
   - Pages batched (batch_size=8)
   - Sent to DeepSeek-OCR container
   - OCR text saved to `page_results` table
4. **Merge Stage** (60-100% progress):
   - OCR text sent to Qwen3-VL for refinement
   - Merge text saved to `page_results` table
5. **Streaming** (Phase 4):
   - Tokens streamed to `streams` table (single mutable row)
   - Frontend subscribes via Supabase Realtime
6. **Completion**: Final result assembled and saved

---

## Quick Start Checklist

- [ ] Install prerequisites (Python, UV, Docker, Node.js)
- [ ] Clone repository
- [ ] Setup Supabase (cloud or local)
- [ ] Run database migrations
- [ ] Build Docker containers (DeepSeek-OCR, Qwen3-VL)
- [ ] Create `.env` file with credentials
- [ ] Install Python dependencies (`uv sync`)
- [ ] Install frontend dependencies (`npm install`)
- [ ] Start Docker containers
- [ ] Start backend API
- [ ] Start frontend dev server
- [ ] Upload test PDF and verify processing

---

**Last Updated**: 2025-01-17 (Phase 4 complete)
