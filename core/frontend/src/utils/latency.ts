/**
 * Latency formatting.
 *
 * Single authoritative definition for turning a chat message's latency into
 * display text. `Message.latency` is produced by `useMessageSending` as
 * `(endTime - startTime) / 1000`, i.e. it is expressed in SECONDS. Several call
 * sites used to divide by 1000 again, reporting a 10s answer as "0.01s".
 *
 * Note: this is for the chat pipeline only. The Consigliere pipeline reports
 * latency in milliseconds and formats it separately.
 */

const MILLISECONDS_PER_SECOND = 1000
const SUB_SECOND_THRESHOLD_MS = 1000

/**
 * Format a chat message latency given in seconds.
 *
 * @param latencySeconds latency in seconds, as stored on `Message.latency`
 * @param emptyPlaceholder text to return when no latency is available
 */
export function formatLatencyFromSeconds(
  latencySeconds?: number,
  emptyPlaceholder = '-'
): string {
  if (!latencySeconds) return emptyPlaceholder

  const latencyMs = latencySeconds * MILLISECONDS_PER_SECOND
  if (latencyMs < SUB_SECOND_THRESHOLD_MS) return `${Math.round(latencyMs)}ms`
  return `${latencySeconds.toFixed(2)}s`
}
