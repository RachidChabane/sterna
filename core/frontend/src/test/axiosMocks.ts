import { AxiosHeaders, type AxiosResponse } from 'axios'

/**
 * Builds a minimal, correctly-typed `AxiosResponse` for mocking a resolved
 * axios call (`vi.spyOn(...).mockResolvedValue(...)`, `vi.mocked(...).mockResolvedValue(...)`).
 * Fills the required envelope fields (status, statusText, headers, config)
 * with harmless defaults so tests only need to supply the `data` they care about.
 */
export function makeAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config: { headers: new AxiosHeaders() },
  }
}
