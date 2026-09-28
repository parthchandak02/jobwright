const key = (userId: string) => `jobwright-calibration-dismissed:${userId}`

export function isCalibrationDismissed(userId: string | null | undefined): boolean {
  if (!userId) return false
  try {
    return localStorage.getItem(key(userId)) === '1'
  } catch {
    return false
  }
}

export function dismissCalibration(userId: string | null | undefined) {
  if (!userId) return
  try {
    localStorage.setItem(key(userId), '1')
  } catch {
    /* storage unavailable */
  }
}
