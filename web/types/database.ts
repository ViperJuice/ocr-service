/**
 * TypeScript type definitions for Supabase database schema.
 * 
 * Generated from: supabase/migrations/20250114000001_initial_schema.sql
 * Phase 3.5: Type-safe Realtime subscriptions
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          user_id: string
          email: string
          api_key: string
          created_at: string
          is_active: boolean | null
        }
        Insert: {
          user_id?: string
          email: string
          api_key: string
          created_at?: string
          is_active?: boolean | null
        }
        Update: {
          user_id?: string
          email?: string
          api_key?: string
          created_at?: string
          is_active?: boolean | null
        }
      }
      files: {
        Row: {
          file_id: string
          user_id: string
          filename: string
          content_type: string
          size_bytes: number
          page_count: number | null
          storage_bucket: string | null
          storage_path: string
          uploaded_at: string
          expires_at: string | null
          deleted_at: string | null
          metadata: Json
        }
        Insert: {
          file_id?: string
          user_id: string
          filename: string
          content_type: string
          size_bytes: number
          page_count?: number | null
          storage_bucket?: string | null
          storage_path: string
          uploaded_at?: string
          expires_at?: string | null
          deleted_at?: string | null
          metadata?: Json
        }
        Update: {
          file_id?: string
          user_id?: string
          filename?: string
          content_type?: string
          size_bytes?: number
          page_count?: number | null
          storage_bucket?: string | null
          storage_path?: string
          uploaded_at?: string
          expires_at?: string | null
          deleted_at?: string | null
          metadata?: Json
        }
      }
      batch_jobs: {
        Row: {
          batch_job_id: string
          user_id: string
          name: string | null
          status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          total_documents: number
          documents_completed: number | null
          overall_progress_pct: number | null
          created_at: string
          started_at: string | null
          completed_at: string | null
          model: string
          prompt_type: string | null
          custom_prompts: Json | null
          processing_options: Json
          output_format: string | null
          error_message: string | null
          metadata: Json
        }
        Insert: {
          batch_job_id?: string
          user_id: string
          name?: string | null
          status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          total_documents: number
          documents_completed?: number | null
          overall_progress_pct?: number | null
          created_at?: string
          started_at?: string | null
          completed_at?: string | null
          model?: string
          prompt_type?: string | null
          custom_prompts?: Json | null
          processing_options?: Json
          output_format?: string | null
          error_message?: string | null
          metadata?: Json
        }
        Update: {
          batch_job_id?: string
          user_id?: string
          name?: string | null
          status?: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          total_documents?: number
          documents_completed?: number | null
          overall_progress_pct?: number | null
          created_at?: string
          started_at?: string | null
          completed_at?: string | null
          model?: string
          prompt_type?: string | null
          custom_prompts?: Json | null
          processing_options?: Json
          output_format?: string | null
          error_message?: string | null
          metadata?: Json
        }
      }
      jobs: {
        Row: {
          job_id: string
          user_id: string
          file_id: string
          filename: string
          model: string
          prompt_type: string | null
          custom_prompts: Json | null
          processing_options: Json
          output_format: string | null
          status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          created_at: string
          started_at: string | null
          completed_at: string | null
          total_pages: number | null
          pages_completed: number | null
          current_stage: string | null
          progress_pct: number | null
          result_path: string | null
          error_message: string | null
          parent_job_id: string | null
          version_number: number | null
          parent_batch_id: string | null
          metadata: Json
        }
        Insert: {
          job_id?: string
          user_id: string
          file_id: string
          filename: string
          model?: string
          prompt_type?: string | null
          custom_prompts?: Json | null
          processing_options?: Json
          output_format?: string | null
          status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          created_at?: string
          started_at?: string | null
          completed_at?: string | null
          total_pages?: number | null
          pages_completed?: number | null
          current_stage?: string | null
          progress_pct?: number | null
          result_path?: string | null
          error_message?: string | null
          parent_job_id?: string | null
          version_number?: number | null
          parent_batch_id?: string | null
          metadata?: Json
        }
        Update: {
          job_id?: string
          user_id?: string
          file_id?: string
          filename?: string
          model?: string
          prompt_type?: string | null
          custom_prompts?: Json | null
          processing_options?: Json
          output_format?: string | null
          status?: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
          created_at?: string
          started_at?: string | null
          completed_at?: string | null
          total_pages?: number | null
          pages_completed?: number | null
          current_stage?: string | null
          progress_pct?: number | null
          result_path?: string | null
          error_message?: string | null
          parent_job_id?: string | null
          version_number?: number | null
          parent_batch_id?: string | null
          metadata?: Json
        }
      }
      page_results: {
        Row: {
          page_result_id: string
          job_id: string
          page_num: number
          ocr_text: string | null
          ocr_completed_at: string | null
          ocr_processing_time: number | null
          merge_text: string | null
          merge_completed_at: string | null
          merge_processing_time: number | null
          metadata: Json
        }
        Insert: {
          page_result_id?: string
          job_id: string
          page_num: number
          ocr_text?: string | null
          ocr_completed_at?: string | null
          ocr_processing_time?: number | null
          merge_text?: string | null
          merge_completed_at?: string | null
          merge_processing_time?: number | null
          metadata?: Json
        }
        Update: {
          page_result_id?: string
          job_id?: string
          page_num?: number
          ocr_text?: string | null
          ocr_completed_at?: string | null
          ocr_processing_time?: number | null
          merge_text?: string | null
          merge_completed_at?: string | null
          merge_processing_time?: number | null
          metadata?: Json
        }
      }
      job_events: {
        Row: {
          event_id: number
          job_id: string
          event_type: string
          event_data: Json
          created_at: string
        }
        Insert: {
          event_id?: number
          job_id: string
          event_type: string
          event_data?: Json
          created_at?: string
        }
        Update: {
          event_id?: number
          job_id?: string
          event_type?: string
          event_data?: Json
          created_at?: string
        }
      }
      directories: {
        Row: {
          directory_id: string
          user_id: string
          name: string
          total_size: number
          uploaded_at: string
        }
        Insert: {
          directory_id?: string
          user_id: string
          name: string
          total_size: number
          uploaded_at?: string
        }
        Update: {
          directory_id?: string
          user_id?: string
          name?: string
          total_size?: number
          uploaded_at?: string
        }
      }
      directory_files: {
        Row: {
          directory_id: string
          file_id: string
          sequence_num: number
        }
        Insert: {
          directory_id: string
          file_id: string
          sequence_num: number
        }
        Update: {
          directory_id?: string
          file_id?: string
          sequence_num?: number
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
  }
}
