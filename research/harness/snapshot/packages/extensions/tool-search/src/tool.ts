/**
 * The `tool_search` tool: the model finds tools by name or capability among
 * every tool it can use. Matches it already sees are listed; matches the
 * composition registered deferred are loaded and reach its next request as
 * tool additions.
 * @module @budmh/tool-search/tool
 */

import type { Context } from '@budmh/cordis'
import z from '@budmh/schemastery'
import { defineTool } from '@budmh/tools'
import type {} from './index.ts'

export const name = 'tool-search-tool'
export const inject = ['tools', 'toolSearch']

/** The model-facing tool name. */
export const TOOL_SEARCH_NAME = 'tool_search'

/** Characters of a matched tool's description repeated in the result. */
const DESCRIPTION_PREVIEW_CHARS = 200

/** Plugin config for the `tool_search` row. */
export interface Config {
  /** The most matches one call lists, an integer from 1 to 20 (default 5). */
  maxMatches: number
}

export const Config: z<Config> = z.object({
  maxMatches: z.natural().min(1).max(20).default(5),
})

/** Shorten a description to its preview length. */
function preview(description: string): string {
  return description.length <= DESCRIPTION_PREVIEW_CHARS
    ? description
    : `${description.slice(0, DESCRIPTION_PREVIEW_CHARS - 1)}…`
}

/** `count` followed by `noun`, plural unless the count is one. */
function counted(count: number, noun: string): string {
  return `${String(count)} ${noun}${count === 1 ? '' : 's'}`
}

/**
 * Register `tool_search` in the calling scope.
 * @param ctx - the row's context; a preset row registers for the agents it composes.
 * @param config - the validated row config.
 */
export function apply(ctx: Context, config: Config): void {
  // Direct construction bypasses the Loader schema; reject the same values it would.
  const maxMatches = config.maxMatches
  if (!Number.isInteger(maxMatches) || maxMatches < 1 || maxMatches > 20) {
    throw new Error('tool-search-tool: maxMatches must be an integer from 1 to 20')
  }
  ctx.tools.register(defineTool({
    name: TOOL_SEARCH_NAME,
    description: 'Find tools by name or by what they do among every tool you can use. A match that is not in your tool list yet is added to it, callable from your next step. Use it when you are unsure which tool fits a task.',
    parameters: {
      query: {
        type: 'string',
        required: true,
        description: 'Keywords for the capability you need, an exact tool name, or `select:name1,name2` to get tools by name.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          matches: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                name: { type: 'string', required: true },
                description: { type: 'string', required: true },
                added: { type: 'boolean', required: true },
              },
            },
          },
          more: { type: 'integer', required: true },
        },
      },
      render(args, value) {
        if (value.matches.length === 0) {
          return [{ type: 'text', text: `No tools match "${args.query}".` }]
        }
        const added = value.matches.some(match => match.added)
        const lines = [
          `Found ${counted(value.matches.length, 'tool')}:`,
          ...value.matches.map(match => `- ${match.name}${match.added ? ' (added)' : ''}: ${preview(match.description)}`),
          ...added ? ['Tools marked (added) are callable from your next step.'] : [],
          ...value.more > 0 ? [`${counted(value.more, 'more tool')} matched; refine the query to see them.`] : [],
        ]
        return [{ type: 'text', text: lines.join('\n') }]
      },
    },
    // Loading is idempotent and commutative, so parallel searches cannot conflict.
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const agent = exec.agent
      if (agent === undefined) throw new Error('tool_search searches the tools of an agent; this call has none')
      // One extra hit keeps `maxMatches` full when this tool matches its own query.
      const result = await ctx.toolSearch.search(agent, args.query, maxMatches + 1)
      const others = result.hits.filter(hit => hit.name !== TOOL_SEARCH_NAME)
      const hits = others.slice(0, maxMatches)
      const added = new Set(ctx.toolSearch.activate(agent, hits.map(hit => hit.name)))
      // A tool unregistered while the search ran is no longer callable, so it is not listed.
      const callable = hits.filter(hit => ctx.tools.get(hit.name, agent) !== undefined)
      return {
        matches: callable.map(hit => ({ name: hit.name, description: hit.description, added: added.has(hit.name) })),
        more: result.more + others.length - hits.length,
      }
    },
  }))
}
