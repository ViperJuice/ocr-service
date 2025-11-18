/**
 * React hook for real-time streaming token subscriptions using Supabase Realtime.
 *
 * Phase 4: Database-based token streaming for merge stage.
 * This hook subscribes to streaming_tokens table and accumulates chunks per page.
 */

import { useEffect, useState, useRef } from 'react'
import { supabase } from '@/lib/supabase'
import { RealtimeChannel } from '@supabase/supabase-js'

interface StreamingToken {
  token_id: string
  job_id: string
  page_num: number
  chunk_sequence: number
  chunk_text: string
  created_at: string
}

export interface UseRealtimeStreamingTokensResult {
  /** Accumulated text per page (Map<page_num, text>) */
  pageTexts: Map<number, string>
  /** Total number of tokens received */
  tokenCount: number
  /** WebSocket connection status */
  isConnected: boolean
  /** Error from subscription */
  error: Error | null
}

/**
 * Subscribe to real-time streaming tokens for a specific job.
 *
 * Features:
 * - Subscribes to INSERT events on streaming_tokens table filtered by job_id
 * - Accumulates chunks in sequence order per page
 * - Tracks connection status
 * - Automatic cleanup on unmount
 *
 * @param jobId - Job ID to subscribe to (null to skip subscription)
 * @returns Accumulated page texts, token count, connection status, and error
 *
 * @example
 * ```tsx
 * const { pageTexts, tokenCount, isConnected } = useRealtimeStreamingTokens(jobId)
 *
 * // Display accumulated text for page 1
 * const page1Text = pageTexts.get(1) || ''
 * ```
 */
export function useRealtimeStreamingTokens(jobId: string | null): UseRealtimeStreamingTokensResult {
  const [pageTexts, setPageTexts] = useState<Map<number, string>>(new Map())
  const [tokenCount, setTokenCount] = useState(0)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const channelRef = useRef<RealtimeChannel | null>(null)
  // Store chunks per page for ordered accumulation
  const chunksRef = useRef<Map<number, Map<number, string>>>(new Map())

  useEffect(() => {
    if (!jobId) {
      setPageTexts(new Map())
      setTokenCount(0)
      setIsConnected(false)
      setError(null)
      chunksRef.current = new Map()
      return
    }

    // Reset state for new job
    setPageTexts(new Map())
    setTokenCount(0)
    setError(null)
    chunksRef.current = new Map()

    // Subscribe to real-time streaming tokens
    const channel = supabase
      .channel(`streaming_tokens:${jobId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'streaming_tokens',
          filter: `job_id=eq.${jobId}`
        },
        (payload) => {
          const token = payload.new as StreamingToken

          console.log('[PHASE 4] Streaming token received:', {
            jobId,
            page: token.page_num,
            sequence: token.chunk_sequence,
            length: token.chunk_text.length
          })

          // Get or create chunks map for this page
          let pageChunks = chunksRef.current.get(token.page_num)
          if (!pageChunks) {
            pageChunks = new Map()
            chunksRef.current.set(token.page_num, pageChunks)
          }

          // Store chunk by sequence number
          pageChunks.set(token.chunk_sequence, token.chunk_text)

          // Rebuild accumulated text in sequence order
          const sortedChunks = Array.from(pageChunks.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([_, text]) => text)
          const accumulatedText = sortedChunks.join('')

          // Update page texts
          setPageTexts(prev => {
            const next = new Map(prev)
            next.set(token.page_num, accumulatedText)
            return next
          })

          // Increment token count
          setTokenCount(prev => prev + 1)
        }
      )
      .subscribe((status) => {
        console.log('[PHASE 4] Streaming tokens subscription status:', status)
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

  return { pageTexts, tokenCount, isConnected, error }
}
