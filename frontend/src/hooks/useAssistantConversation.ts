import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from './authContext'
import { assistantApi, parseAssistantTurn } from '@/services/api/assistantApi'
import type { Conversation, AssistantMessage, AssistantTurn } from '@/services/api/assistantApi'
import { ApiError } from '@/services/api/apiClient'

const markerName='vibewealth.assistant.operation.v1'
interface Marker { version: 1; userId: string; conversationId: string; key: string }
interface Operation { marker: Marker; content?: string }
const aborted=(e: unknown)=>e instanceof Error && e.name==='AbortError'
function store(marker: Marker|null,owner: string|undefined) {
  if(!owner)return
  try { const name=`${markerName}:${owner}`;if(marker)sessionStorage.setItem(name,JSON.stringify(marker));else sessionStorage.removeItem(name) } catch { /* Memory retains the operation if storage is unavailable. */ }
}
function read(owner: string): Marker|null {
  try {
    const v=JSON.parse(sessionStorage.getItem(`${markerName}:${owner}`)||'null')
    if(v?.version===1 && v.userId===owner && typeof v.key==='string' && typeof v.conversationId==='string')return v
    // Read the previous pointer format without ever reconstructing a payload.
    if(v?.owner===owner && typeof v.key==='string' && typeof v.conversation==='string')return {version:1,userId:owner,key:v.key,conversationId:v.conversation}
  } catch { /* Invalid storage cannot supply a request body or owner identity. */ }
  return null
}
export function useAssistantConversation(enabled=true) {
  const {user,sessionIdentity,logout}=useAuth(), owner=user?.id
  const [conversations,setConversations]=useState<Conversation[]>([])
  const [conversation,setConversation]=useState<Conversation|null>(null)
  const [messages,setMessages]=useState<AssistantMessage[]>([])
  const [turn,setTurn]=useState<AssistantTurn|null>(null)
  const [isTyping,setBusy]=useState(false),[error,setError]=useState<string|null>(null)
  const [recovery,setRecovery]=useState<Operation|null>(null),[historyReviewed,setReviewed]=useState(false)
  const [historyOffset,setHistoryOffset]=useState(0),[totalMessages,setTotalMessages]=useState(0)
  const [totalConversations,setTotalConversations]=useState(0),[pollPaused,setPollPaused]=useState(false)
  const epoch=useRef(0),mounted=useRef(false),busy=useRef(false),active=useRef<string|null>(null)
  const creation=useRef<string|null>(null),pending=useRef<Operation|null>(null),retryAt=useRef(0)
  const requests=useRef(new Map<AbortController,'read'|'write'>())
  const accepted=useRef(new Map<string,{attempt: number; status: string}>())
  const valid=useCallback((e: number,id?: string)=>mounted.current && epoch.current===e && (id===undefined || active.current===id),[])
  const invalidate=useCallback((all=false)=>{
    epoch.current++
    for(const [controller,kind] of requests.current)if(all || kind==='read')controller.abort()
    return epoch.current
  },[])
  const request=useCallback(async <T,>(kind: 'read'|'write',run: (signal: AbortSignal)=>Promise<T>): Promise<T>=>{
    const controller=new AbortController();requests.current.set(controller,kind)
    try{return await run(controller.signal)}finally{requests.current.delete(controller)}
  },[])
  const remember=useCallback((operation: Operation|null)=>{
    pending.current=operation;setRecovery(operation);setReviewed(false);store(operation?.marker??null,owner)
  },[owner])
  const fail=useCallback((cause: unknown)=>{
    if(aborted(cause))return
    if(cause instanceof ApiError && cause.status===401){void logout();return}
    if(cause instanceof ApiError && cause.retryAfter)retryAt.current=Date.now()+cause.retryAfter*1000
    setError(cause instanceof ApiError && cause.code==='PROVIDER_DISABLED'
      ? 'The assistant provider is disabled. Your saved conversations remain available.'
      : cause instanceof Error?cause.message:'The assistant request failed. Please try again.')
  },[logout])
  useEffect(()=>{
    mounted.current=true;invalidate(true);busy.current=false;active.current=null;creation.current=null;accepted.current.clear()
    setBusy(false);setConversations([]);setConversation(null);setMessages([]);setTurn(null);setError(null);setReviewed(false)
    const marker=owner?read(owner):null;pending.current=marker?{marker}:null;setRecovery(pending.current)
    return ()=>{mounted.current=false;invalidate(true)}
  },[owner,sessionIdentity?.generation,invalidate])
  useEffect(()=>{
    if(!enabled){invalidate(true);busy.current=false;setBusy(false)}
  },[enabled,invalidate])
  const list=useCallback(async(offset=0)=>{
    const e=epoch.current
    try{const page=await request('read',signal=>assistantApi.list(offset,signal))
      if(valid(e)){setConversations(old=>offset?[...old,...page.items.filter(c=>!old.some(o=>o.id===c.id))]:page.items);setTotalConversations(page.total)}}
    catch(cause){if(valid(e))fail(cause)}
  },[request,valid,fail])
  useEffect(()=>{if(enabled)void list()},[enabled,sessionIdentity?.generation,list])
  const apply=useCallback((result: AssistantTurn,e: number)=>{
    if(!valid(e,result.conversation_id))return false
    const previous=accepted.current.get(result.id)
    if(previous && (previous.attempt>result.attempt_no ||
      (['completed','abandoned'].includes(previous.status) && (previous.status!==result.status || previous.attempt!==result.attempt_no)) ||
      (previous.attempt===result.attempt_no && previous.status==='failed' && result.status==='pending')))return false
    accepted.current.set(result.id,{attempt:result.attempt_no,status:result.status})
    setTurn(result);setMessages(old=>[...old.filter(m=>m.sequence_no!==result.user_message.sequence_no && m.sequence_no!==result.assistant_message?.sequence_no),
      result.user_message,...(result.assistant_message?[result.assistant_message]:[])].sort((a,b)=>a.sequence_no-b.sequence_no))
    if(pending.current?.marker.key===result.idempotency_key && pending.current.marker.conversationId===result.conversation_id)remember(null)
    return true
  },[valid,remember])
  const loadConversation=useCallback(async(id: string,e: number,recovered?: AssistantTurn)=>{
    if(!valid(e))return
    active.current=id;setPollPaused(false)
    setConversation(null);setMessages([]);setTurn(null);setHistoryOffset(0);setTotalMessages(0)
    const [current,page]=await Promise.all([request('read',s=>assistantApi.get(id,s)),request('read',s=>assistantApi.messages(id,0,s))])
    if(!valid(e,id))return
    setConversation(current);setMessages(page.items)
    // Offset counts rows actually paged, never extra messages merged from a turn.
    setHistoryOffset(page.offset+page.items.length);setTotalMessages(page.total)
    if(recovered)apply(recovered,e)
    if(current.unresolved_turn)apply(current.unresolved_turn,e)
    if(pending.current?.marker.conversationId===id)setReviewed(true)
  },[request,valid,apply])
  const select=useCallback(async(id: string)=>{
    if(busy.current)return
    const e=invalidate();busy.current=true;setBusy(true);setError(null)
    try{await loadConversation(id,e)}catch(cause){if(valid(e,id)){
      if(cause instanceof ApiError && cause.code==='CONVERSATION_NOT_FOUND' && pending.current?.marker.conversationId===id)setReviewed(true)
      fail(cause)
    }}
    finally{if(valid(e,id)){busy.current=false;setBusy(false)}}
  },[invalidate,loadConversation,valid,fail])
  const reconcileConflict=useCallback(async(cause: unknown,e: number,id: string)=>{
    if(!(cause instanceof ApiError) || !valid(e,id))return false
    if(cause.currentTurn){const current=parseAssistantTurn(cause.currentTurn);if(current.conversation_id===id)return apply(current,e)}
    return false
  },[valid,apply])
  const submitOperation=useCallback(async(operation: Operation,e: number,stage: 'initial'|'resend')=>{
    const {marker,content}=operation
    if(content===undefined)return false
    try{const result=await request('write',s=>assistantApi.submit(marker.conversationId,marker.key,content,s))
      return apply(result,e)
    }catch(cause){if(valid(e,marker.conversationId)){
      const reconciled=await reconcileConflict(cause,e,marker.conversationId)
      if(reconciled && pending.current===null)return true
      // These codes refuse this transmission before reservation. On a resend,
      // they cannot resolve the earlier uncertain transmission of the same key.
      const refusal=cause instanceof ApiError && ['ORIGIN_REJECTED','CSRF_FAILED','INVALID_REQUEST','REQUEST_TOO_LARGE',
        'UNRESOLVED_TURN','TURN_LIMIT_REACHED','PROVIDER_DISABLED','PROVIDER_CONFIGURATION_INVALID',
        'RATE_LIMITED','GENERATION_BUSY'].includes(cause.code??'')
      if(stage==='initial' && refusal && pending.current?.marker.key===marker.key)remember(null)
      // ATTEMPT_CONFLICT, IDEMPOTENCY_CONFLICT and ambiguous transport/server
      // failures never imply rollback. A matching current_turn may resolve it.
      fail(cause)
    }return false}
  },[request,apply,valid,reconcileConflict,remember,fail])
  const sendMessage=useCallback(async(content: string)=>{
    if(busy.current || pending.current || !content.trim() || Date.now()<retryAt.current || (turn && ['pending','failed'].includes(turn.status)))return false
    const normalized=content.replace(/\r\n?/g,'\n').trim()
    if(Array.from(normalized).length>4000 || normalized.includes(String.fromCharCode(0)) || /[\uD800-\uDFFF]/u.test(normalized)){
      setError('Messages must contain at most 4,000 Unicode characters and no invalid control characters.');return false
    }
    const e=invalidate();busy.current=true;setBusy(true);setError(null);setPollPaused(false)
    try{let current=conversation
      if(!current){creation.current??=crypto.randomUUID();current=await request('write',s=>assistantApi.create(creation.current!,null,s))
        if(!valid(e))return false;active.current=current.id;setConversation(current)}
      const operation: Operation={marker:{version:1,userId:owner!,conversationId:current.id,key:crypto.randomUUID()},content:normalized}
      remember(operation);return await submitOperation(operation,e,'initial')
    }catch(cause){if(valid(e))fail(cause);return false}
    finally{if(valid(e)){busy.current=false;setBusy(false);void list()}}
  },[turn,invalidate,conversation,request,valid,owner,remember,submitOperation,fail,list])
  const recover=useCallback(async()=>{
    const operation=pending.current;if(!operation || busy.current)return
    const e=invalidate();busy.current=true;setBusy(true);setError(null)
    try{const result=await request('read',s=>assistantApi.lookup(operation.marker.key,s))
      if(valid(e))await loadConversation(result.conversation_id,e,result)}
    catch(cause){if(valid(e)){
      if(cause instanceof ApiError && cause.code==='TURN_NOT_FOUND')setError('No committed operation is visible yet. This does not prove failure. You may check again, review saved history, or explicitly resend the original key and payload when available.')
      else fail(cause)
    }}finally{if(valid(e)){busy.current=false;setBusy(false)}}
  },[invalidate,request,valid,loadConversation,fail])
  const resubmit=useCallback(async()=>{
    const operation=pending.current;if(!operation?.content || busy.current || Date.now()<retryAt.current)return
    const e=invalidate(),id=operation.marker.conversationId
    if(active.current!==id){setMessages([]);setTurn(null);setConversation(null);setHistoryOffset(0);setTotalMessages(0)}
    active.current=id;busy.current=true;setBusy(true);setError(null)
    try{
      const accepted=await submitOperation(operation,e,'resend')
      if(valid(e,id))try{const current=await request('read',s=>assistantApi.get(id,s));if(valid(e,id))setConversation(current)}catch(cause){if(valid(e,id))fail(cause)}
      return accepted
    }finally{if(valid(e)){busy.current=false;setBusy(false);void list()}}
  },[invalidate,submitOperation,valid,list,request,fail])
  const lifecycle=useCallback(async(action: 'retry'|'abandon')=>{
    if(!turn || busy.current || Date.now()<retryAt.current)return
    const e=invalidate();busy.current=true;setBusy(true);setError(null);setPollPaused(false)
    try{const result=await request('write',s=>assistantApi.action(turn.conversation_id,turn.id,action,turn.attempt_no,s));apply(result,e)}
    catch(cause){if(valid(e,turn.conversation_id)){
      fail(cause);if(!await reconcileConflict(cause,e,turn.conversation_id))try{apply(await request('read',s=>assistantApi.turn(turn.conversation_id,turn.id,s)),e)}catch(next){if(valid(e))fail(next)}
    }}finally{if(valid(e)){busy.current=false;setBusy(false);void list()}}
  },[turn,invalidate,request,apply,valid,fail,reconcileConflict,list])
  useEffect(()=>{
    if(!enabled || !turn || turn.status!=='pending' || turn.lease_expired || isTyping || pollPaused)return
    const e=epoch.current
    const timer=setTimeout(()=>{void request('read',s=>assistantApi.turn(turn.conversation_id,turn.id,s)).then(
      result=>apply(result,e),cause=>{if(valid(e,turn.conversation_id) && !aborted(cause)){setPollPaused(true);fail(cause)}})},Math.max(2000,retryAt.current-Date.now()))
    return ()=>clearTimeout(timer)
  },[enabled,turn,isTyping,pollPaused,request,apply,valid,fail])
  const clearConversation=useCallback(async()=>{
    if(!conversation || busy.current)return false
    const id=conversation.id,e=invalidate();busy.current=true;setBusy(true)
    try{await request('write',s=>assistantApi.delete(id,s))
      if(!valid(e,id))return false
      active.current=null;creation.current=null;setConversation(null);setMessages([]);setTurn(null);setError(null);setHistoryOffset(0);setTotalMessages(0)
      if(pending.current?.marker.conversationId===id)remember(null)
      void list();return true
    }catch(cause){if(valid(e,id))fail(cause);return false}
    finally{if(valid(e)){busy.current=false;setBusy(false)}}
  },[conversation,invalidate,request,valid,remember,list,fail])
  const newConversation=useCallback(()=>{
    if(busy.current)return
    invalidate();active.current=null;creation.current=null;setConversation(null);setMessages([]);setTurn(null);setError(null);setReviewed(false);setHistoryOffset(0);setTotalMessages(0)
  },[invalidate])
  const loadMoreMessages=useCallback(async()=>{
    if(!conversation || busy.current)return
    const e=epoch.current,id=conversation.id
    try{const page=await request('read',s=>assistantApi.messages(id,historyOffset,s))
      if(valid(e,id)){setMessages(old=>[...old,...page.items.filter(m=>!old.some(o=>o.id===m.id))].sort((a,b)=>a.sequence_no-b.sequence_no));setTotalMessages(page.total);setHistoryOffset(page.offset+page.items.length)}}
    catch(cause){if(valid(e,id))fail(cause)}
  },[conversation,historyOffset,request,valid,fail])
  const reviewHistory=useCallback(async()=>{if(pending.current)await select(pending.current.marker.conversationId)},[select])
  const stopTracking=useCallback(()=>{
    if(historyReviewed && !busy.current){remember(null);setError('Tracking was stopped after your review. The original request may still commit; no request was resent.')}
  },[historyReviewed,remember])
  const refresh=useCallback(async()=>{if(recovery)await recover();else if(conversation)await select(conversation.id);else await list()},[recovery,recover,conversation,select,list])
  return {messages:messages.map(m=>({id:m.id,role:m.role,content:m.content,createdAt:m.created_at})),isTyping,sendMessage,clearConversation,
    conversations,conversation,turn,error,ambiguous:recovery!==null,recover,resubmit,canResubmit:recovery?.content!==undefined,
    reviewHistory,historyReviewed,stopTracking,refresh,select,newConversation,loadMoreConversations:()=>list(conversations.length),
    hasMoreConversations:conversations.length<totalConversations,loadMoreMessages,hasMoreMessages:historyOffset<totalMessages,lifecycle,
    blocked:recovery!==null || Boolean(turn && ['pending','failed'].includes(turn.status))}
}
