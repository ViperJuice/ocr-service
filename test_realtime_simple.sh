#!/bin/bash

# Phase 3.5: Simple Realtime Test
# Directly update database via Supabase REST API

SUPABASE_URL="http://127.0.0.1:54321"
SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"

JOB_ID=$(uuidgen)
FILE_ID=$(uuidgen)
USER_ID="a0000000-0000-0000-0000-000000000001"

echo "======================================================================"
echo "Phase 3.5: Realtime Subscription Test"
echo "======================================================================"

echo ""
echo "[1/4] Creating test job in database..."
echo "Job ID: $JOB_ID"

# Insert job into database
curl -s -X POST "$SUPABASE_URL/rest/v1/jobs" \
  -H "apikey: $SERVICE_KEY" \
  -H "Authorization: Bearer $SERVICE_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"job_id\": \"$JOB_ID\",
    \"user_id\": \"$USER_ID\",
    \"file_id\": \"$FILE_ID\",
    \"filename\": \"realtime_test.pdf\",
    \"model\": \"deepseek-ocr\",
    \"status\": \"queued\",
    \"progress_pct\": 0.0,
    \"pages_completed\": 0,
    \"total_pages\": 10,
    \"processing_options\": {}
  }" > /dev/null

echo "✅ Job created"

echo ""
echo "[2/4] Instructions:"
echo "🌐 Open: http://localhost:3000"
echo "📋 Use the job monitoring UI with Job ID: $JOB_ID"
echo "🔍 Open browser console (F12)"
echo ""
echo "Press ENTER when ready to send Realtime updates..."
read

echo ""
echo "[3/4] Sending progress updates (watch browser console)..."

# Update progress in steps
for pct in 25 50 75 100; do
  pages=$((pct / 10))
  status="processing"
  if [ "$pct" -eq 100 ]; then
    status="completed"
  fi
  
  echo "  → Updating: ${pct}% ($pages pages, status=$status)"
  
  curl -s -X PATCH "$SUPABASE_URL/rest/v1/jobs?job_id=eq.$JOB_ID" \
    -H "apikey: $SERVICE_KEY" \
    -H "Authorization: Bearer $SERVICE_KEY" \
    -H "Content-Type: application/json" \
    -H "Prefer: return=minimal" \
    -d "{
      \"status\": \"$status\",
      \"progress_pct\": $pct.0,
      \"pages_completed\": $pages
    }" > /dev/null
  
  sleep 2
done

echo ""
echo "======================================================================"
echo "✅ Test Complete!"
echo "======================================================================"
echo ""
echo "Check browser console for [PHASE 3.5] logs:"
echo "  • Realtime subscription status: SUBSCRIBED"
echo "  • Realtime update received (with latency)"
echo "  • Dual-Subscription Comparison (if SSE also running)"
echo "======================================================================"
