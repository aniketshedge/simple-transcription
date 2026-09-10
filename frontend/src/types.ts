export interface TranscriptFile {
  id: string;
  name: string;
  size: number;
  status: string;
  stage: string;
  progress: number | null;
  eta_seconds: number | null;
  duration: number | null;
  error: string | null;
  warnings: string[];
  has_transcript: boolean;
}
export interface Job {
  id: string;
  name: string;
  model: string;
  diarize: boolean;
  status: string;
  created_at: number;
  files: TranscriptFile[];
  finished_files: number;
  cancel_requested: boolean;
}
export interface Config {
  speaker_labels_available: boolean;
  max_file_bytes: number;
  max_files: number;
  max_duration_seconds: number;
}
