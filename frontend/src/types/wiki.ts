export type WikiLanguage = 'english' | 'chinese'

export interface GenerateWikiRequest {
  repo?: string
  token?: string
  dir?: string
  name?: string
  include: string[]
  exclude: string[]
  max_size: number
  output: string
  language: WikiLanguage
  max_abstractions: number
  no_cache: boolean
}

export interface WikiFile {
  path: string
  size: number
  content: string
}

export interface GenerateWikiResponse {
  status: 'success'
  project_name: string
  output_dir: string
  files: WikiFile[]
  chapter_order: number[]
}
