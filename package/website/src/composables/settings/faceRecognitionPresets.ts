export type FaceRecognitionParameters = {
  face_recognition_threshold: number
  face_cluster_threshold: number
  face_cluster_merge_threshold: number
  face_identity_match_threshold: number
  face_identity_merge_threshold: number
  face_rescan_auto_match_threshold: number
  face_rescan_candidate_threshold: number
  face_rescan_removal_threshold: number
  face_recognition_min_photos: number
}

export const faceRecognitionPresets = {
  loose: {
    label: '宽松',
    parameters: {
      face_recognition_threshold: 0.65,
      face_cluster_threshold: 0.6,
      face_cluster_merge_threshold: 0.3,
      face_identity_match_threshold: 0.51,
      face_identity_merge_threshold: 0.24,
      face_rescan_auto_match_threshold: 0.4,
      face_rescan_candidate_threshold: 0.55,
      face_rescan_removal_threshold: 0.65,
      face_recognition_min_photos: 3,
    },
  },
  normal: {
    label: '普通',
    parameters: {
      face_recognition_threshold: 0.7,
      face_cluster_threshold: 0.5,
      face_cluster_merge_threshold: 0.25,
      face_identity_match_threshold: 0.425,
      face_identity_merge_threshold: 0.2,
      face_rescan_auto_match_threshold: 0.35,
      face_rescan_candidate_threshold: 0.45,
      face_rescan_removal_threshold: 0.52,
      face_recognition_min_photos: 5,
    },
  },
  strict: {
    label: '严格',
    parameters: {
      face_recognition_threshold: 0.8,
      face_cluster_threshold: 0.35,
      face_cluster_merge_threshold: 0.175,
      face_identity_match_threshold: 0.2975,
      face_identity_merge_threshold: 0.14,
      face_rescan_auto_match_threshold: 0.28,
      face_rescan_candidate_threshold: 0.38,
      face_rescan_removal_threshold: 0.48,
      face_recognition_min_photos: 8,
    },
  },
} satisfies Record<string, { label: string; parameters: FaceRecognitionParameters }>

export type FaceRecognitionPreset = keyof typeof faceRecognitionPresets

export function detectFaceRecognitionPreset(parameters: FaceRecognitionParameters): FaceRecognitionPreset | 'custom' {
  for (const key of Object.keys(faceRecognitionPresets) as FaceRecognitionPreset[]) {
    const preset = faceRecognitionPresets[key].parameters
    if ((Object.keys(preset) as Array<keyof FaceRecognitionParameters>).every(
      field => Math.abs(parameters[field] - preset[field]) < 0.000001,
    )) return key
  }
  return 'custom'
}
