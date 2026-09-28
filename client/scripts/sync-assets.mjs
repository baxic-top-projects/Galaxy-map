#!/usr/bin/env node
/**
 * Map plate textures and GLBs are stored in S3 (galaxybucket).
 * Upload with: python tools/upload_models_to_s3.py
 *
 * This script no longer copies heavy assets into client/public.
 */
console.log(
  JSON.stringify(
    {
      note: 'Models and textures are served from S3 via asset-service / VITE_ASSETS_BASE',
      upload: 'python tools/upload_models_to_s3.py',
    },
    null,
    2,
  ),
)
