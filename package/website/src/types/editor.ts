export type EditorTool = 'select' | 'draw' | 'text' | 'rect' | 'ellipse' | 'line' | 'crop'

export interface EditorExportOptions {
  format: 'jpeg' | 'png' | 'webp'
  quality: number
  multiplier: number
}
