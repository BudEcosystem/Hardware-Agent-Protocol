/**
 * Work items over the SDK protocol: `invoke` runs a request as a work item
 * and follows it until `work/settled`; `HarnessWork` reads and operates on
 * items as `budmh work` does, and `HarnessTriggers` reads and overrides the
 * trigger rules as `budmh trigger` does. The design twin is the Python
 * SDK's `HarnessWork` and `HarnessTriggers`; both speak the methods
 * `@budmh/transport-sdk` registers.
 *
 * @module @budmh/sdk-client/work
 */

import type {
  SdkRequestResult, TriggerAdmitParams, TriggerOverrideParams, TriggerRulesParams, WorkAnswerParams, WorkListParams, WorkRetryParams,
  WorkSettledNotification, WorkSubmissionKind,
} from '@budmh/sdk-protocol'
import { isRecord, type HarnessClient } from './client.ts'
import type { HarnessNotification, RunResult } from './types.ts'

/** Options of one invoked or resumed item. */
export interface FollowOptions {
  /** Observer invoked with every notification of the item and its session, in wire order. */
  onNotification?: (notification: HarnessNotification) => void
}

/** Options of `BudMetaHarness.invoke`. */
export interface InvokeOptions extends FollowOptions {
  /** The request id; a repeat continues the item the first call admitted. Minted by the runtime when absent. */
  requestId?: string
  /** The SDK session to run in; an unknown id composes it. Minted by the runtime when absent. */
  sessionId?: string
  /** The agent of a new session: a preset id or a registry reference. */
  agent?: string
}

/**
 * One item followed until it ended: the session events the runtime streamed meanwhile and its settlement. A
 * `finalResponse` is the last assistant message the item's session produced in that interval, or the stored result's
 * text when the session produced none here (an item that had already ended).
 */
export interface WorkRunResult extends RunResult {
  /** The item. */
  workItemId: string
  /** What the call did with the item. */
  submission: WorkSubmissionKind
  /** The item's `work/settled` notification. */
  settled: WorkSettledNotification
}

/** The `invoke` result: the item's run and its request id. */
export interface InvokeResult extends WorkRunResult {
  /** The request id, as given or minted by the runtime. */
  requestId: string
}

/**
 * Whether a `work/settled` payload carries the fields a client reads.
 * @param value - the notification's params.
 * @returns whether the item, its status and its text are present.
 */
export function isSettledPayload(value: unknown): value is WorkSettledNotification {
  return isRecord(value) && typeof value.workItemId === 'string' && typeof value.status === 'string' && typeof value.text === 'string'
}

/** Starts an item and resolves with it and the session it runs in. */
export type ItemStart = () => Promise<{ readonly workItemId: string; readonly sessionId?: string; readonly submission: WorkSubmissionKind }>

/**
 * Follow an item until its `work/settled`.
 * @param start - sends the request that starts or continues the item.
 * @param options - the observer.
 * @returns the item's run.
 */
export type ItemFollower = (start: ItemStart, options?: FollowOptions) => Promise<WorkRunResult>

/**
 * The work items of one runtime, read and operated on as `budmh work` does. Each method starts the runtime first.
 */
export class HarnessWork {
  /**
   * @param client - resolves the started client.
   * @param follow - follows an item until it ends.
   */
  constructor(private readonly client: () => Promise<HarnessClient>, private readonly follow: ItemFollower) {}

  /**
   * Read one item with its history, inputs and questions.
   * @param workItemId - the item.
   * @returns the item and its rows.
   */
  async get(workItemId: string): Promise<SdkRequestResult<'work/get'>> {
    return (await this.client()).getWorkItem(workItemId)
  }

  /**
   * Read one page of items from one index.
   * @param params - `open` (default), `attention` or `closed`, a status of open items, the cursor and the page size.
   * @returns the items and the next page's cursor.
   */
  async list(params: WorkListParams = {}): Promise<SdkRequestResult<'work/list'>> {
    return (await this.client()).listWorkItems(params)
  }

  /**
   * Answer an item's question, or queue the answer as input when no question takes it.
   * @param params - the item, the answer, and optionally the question and the answer's key.
   * @returns what was admitted, or why nothing was.
   */
  async answer(params: WorkAnswerParams): Promise<SdkRequestResult<'work/answer'>> {
    return (await this.client()).answerWorkItem(params)
  }

  /**
   * Cancel an item and its children.
   * @param workItemId - the item.
   * @param reason - why, recorded on its history.
   * @returns the applied change, or why nothing changed.
   */
  async cancel(workItemId: string, reason: string): Promise<SdkRequestResult<'work/cancel'>> {
    return (await this.client()).cancelWorkItem(workItemId, reason)
  }

  /**
   * Run an item again in a new attempt.
   * @param params - the item, and optionally a fresh session or another agent.
   * @returns the applied change, or why nothing changed.
   */
  async retry(params: WorkRetryParams): Promise<SdkRequestResult<'work/retry'>> {
    return (await this.client()).retryWorkItem(params)
  }

  /**
   * Give an item an agent; an item that waits for a route is launched on it.
   * @param workItemId - the item.
   * @param agent - the agent reference.
   * @returns the applied change, or why nothing changed.
   */
  async route(workItemId: string, agent: string): Promise<SdkRequestResult<'work/route'>> {
    return (await this.client()).routeWorkItem(workItemId, agent)
  }

  /**
   * Take an item over in this runtime, as a CLI re-run of its request id does, and follow it until it ends: its
   * session is loaded here, an interrupted turn continues after the recovery note, and an item that had ended
   * answers from its stored result.
   * @param workItemId - the item.
   * @param options - the observer.
   * @returns the item's run.
   */
  async resume(workItemId: string, options: FollowOptions = {}): Promise<WorkRunResult> {
    const client = await this.client()
    return this.follow(() => client.resumeWorkItem(workItemId), options)
  }
}

/** The trigger rules of one runtime, read and overridden as `budmh trigger` does; and generic trigger admission. */
export class HarnessTriggers {
  /**
   * @param client - resolves the started client.
   */
  constructor(private readonly client: () => Promise<HarnessClient>) {}

  /**
   * Read the resolved rules.
   * @param params - only rules of an agent, or in some states.
   * @returns the rules, sorted by id.
   */
  async rules(params: TriggerRulesParams = {}): Promise<SdkRequestResult<'trigger/rules'>> {
    return (await this.client()).triggerRules(params)
  }

  /**
   * Write a runtime override of one rule; a field the config file sets is refused.
   * @param params - the rule, `enabled` or a merge `patch`, an optional version pin, and the reason.
   * @returns the rule after the change.
   */
  async override(params: TriggerOverrideParams): Promise<SdkRequestResult<'trigger/override'>> {
    return (await this.client()).overrideTrigger(params)
  }

  /**
   * Remove the runtime override of one rule.
   * @param rule - the rule id.
   * @param reason - why, recorded on its history.
   * @returns the rule after the change, or null when the override named a rule that no longer exists.
   */
  async clearOverride(rule: string, reason: string): Promise<SdkRequestResult<'trigger/clear-override'>> {
    return (await this.client()).clearTriggerOverride(rule, reason)
  }

  /**
   * Explain why each rule matched a stored trigger or not.
   * @param intakeKey - the trigger's key, `<sourceInstance>:<nativeKey>`.
   * @param rule - one rule; every rule of the trigger's table when absent.
   * @returns per rule, `matched` or the first step it failed.
   */
  async explain(intakeKey: string, rule?: string): Promise<SdkRequestResult<'trigger/explain'>> {
    return (await this.client()).explainTrigger(intakeKey, rule)
  }

  /**
   * Admit one trigger through intake; every item it creates is launched, and `work/settled` and `work/attention`
   * arrive for each item it reached.
   * @param params - the trigger: its key, content and the optional routing fields.
   * @returns the admission.
   */
  async admit(params: TriggerAdmitParams): Promise<SdkRequestResult<'trigger/admit'>> {
    return (await this.client()).admitTrigger(params)
  }
}
