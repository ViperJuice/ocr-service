/**
 * Supabase client initialization for frontend Realtime subscriptions.
 * 
 * Phase 3.5: Add Realtime implementation alongside existing SSE.
 */

import { createClient } from '@supabase/supabase-js'
import type { Database } from '@/types/database'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing Supabase environment variables. Please check .env.local'
  )
}

/**
 * Supabase client instance with Realtime configuration.
 * 
 * Configuration:
 * - eventsPerSecond: 10 (rate limiting for Realtime events)
 */
export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey, {
  realtime: {
    params: {
      eventsPerSecond: 10
    }
  }
})
