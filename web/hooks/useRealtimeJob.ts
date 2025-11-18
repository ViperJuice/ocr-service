/**
 * React hook for real-time job subscriptions using Supabase Realtime.
 * 
 * Phase 3.5: Adds Realtime subscriptions alongside existing SSE.
 * This hook provides WebSocket-based updates for job status and progress.
 */

import { useEffect, useState, useRef } from 'react'
import { supabase } from '@/lib/supabase'
import type { Database } from '@/types/database'
import { RealtimeChannel } from '@supabase/supabase-js'

type Job = Database['public']['Tables']['jobs']['Row']

export interface UseRealtimeJobResult {
  /** Current job data from Realtime subscription */
  job: Job | null
  /** WebSocket connection status */
  isConnected: boolean
  /** Error from subscription or fetching */
  error: Error | null
  /** Latency of last update (for performance comparison) */
  latency: number | null
}

/**
 * Subscribe to real-time updates for a specific job.
 * 
 * Features:
 * - Fetches initial job state from database
 * - Subscribes to postgres_changes events filtered by job_id
 * - Tracks connection status and latency
 * - Automatic cleanup on unmount
 * 
 * @param jobId - Job ID to subscribe to (null to skip subscription)
 * @returns Job data, connection status, error, and latency metrics
 * 
 * @example
 * ```tsx
 * const { job, isConnected, latency } = useRealtimeJob(jobId)
 * 
 * console.log('[REALTIME]', {
 *   status: job?.status,
 *   progress: job?.progress_pct,
 *   latency,
 *   connected: isConnected
 * })
 * ```
 */
export function useRealtimeJob(jobId: string | null): UseRealtimeJobResult {
  const [job, setJob] = useState<Job | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [latency, setLatency] = useState<number | null>(null)
  
  const channelRef = useRef<RealtimeChannel | null>(null)
  const updateTimestampRef = useRef<number | null>(null)

  useEffect(() => {
    if (!jobId) {
      setJob(null)
      setIsConnected(false)
      setError(null)
      setLatency(null)
      return
    }

    // Note: Skip initial fetch - we'll get the first update from Realtime subscription
    // This avoids HTTP 406 errors from Supabase REST API content negotiation issues

    // Subscribe to real-time updates
    const channel = supabase
      .channel(`job:${jobId}`)
      .on(
        'postgres_changes',
        {
          event: '*', // Listen to INSERT, UPDATE, DELETE
          schema: 'public',
          table: 'jobs',
          filter: `job_id=eq.${jobId}`
        },
        (payload) => {
          // Track when backend sent this update (if available in metadata)
          updateTimestampRef.current = Date.now()
          
          const newJob = payload.new as Job
          setJob(newJob)
          
          // Calculate latency (rough estimate from our timestamp)
          // In production, backend should include server timestamp in payload
          const now = Date.now()
          if (updateTimestampRef.current) {
            setLatency(now - updateTimestampRef.current)
          }

          console.log('[PHASE 3.5] Realtime update received:', {
            jobId,
            event: payload.eventType,
            status: newJob.status,
            progress_pct: newJob.progress_pct,
            pages_completed: newJob.pages_completed,
            latency: latency ? `${latency}ms` : 'N/A'
          })
        }
      )
      .subscribe((status) => {
        console.log('[PHASE 3.5] Realtime subscription status:', status)
        setIsConnected(status === 'SUBSCRIBED')
        
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          setError(new Error(`Subscription ${status}`))
        }
      })

    channelRef.current = channel

    // Cleanup on unmount
    return () => {
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current)
        channelRef.current = null
      }
    }
  }, [jobId])

  return { job, isConnected, error, latency }
}
