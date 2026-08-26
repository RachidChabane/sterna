/**
 * Coverage test for the tool-renderer registry against the backend's
 * per-tool plugin registry (llm.agent_core.registry.discover_tools(),
 * synced to agent-core-tool-ids.json by script/tool-ids-snapshot).
 *
 * Two assertions, not one:
 *
 *  (a) every id in the committed list resolves to *some* entry — trivially
 *      true, since `getRendererEntry` always falls back to `DEFAULT_ENTRY`.
 *  (b) the ids that resolve to `DEFAULT_ENTRY` are exactly the ones this
 *      file has explicitly acknowledged as intentionally generic
 *      (`EXPECTED_DEFAULT_TOOL_IDS`).
 *
 * (b) is what makes this fail when the backend adds a tool: a new id in
 * agent-core-tool-ids.json that isn't in `EXPECTED_DEFAULT_TOOL_IDS`
 * resolves to `DEFAULT_ENTRY` by construction, and the test then demands
 * a conscious choice — give it a renderer in registry.ts, or add it here
 * as an acknowledged default — rather than silently passing.
 */
import { describe, it, expect } from 'vitest'
import agentCoreToolIds from '@/api/generated/agent-core-tool-ids.json'
import { getRendererEntry, DEFAULT_ENTRY } from '../registry'

// Agent-core tool ids with no tool-specific renderer: they render with
// the generic icon + name + summary header and no result body. Adding a
// new entry here is a real review decision, not busywork — it is saying
// "this tool intentionally has no bespoke rendering."
const EXPECTED_DEFAULT_TOOL_IDS = new Set([
  'animate_character',
  'animate_image',
  'brave_local_search',
  'brave_news_search',
  'brave_web_search',
  'clone_repo',
  'edit_image',
  'explore_codebase',
  'fetch_web_page',
  'generate_image',
  'generate_video',
  'geocode_address',
  'get_air_quality',
  'get_directions',
  'get_place_details',
  'get_street_view',
  'get_tool_details',
  'prepare_pull_request',
  'search_nearby_places',
  'upscale_video',
])

describe('tool-renderer registry — agent_core coverage', () => {
  it('the committed agent_core tool id list is non-empty (sanity: catches an empty/broken sync)', () => {
    expect(agentCoreToolIds.length).toBeGreaterThan(0)
  })

  it('every acknowledged-default id is still a real agent_core tool id (catches a stale entry)', () => {
    const known = new Set(agentCoreToolIds)
    for (const id of EXPECTED_DEFAULT_TOOL_IDS) {
      expect(known.has(id), `${id} is in EXPECTED_DEFAULT_TOOL_IDS but not in agent-core-tool-ids.json`).toBe(true)
    }
  })

  it.each(agentCoreToolIds as string[])(
    'resolves %s to a renderer, and to the default only if acknowledged',
    (toolId) => {
      const entry = getRendererEntry(toolId)
      const usesDefault = entry === DEFAULT_ENTRY

      if (EXPECTED_DEFAULT_TOOL_IDS.has(toolId)) {
        expect(usesDefault, `${toolId} is acknowledged as default but now has a bespoke renderer — drop it from EXPECTED_DEFAULT_TOOL_IDS`).toBe(true)
      } else {
        expect(usesDefault, `${toolId} has no renderer and is not acknowledged as an intentional default — add one in registry.ts, or add it to EXPECTED_DEFAULT_TOOL_IDS if the generic renderer is correct for it`).toBe(false)
      }
    }
  )

  it('falls back to the default renderer for a tool id it has never heard of', () => {
    expect(getRendererEntry('some_future_tool_the_backend_has_not_added_yet')).toBe(DEFAULT_ENTRY)
  })
})
