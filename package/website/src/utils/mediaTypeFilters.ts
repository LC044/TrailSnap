/** Upgrade the previous independent panorama toggle to a virtual media type. */
export const normalizeMediaTypeFilters = (fileTypes: string[] = [], legacyPanorama?: unknown): string[] => {
  return [...new Set([
    ...fileTypes,
    ...(legacyPanorama === true || legacyPanorama === 'true' ? ['panorama'] : []),
  ])];
};
