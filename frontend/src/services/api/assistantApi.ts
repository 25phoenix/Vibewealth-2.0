import { apiClient, ApiClient, ApiContractError } from './apiClient'

export type TurnStatus = 'pending' | 'completed' | 'failed' | 'abandoned'
export interface TurnMetadata { id: string; status: TurnStatus; attempt_no: number }
export interface AssistantMessage {
  id: string; conversation_id: string; sequence_no: number; role: 'user' | 'assistant'
  content: string; created_at: string; turn: TurnMetadata | null
}
export interface AssistantTurn {
  id: string; conversation_id: string; idempotency_key: string; status: TurnStatus; attempt_no: number
  user_message: AssistantMessage; assistant_message: AssistantMessage | null
  created_at: string; attempt_started_at: string; attempt_finished_at: string | null
  lease_expires_at: string | null; context_as_of: string | null; financial_date: string | null
  lease_expired: boolean; can_retry: boolean; can_abandon: boolean
  error: { code: string; message: string } | null
}
export interface Conversation {
  id: string; title: string | null; created_at: string; updated_at: string
  last_sequence_no: number; unresolved_turn: AssistantTurn | null
}
export interface AssistantPageDto<T> { items: T[]; total: number; offset: number; limit: number }
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const failures = new Set(['PROVIDER_TIMEOUT','PROVIDER_UNAVAILABLE','PROVIDER_RATE_LIMITED','INVALID_PROVIDER_RESPONSE',
  'CONTEXT_UNAVAILABLE','SESSION_INVALIDATED','INTERNAL_FAILURE','CONTEXT_LIMIT','FINANCIAL_INVARIANT','OUTPUT_REJECTED','GENERATION_INTERRUPTED'])
function invalid(): never { throw new ApiContractError('assistant') }
function object(value: unknown, fields: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid()
  const row = value as Record<string, unknown>
  if (Object.keys(row).length !== fields.length || fields.some((key) => !(key in row))) return invalid()
  return row
}
function text(value: unknown, max = 16000): string {
  if (typeof value !== 'string' || !value || value.length > max) return invalid()
  return value
}
function uuid(value: unknown): string { const id = text(value, 36); if (!uuidPattern.test(id)) return invalid(); return id }
function integer(value: unknown, min = 0, max = 2147483647): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) return invalid()
  return value
}
function dateOnly(value: unknown): string {
  const result=text(value,10)
  if(result.startsWith('0000-') || !/^\d{4}-\d{2}-\d{2}$/.test(result) || !Number.isFinite(Date.parse(result+'T00:00:00Z')) ||
    new Date(result+'T00:00:00Z').toISOString().slice(0,10)!==result)return invalid()
  return result
}
function timestamp(value: unknown): string {
  const result=text(value,40)
  if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(result) ||
     !Number.isFinite(Date.parse(result)))return invalid()
  dateOnly(result.slice(0,10))
  if(Number(result.slice(11,13))>23 || Number(result.slice(14,16))>59 || Number(result.slice(17,19))>59)return invalid()
  return result
}
function instant(value: string): bigint {
  const fraction=value.match(/\.(\d{1,6})/)?.[1]??''
  return BigInt(Date.parse(value.replace(/\.\d{1,6}/,'')))*1000n+BigInt(fraction.padEnd(6,'0'))
}
function status(value: unknown): TurnStatus {
  if (typeof value !== 'string' || !['pending','completed','failed','abandoned'].includes(value)) return invalid()
  return value as TurnStatus
}
function metadata(value: unknown): TurnMetadata {
  const r=object(value,['id','status','attempt_no'])
  return { id:uuid(r.id),status:status(r.status),attempt_no:integer(r.attempt_no,1,3) }
}
export function parseAssistantMessage(value: unknown): AssistantMessage {
  const r=object(value,['id','conversation_id','sequence_no','role','content','created_at','turn'])
  if (r.role !== 'user' && r.role !== 'assistant') return invalid()
  return { id:uuid(r.id),conversation_id:uuid(r.conversation_id),sequence_no:integer(r.sequence_no,1),
    role:r.role,content:text(r.content),created_at:timestamp(r.created_at),turn:r.turn===null?null:metadata(r.turn) }
}
export function parseAssistantTurn(value: unknown): AssistantTurn {
  const r=object(value,['id','conversation_id','idempotency_key','status','attempt_no','user_message','assistant_message',
    'created_at','attempt_started_at','attempt_finished_at','lease_expires_at','context_as_of','financial_date',
    'lease_expired','can_retry','can_abandon','error'])
  for (const field of ['lease_expired','can_retry','can_abandon']) if (typeof r[field] !== 'boolean') return invalid()
  let error=null
  if (r.error !== null) {
    const e=object(r.error,['code','message']); const code=text(e.code,80)
    if (!failures.has(code)) return invalid()
    if(e.message!==assistantTurnErrorDetails[code])return invalid()
    error={ code,message:text(e.message,160) }
  }
  const state=status(r.status)
  const user=parseAssistantMessage(r.user_message)
  const assistant=r.assistant_message===null?null:parseAssistantMessage(r.assistant_message)
  const id=uuid(r.id), conversation=uuid(r.conversation_id), attempt=integer(r.attempt_no,1,3)
  if (user.role!=='user' || user.conversation_id!==conversation ||
      (assistant && (assistant.role!=='assistant' || assistant.conversation_id!==conversation || assistant.sequence_no!==user.sequence_no+1)) ||
      (state==='completed')!==(assistant!==null) || (state==='failed' && !error) ||
      (state==='abandoned' && error)) return invalid()
  const day=r.financial_date===null?null:dateOnly(r.financial_date)
  const created=timestamp(r.created_at), started=timestamp(r.attempt_started_at)
  const finished=r.attempt_finished_at===null?null:timestamp(r.attempt_finished_at)
  const lease=r.lease_expires_at===null?null:timestamp(r.lease_expires_at)
  const observed=r.context_as_of===null?null:timestamp(r.context_as_of)
  if(instant(created)>instant(started) || (finished && instant(finished)<instant(started)) ||
    (observed && instant(observed)<instant(started)) || (day===null)!==(observed===null))return invalid()
  if(observed){
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(observed))
    const india=['year','month','day'].map(kind=>parts.find(part=>part.type===kind)?.value).join('-')
    if(day!==india)return invalid()
  }
  for(const m of [user,assistant])if(m && (!m.turn || m.turn.id!==id || m.turn.status!==state || m.turn.attempt_no!==attempt))return invalid()
  if(user.sequence_no>=2147483647 || user.content.replace(/\r\n?/g,'\n').trim()!==user.content || Array.from(user.content).length>4000 ||
    user.content.includes(String.fromCharCode(0)) || /[\uD800-\uDFFF]/u.test(user.content))return invalid()
  const retryable=new Set(['PROVIDER_TIMEOUT','PROVIDER_UNAVAILABLE','PROVIDER_RATE_LIMITED','INVALID_PROVIDER_RESPONSE',
    'CONTEXT_UNAVAILABLE','SESSION_INVALIDATED','INTERNAL_FAILURE'])
  if(state==='pending'){
    if(!lease || instant(lease)<=instant(started) || finished || assistant ||
      (error?.code??null)!==(r.lease_expired?'GENERATION_INTERRUPTED':null) ||
      r.can_retry!==(r.lease_expired && attempt<3) || r.can_abandon!==r.lease_expired)return invalid()
  }else{
    if(lease || !finished || r.lease_expired ||
      (state==='failed' && (!error || error.code==='GENERATION_INTERRUPTED')) ||
      (state!=='failed' && error) || r.can_abandon!==(state==='failed') ||
      r.can_retry!==(state==='failed' && attempt<3 && retryable.has(error?.code??'')))return invalid()
    if(state==='completed' && (!observed || !assistant))return invalid()
  }
  return {id,conversation_id:conversation,idempotency_key:uuid(r.idempotency_key),status:state,attempt_no:attempt,
    user_message:user,assistant_message:assistant,created_at:created,attempt_started_at:started,
    attempt_finished_at:finished,lease_expires_at:lease,context_as_of:observed,financial_date:day,
    lease_expired:r.lease_expired as boolean,can_retry:r.can_retry as boolean,can_abandon:r.can_abandon as boolean,error}

}
export function parseConversation(value: unknown): Conversation {
  const r=object(value,['id','title','created_at','updated_at','last_sequence_no','unresolved_turn'])
  const id=uuid(r.id), turn=r.unresolved_turn===null?null:parseAssistantTurn(r.unresolved_turn)
  if(Date.parse(timestamp(r.updated_at))<Date.parse(timestamp(r.created_at)))return invalid()
  if (turn && (turn.user_message.sequence_no>integer(r.last_sequence_no) || turn.conversation_id!==id || !['pending','failed'].includes(turn.status))) return invalid()
  return { id,title:r.title===null?null:text(r.title,160),created_at:timestamp(r.created_at),updated_at:timestamp(r.updated_at),
    last_sequence_no:integer(r.last_sequence_no),unresolved_turn:turn }
}
function page<T>(value: unknown, parse: (value: unknown)=>T): AssistantPageDto<T> {
  const r=object(value,['items','total','offset','limit'])
  const limit=integer(r.limit,1,100), total=integer(r.total), offset=integer(r.offset)
  if (!Array.isArray(r.items) || r.items.length>limit || r.items.length>Math.max(0,total-offset)) return invalid()
  return { items:r.items.map(parse),limit,total,offset }
}
export const parseConversationPage=(v: unknown)=>page(v,parseConversation)
export const parseAssistantMessagePage=(v: unknown)=>page(v,parseAssistantMessage)
export class AssistantApi {
  private readonly client: ApiClient
  constructor(client: ApiClient = apiClient) { this.client=client }
  list(offset=0,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations?offset=${offset}&limit=50`,{signal,cache:'no-store',parseError:parseAssistantError,parseResponse:parseConversationPage}) }
  create(id: string,title: string|null=null,signal?: AbortSignal) { return this.client.request('/api/assistant/conversations',{signal,method:'POST',body:{id:uuid(id),title},cache:'no-store',parseError:parseAssistantError,parseResponse:parseConversation}) }
  get(id: string,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations/${uuid(id)}`,{signal,cache:'no-store',parseError:parseAssistantError,parseResponse:parseConversation}) }
  async delete(id: string,signal?: AbortSignal) { await this.client.request(`/api/assistant/conversations/${uuid(id)}`,{signal,method:'DELETE',cache:'no-store',parseError:parseAssistantError}) }
  messages(id: string,offset=0,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations/${uuid(id)}/messages?offset=${offset}&limit=100`,{signal,cache:'no-store',parseError:parseAssistantError,parseResponse:parseAssistantMessagePage}) }
  submit(id: string,key: string,content: string,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations/${uuid(id)}/messages`,{signal,method:'POST',headers:{'Idempotency-Key':uuid(key)},body:{content},cache:'no-store',parseError:parseAssistantError,parseResponse:parseAssistantTurn}) }
  lookup(key: string,signal?: AbortSignal) { return this.client.request('/api/assistant/turns/by-key',{signal,headers:{'Idempotency-Key':uuid(key)},cache:'no-store',parseError:parseAssistantError,parseResponse:parseAssistantTurn}) }
  turn(conversation: string,id: string,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations/${uuid(conversation)}/turns/${uuid(id)}`,{signal,cache:'no-store',parseError:parseAssistantError,parseResponse:parseAssistantTurn}) }
  action(conversation: string,id: string,action: 'retry'|'abandon',expected: number,signal?: AbortSignal) { return this.client.request(`/api/assistant/conversations/${uuid(conversation)}/turns/${uuid(id)}/${action}`,{signal,method:'POST',body:{expected_attempt_no:expected},cache:'no-store',parseError:parseAssistantError,parseResponse:parseAssistantTurn}) }
}
export const assistantApi=new AssistantApi()

export const assistantErrorDetails: Record<string,string> = {
  "AUTHENTICATION_REQUIRED": "Authentication required",
  "ORIGIN_REJECTED": "Request origin is not allowed",
  "CSRF_FAILED": "CSRF validation failed",
  "CONVERSATION_NOT_FOUND": "Conversation not found.",
  "TURN_NOT_FOUND": "Turn not found.",
  "ASSISTANT_ROUTE_NOT_FOUND": "Assistant route not found.",
  "METHOD_NOT_ALLOWED": "Method not allowed.",
  "CONVERSATION_CREATE_CONFLICT": "Conversation creation attributes conflict with the existing conversation.",
  "IDEMPOTENCY_CONFLICT": "The operation key was already used for a different request.",
  "UNRESOLVED_TURN": "Resolve the existing pending or failed turn before submitting another message.",
  "ATTEMPT_CONFLICT": "The turn attempt has changed. Retrieve its current state.",
  "TURN_NOT_RETRYABLE": "This turn cannot be retried.",
  "TURN_NOT_ABANDONABLE": "This turn cannot be abandoned.",
  "RETRY_LIMIT_REACHED": "The retry limit has been reached.",
  "CONVERSATION_LIMIT_REACHED": "The conversation limit has been reached.",
  "TURN_LIMIT_REACHED": "The conversation's turn limit has been reached.",
  "REQUEST_TOO_LARGE": "The request body exceeds the size limit.",
  "INVALID_REQUEST": "Invalid request",
  "RATE_LIMITED": "Too many assistant requests. Try again later.",
  "GENERATION_BUSY": "Assistant generation capacity is busy. Try again later.",
  "PROVIDER_DISABLED": "The assistant provider is disabled.",
  "PROVIDER_CONFIGURATION_INVALID": "The assistant provider configuration is invalid.",
  "DATABASE_UNAVAILABLE": "Assistant storage is unavailable. Resolve any pending operation before resubmitting.",
  "WORK_DEADLINE_EXCEEDED": "Assistant work exceeded its deadline. Resolve any pending operation before resubmitting.",
  "INTERNAL_ERROR": "The assistant request could not be completed. Resolve any pending operation before resubmitting."
}
const conflictCodes=new Set(['UNRESOLVED_TURN','ATTEMPT_CONFLICT','TURN_NOT_RETRYABLE','TURN_NOT_ABANDONABLE','RETRY_LIMIT_REACHED'])
export function parseAssistantError(value: unknown,statusCode: number) {
  const r=object(value,['detail','code','issues','current_turn']);const code=text(r.code,80)
  const expected=code==='AUTHENTICATION_REQUIRED'?401:['ORIGIN_REJECTED','CSRF_FAILED'].includes(code)?403:
    ['CONVERSATION_NOT_FOUND','TURN_NOT_FOUND','ASSISTANT_ROUTE_NOT_FOUND'].includes(code)?404:code==='METHOD_NOT_ALLOWED'?405:
    code==='REQUEST_TOO_LARGE'?413:code==='INVALID_REQUEST'?422:['RATE_LIMITED','GENERATION_BUSY'].includes(code)?429:
    ['PROVIDER_DISABLED','PROVIDER_CONFIGURATION_INVALID','DATABASE_UNAVAILABLE','WORK_DEADLINE_EXCEEDED'].includes(code)?503:
    code==='INTERNAL_ERROR'?500:409
  if(!Object.hasOwn(assistantErrorDetails,code) || r.detail!==assistantErrorDetails[code] || statusCode!==expected || !Array.isArray(r.issues))return invalid()
  if(r.issues.length && code!=='INVALID_REQUEST')return invalid()
  for(const issue of r.issues){const e=object(issue,['location','message'])
    if(typeof e.location!=='string' || typeof e.message!=='string' || !['body','id','title','content','conversation_id','turn_id','expected_attempt_no','offset','limit','Idempotency-Key','Content-Encoding'].includes(String(e.location)) ||
      !['Invalid value','Required field','Unexpected field'].includes(String(e.message)))return invalid()
  }
  const currentTurn=r.current_turn===null?null:parseAssistantTurn(r.current_turn)
  if(currentTurn && !conflictCodes.has(code))return invalid()
  return {code,detail:r.detail as string,currentTurn}
}

export const assistantTurnErrorDetails: Record<string,string> = {
  "PROVIDER_TIMEOUT": "The assistant provider timed out. You can retry.",
  "PROVIDER_UNAVAILABLE": "The assistant provider is unavailable. You can retry.",
  "PROVIDER_RATE_LIMITED": "The assistant provider is busy. Try again later.",
  "INVALID_PROVIDER_RESPONSE": "The assistant provider returned an invalid response. You can retry.",
  "CONTEXT_UNAVAILABLE": "Financial context could not be loaded. You can retry.",
  "SESSION_INVALIDATED": "Your session is no longer valid. Sign in before retrying.",
  "INTERNAL_FAILURE": "The assistant could not finish this attempt. You can retry.",
  "CONTEXT_LIMIT": "The required financial context exceeds the assistant's limits.",
  "FINANCIAL_INVARIANT": "The financial context could not be verified.",
  "OUTPUT_REJECTED": "The assistant response could not be verified.",
  "GENERATION_INTERRUPTED": "Generation was interrupted. Retry if available, or abandon this turn."
}
