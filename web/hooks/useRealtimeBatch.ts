/**
 * React hook for real-time batch job subscriptions using Supabase Realtime.
 * 
 * Phase 3.5: Adds Realtime subscriptions alongside existing SSE.
 * This hook provides WebSocket-based updates for batch job status and progress.
 */

import { useEffect, useState, useRef } from 'react'
import { supabase } from '@/lib/supabase'
import type { Database } from '@/types/database'
import { RealtimeChannel } from '@supabase/supabase-js'

type BatchJob = Database['public']['Tables']['batch_jobs']['Row']

export interface UseRealtimeBatchResult {
  /** Current batch job data from Realtime subscription */
  batch: BatchJob | null
  /** WebSocket connection status */
  isConnected: boolean
  /** Error from subscription or fetching */
  error: Error | null
  /** Latency of last update (for performance comparison) */
  latency: number | null
}

/**
 * Subscribe to real-time updates for a specific batch job.
 * 
 * Features:
 * - Fetches initial batch state from database
 * - Subscribes to postgres_changes events filtered by batch_job_id
 * - Tracks connection status and latency
 * - Automatic cleanup on unmount
 * 
 * @param batchId - Batch job ID to subscribe to (null to skip subscription)
 * @returns Batch data, connection status, error, and latency metrics
 * 
 * @example
 * ```tsx
 * const { batch, isConnected, latency } = useRealtimeBatch(batchId)
 * 
 * console.log('[REALTIME]', {
 *   status: batch?.status,
 *   progress: batch?.overall_progress_pct,
 *   completed: batch?.documents_completed,
 *   total: batch?.total_documents,
 *   latency,
 *   connected: isConnected
 * })
 * ```
 */
export function useRealtimeBatch(batchId: string | null): UseRealtimeBatchResult {
  const [batch, setBatch] = useState<BatchJob | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [latency, setLatency] = useState<number | null>(null)
  
  const channelRef = useRef<RealtimeChannel | null>(null)
  const updateTimestampRef = useRef<number | null>(null)

  useEffect(() => {
    if (!batchId) {
      setBatch(null)
      setIsConnected(false)
      setError(null)
      setLatency(null)
      return
    }

    // Fetch initial batch state from database
    const fetchInitialBatch = async () => {
      try {
        const { data, error: fetchError } = await supabase
          .from('batch_jobs')
          .select('*')
          .eq('batch_job_id', batchId)
          .single()

        if (fetchError) throw fetchError
        setBatch(data)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to fetch initial batch'))
      }
    }

    fetchInitialBatch()

    // Subscribe to real-time updates
    const channel = supabase
      .channel(`batch:${batchId}`)
      .on(
        'postgres_changes',
        {
          event: '*', // Listen to INSERT, UPDATE, DELETE
          schema: 'public',
          table: 'batch_jobs',
          filter: `batch_job_id=eq.${batchId}`
        },
        (payload) => {
          // Track when we received this update
          updateTimestampRef.current = Date.now()
          
          const newBatch = payload.new as BatchJob
          setBatch(newBatch)
          
          // Calculate latency (rough estimate)
          // In production, backend should include server timestamp in payload
          const now = Date.now()
          if (updateTimestampRef.current) {
            setLatency(now - updateTimestampRef.current)
          }

          console.log('[PHASE 3.5] Realtime batch update received:', {
            batchId,
            event: payload.eventType,
            status: newBatch.status,
            overall_progress_pct: newBatch.overall_progress_pct,
            documents_completed: newBatch.documents_completed,
            total_documents: newBatch.total_documents,
            latency: latency ? `${latency}ms` : 'N/A'
          })
        }
      )
      .subscribe((status) => {
        console.log('[PHASE 3.5] Realtime batch subscription status:', status)
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
  }, [batchId])

  return { batch, isConnected, error, latency }
}
