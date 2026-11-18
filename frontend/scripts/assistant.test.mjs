import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { act, createElement } from 'react'
import { createServer } from 'vite'
import { JSDOM } from 'jsdom'

let server,api,ApiClient,ApiError,parseTurn,parseConversation,hook,AuthContext,AssistantPage,dom,previous
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const key='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const stamp='2026-11-16T10:00:00Z'
const conversation={id,title:'Saved conversation',created_at:stamp,updated_at:stamp,last_sequence_no:0,unresolved_turn:null}
const page=items=>({items,total:items.length,offset:0,limit:50})
const message=(role,sequence)=>({id:role==='user'?key:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',conversation_id:id,
  sequence_no:sequence,role,content:role==='user'?'Show my accounts':'Backend-authored answer',created_at:stamp,
  turn:{id:key,status:'completed',attempt_no:1}})
const turn={id:key,conversation_id:id,idempotency_key:key,status:'completed',attempt_no:1,
  user_message:message('user',1),assistant_message:message('assistant',2),created_at:stamp,attempt_started_at:stamp,
  attempt_finished_at:stamp,lease_expires_at:null,context_as_of:stamp,financial_date:'2026-11-16',
  lease_expired:false,can_retry:false,can_abandon:false,error:null}
const json=(body,status=200,headers={})=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store',...headers}})
before(async()=>{
  dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost:5173/',pretendToBeVisual:true})
  const values={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,HTMLElement:dom.window.HTMLElement,
    Element:dom.window.Element,Node:dom.window.Node,getComputedStyle:dom.window.getComputedStyle.bind(dom.window),MutationObserver:dom.window.MutationObserver,sessionStorage:dom.window.sessionStorage,
    requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window),
    IS_REACT_ACT_ENVIRONMENT:true}
  previous=new Map(Object.keys(values).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  for(const [k,v] of Object.entries(values))Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:v})
  server=await createServer({configFile:'vite.config.ts',server:{middlewareMode:true,hmr:{port:24681}},appType:'custom'})
  api=await server.ssrLoadModule('/src/services/api/assistantApi.ts')
  ;({ApiClient,ApiError}=await server.ssrLoadModule('/src/services/api/apiClient.ts'))
  parseTurn=api.parseAssistantTurn;parseConversation=api.parseConversation
  ;({useAssistantConversation:hook}=await server.ssrLoadModule('/src/hooks/useAssistantConversation.ts'))
  ;({AuthContext}=await server.ssrLoadModule('/src/hooks/authContext.ts'))
  ;({AssistantPage}=await server.ssrLoadModule('/src/pages/AssistantPage.tsx'))
})
after(async()=>{if(server)await server.close();dom?.window.close();for(const [k,v] of previous||[])if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]})

test('assistant API uses authenticated no-store requests, header keys and allocation-free paths',async()=>{
  const calls=[]
  const client=new ApiClient('http://localhost:8000',async(url,options)=>{
    calls.push({url:String(url),options})
    const path=new URL(url).pathname
    if(options.method==='DELETE')return new Response(null,{status:204})
    if(path.endsWith('/messages') && options.method==='GET')return json({...page([message('user',1)]),limit:100})
    if(path.endsWith('/conversations') && options.method==='GET')return json(page([conversation]))
    if(path.endsWith('/conversations') || path===`/api/assistant/conversations/${id}`)return json(conversation)
    return json(turn)
  })
  client.setCsrfToken('test-csrf')
  const service=new api.AssistantApi(client)
  await service.list();await service.create(id);await service.get(id);await service.messages(id)
  await service.submit(id,key,'Show my accounts');await service.lookup(key);await service.turn(id,key)
  await service.action(id,key,'retry',1);await service.action(id,key,'abandon',1);await service.delete(id)
  assert.ok(calls.every(({url,options})=>url.includes('/api/assistant/') && options.credentials==='include' && options.cache==='no-store'))
  assert.ok(calls.every(({url})=>!url.includes(key)||url.includes('/turns/')))
  assert.equal(calls.find(c=>c.url.endsWith('/turns/by-key')).options.headers.get('Idempotency-Key'),key)
  assert.ok(calls.filter(c=>c.options.method==='POST'||c.options.method==='DELETE').every(c=>c.options.headers.get('X-CSRF-Token')==='test-csrf'))
  assert.ok(!calls.some(c=>/transactions|contributions|withdrawals/.test(c.url)))
})

test('runtime validators reject unknown fields, broken ownership and malformed lifecycle',()=>{
  assert.equal(parseTurn(turn).status,'completed')
  assert.throws(()=>parseTurn({...turn,raw_provider_output:'unsafe'}))
  assert.throws(()=>parseTurn({...turn,assistant_message:null}))
  assert.throws(()=>parseTurn({...turn,user_message:{...turn.user_message,conversation_id:key}}))
  assert.throws(()=>parseConversation({...conversation,unresolved_turn:turn}))
  assert.throws(()=>parseTurn({...turn,attempt_no:true}))
})

test('assistant 429 retains safe code and Retry-After; provider-disabled stays identifiable',async()=>{
  for(const [status,code] of [[429,'GENERATION_BUSY'],[503,'PROVIDER_DISABLED']]){
    const client=new ApiClient('http://localhost:8000',async()=>json({detail:api.assistantErrorDetails[code],code,issues:[],current_turn:null},status,{'Retry-After':'2'}))
    await assert.rejects(new api.AssistantApi(client).lookup(key),e=>e instanceof ApiError && e.code===code && e.retryAfter===2)
  }
})

async function mounted(fetchImpl,fn){
  const {apiClient}=await server.ssrLoadModule('/src/services/api/apiClient.ts')
  const original=apiClient.fetchImpl
  apiClient.fetchImpl=fetchImpl;apiClient.setCsrfToken('test-csrf');sessionStorage.clear()
  const {createRoot}=await import('react-dom/client')
  const root=createRoot(document.getElementById('root'))
  let current
  function Harness({enabled=true}){current=hook(enabled);return createElement(AssistantPage,{messages:current.messages,isTyping:current.isTyping,onSend:current.sendMessage,onClear:current.clearConversation,controller:current})}
  const auth={user:{id,email:'person@example.test',display_name:'Abc'},sessionIdentity:{generation:1},logout:async()=>{auth.logoutCalls=(auth.logoutCalls||0)+1}}
  try{
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:auth},createElement(Harness))))
    await fn(()=>current,root,auth,Harness)
  }finally{await act(async()=>root.unmount());apiClient.fetchImpl=original;apiClient.clearCsrfToken();sessionStorage.clear()}
}

test('real hook/page loads selected conversation history and deletes only after confirmation',async()=>{
  const calls=[]
  await mounted(async(url,options)=>{
    calls.push({url:String(url),options})
    if(options.method==='DELETE')return new Response(null,{status:204})
    if(new URL(url).pathname.endsWith('/messages'))return json({...page([message('user',1),message('assistant',2)]),limit:100})
    if(new URL(url).pathname===`/api/assistant/conversations/${id}`)return json(conversation)
    return json(page([conversation]))
  },async current=>{
    await act(async()=>current().select(id))
    assert.match(document.body.textContent,/Backend-authored answer/)
    assert.match(document.body.textContent,/Hi Abc|Backend-authored answer/)
    const button=[...document.querySelectorAll('button')].find(b=>b.textContent==='Delete conversation')
    assert.ok(button && !button.disabled)
    await act(async()=>button.click())
    assert.equal(calls.filter(c=>c.options.method==='DELETE').length,0)
    const cancel=[...document.querySelectorAll('button')].find(b=>b.textContent==='Cancel')
    await act(async()=>cancel.click())
    assert.equal(calls.filter(c=>c.options.method==='DELETE').length,0)
    await act(async()=>current().clearConversation())
    assert.equal(calls.filter(c=>c.options.method==='DELETE').length,1)
    assert.equal(current().messages.length,0)
  })
})

test('disabled provider never falls back to a mock answer and remains retryable',async()=>{
  let posts=0
  await mounted(async(url,options)=>{
    if(options.method==='POST' && new URL(url).pathname.endsWith('/messages')){posts++;return json({detail:api.assistantErrorDetails.PROVIDER_DISABLED,code:'PROVIDER_DISABLED',issues:[],current_turn:null},503)}
    if(options.method==='POST')return json(conversation,201)
    return json(page([]))
  },async current=>{
    await act(async()=>current().sendMessage('Show my accounts'))
    assert.match(document.body.textContent,/provider is disabled/)
    assert.equal(current().messages.length,0);assert.equal(current().ambiguous,false)
    await act(async()=>current().sendMessage('Show my accounts'))
    assert.equal(posts,2)
  })
})

test('ambiguous submission recovers by header lookup without resubmitting and drops late session results',async()=>{
  let submitCount=0,lookupCount=0,operationKey
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key')){lookupCount++;return json({...turn,idempotency_key:operationKey})}
    if(options.method==='POST' && path.endsWith('/messages')){submitCount++;operationKey=options.headers.get('Idempotency-Key');throw new TypeError('network')}
    if(options.method==='POST'||path===`/api/assistant/conversations/${id}`)return json(conversation)
    return json(page([]))
  },async current=>{
    await act(async()=>current().sendMessage('Show my accounts'))
    assert.equal(current().ambiguous,true)
    await act(async()=>current().sendMessage('duplicate'))
    assert.equal(submitCount,1)
    await act(async()=>current().recover())
    assert.equal(lookupCount,1);assert.equal(current().ambiguous,false)
    assert.equal(current().messages[1].content,'Backend-authored answer')
  })
})

function lifecycleTurn(state,options={}){
  return {...turn,status:state,assistant_message:state==='completed'?turn.assistant_message:null,
    user_message:{...turn.user_message,turn:{id:key,status:state,attempt_no:options.attempt_no||1}},
    attempt_finished_at:state==='pending'?null:stamp,lease_expires_at:state==='pending'?'2026-11-16T10:01:30Z':null,
    lease_expired:false,can_retry:state==='failed',can_abandon:state==='failed',
    error:state==='failed'?{code:'PROVIDER_UNAVAILABLE',message:api.assistantTurnErrorDetails.PROVIDER_UNAVAILABLE}:null,...options}
}

test('interrupted and failed lifecycle states expose explicit retry and abandon without a new submission',async()=>{
  let state=lifecycleTurn('pending',{lease_expired:true,can_retry:true,can_abandon:true,
    error:{code:'GENERATION_INTERRUPTED',message:api.assistantTurnErrorDetails.GENERATION_INTERRUPTED}})
  const actions=[]
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/retry')||path.endsWith('/abandon')){
      actions.push({path,body:JSON.parse(options.body)})
      state=path.endsWith('/retry')?lifecycleTurn('failed',{attempt_no:2}):lifecycleTurn('abandoned',{attempt_no:2})
      return json(state)
    }
    if(path.endsWith('/messages'))return json({...page([state.user_message]),limit:100})
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,last_sequence_no:1,unresolved_turn:state})
    return json(page([conversation]))
  },async current=>{
    await act(async()=>current().select(id))
    assert.match(document.body.textContent,/interrupted/)
    assert.ok([...document.querySelectorAll('button')].some(b=>b.textContent==='Retry turn'))
    await act(async()=>current().lifecycle('retry'))
    assert.equal(current().turn.status,'failed')
    assert.equal(actions[0].body.expected_attempt_no,1)
    await act(async()=>current().lifecycle('abandon'))
    assert.equal(current().turn.status,'abandoned');assert.equal(current().blocked,false)
    assert.equal(actions[1].body.expected_attempt_no,2)
    assert.equal(actions.length,2)
  })
})

test('a previous authenticated session cannot publish a late assistant response',async()=>{
  let resolveSubmission, entered
  const started=new Promise(resolve=>{entered=resolve})
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(options.method==='POST' && path.endsWith('/messages')){
      entered();return new Promise(resolve=>{resolveSubmission=resolve})
    }
    if(options.method==='POST')return json(conversation)
    return json(page([]))
  },async(current,root,auth,Harness)=>{
    let pending
    await act(async()=>{pending=current().sendMessage('Show my accounts');await started})
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:{...auth,
      user:{id:key,email:'other@example.test',display_name:'Other'},sessionIdentity:{generation:2}}},createElement(Harness))))
    await act(async()=>{resolveSubmission(json(turn));await pending})
    assert.equal(current().messages.length,0);assert.equal(current().isTyping,false)
    assert.doesNotMatch(document.body.textContent,/Backend-authored answer/)
  })
})

test('appending a new reply does not advance the paginated history cursor past unloaded messages',async()=>{
  const offsets=[]
  const row=n=>({...message(n%2?'user':'assistant',n),id:`dddddddd-dddd-4ddd-8ddd-${n.toString(16).padStart(12,'0')}`,turn:null})
  const completed={...turn,user_message:{...row(103),turn:turn.user_message.turn},assistant_message:{...row(104),turn:turn.assistant_message.turn}}
  await mounted(async(url,options)=>{
    const parsed=new URL(url)
    if(parsed.pathname.endsWith('/messages') && options.method==='POST')return json({...completed,idempotency_key:options.headers.get('Idempotency-Key')},201)
    if(parsed.pathname.endsWith('/messages')){
      const offset=Number(parsed.searchParams.get('offset'));offsets.push(offset)
      return json({items:offset===0?Array.from({length:100},(_,i)=>row(i+1)):[101,102,103,104].map(row),
        total:offset===0?102:104,offset,limit:100})
    }
    if(parsed.pathname===`/api/assistant/conversations/${id}`)return json(conversation)
    return json(page([conversation]))
  },async current=>{
    await act(async()=>current().select(id))
    await act(async()=>current().sendMessage('Show recorded accounts'))
    await act(async()=>current().loadMoreMessages())
    assert.deepEqual(offsets,[0,100])
    assert.equal(current().messages.length,104)
    assert.equal(current().hasMoreMessages,false)
  })
})

const failure=(code,status,current_turn=null)=>json({detail:api.assistantErrorDetails[code],code,issues:[],current_turn},status)

test('strict lifecycle rejects coercion, calendar, metadata, context and action contradictions',()=>{
  for(const bad of [
    {...turn,status:['completed']},{...turn,status:{}},{...turn,created_at:'2026-02-30T10:00:00Z'},
    {...turn,attempt_started_at:'2026-11-16T25:00:00Z'},{...turn,context_as_of:null},
    {...turn,financial_date:null},{...turn,financial_date:'2026-11-17'},{...turn,can_retry:true},
    {...turn,can_abandon:true},{...turn,lease_expires_at:stamp},{...turn,attempt_finished_at:null},
    {...turn,user_message:{...turn.user_message,turn:null}},
    {...turn,user_message:{...turn.user_message,turn:{id:key,status:'pending',attempt_no:1}}},
    {...turn,created_at:'2026-11-16T10:00:00.000002Z',attempt_started_at:'2026-11-16T10:00:00.000001Z'},
  ])assert.throws(()=>parseTurn(bad))
})

test('request not received can be explicitly resent with the SAME key and normalized payload after repeated 404s',async()=>{
  const posts=[];let lookups=0
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key')){lookups++;return failure('TURN_NOT_FOUND',404)}
    if(options.method==='POST'&&path.endsWith('/messages')){
      posts.push({key:options.headers.get('Idempotency-Key'),body:options.body})
      if(posts.length===1)throw new TypeError('not received')
      return json({...turn,idempotency_key:posts[0].key,user_message:{...turn.user_message,content:JSON.parse(options.body).content}},201)
    }
    if(options.method==='POST'||path===`/api/assistant/conversations/${id}`)return json(conversation)
    if(path.endsWith('/messages'))return json({...page([]),limit:100})
    return json(page([conversation]))
  },async current=>{
    await act(async()=>current().sendMessage('  Show\r\naccounts  '))
    await act(async()=>current().recover());await act(async()=>current().recover())
    assert.equal(lookups,2);assert.equal(posts.length,1);assert.equal(current().canResubmit,true)
    await act(async()=>current().select(id)) // Saved history stays accessible.
    assert.equal(current().ambiguous,true)
    await act(async()=>current().resubmit())
    assert.equal(posts.length,2);assert.deepEqual(posts[0],posts[1])
    assert.equal(JSON.parse(posts[0].body).content,'Show\naccounts')
    assert.equal(current().ambiguous,false);assert.equal(current().turn.status,'completed')
  })
})

test('recovery 401 invokes the established authentication-expiry path without erasing the key',async()=>{
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key'))return failure('AUTHENTICATION_REQUIRED',401)
    if(options.method==='POST'&&path.endsWith('/messages'))throw new TypeError('uncertain')
    if(options.method==='POST')return json(conversation)
    return json(page([]))
  },async(current,root,auth)=>{
    await act(async()=>current().sendMessage('Show accounts'))
    await act(async()=>current().recover())
    assert.equal(auth.logoutCalls,1)
    assert.ok(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`))
  })
})

test('reload recovery has no invented payload and permits explicit history reconciliation',async()=>{
  let posts=0
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(options.method==='POST')posts++
    if(path.endsWith('/turns/by-key'))return failure('TURN_NOT_FOUND',404)
    if(path===`/api/assistant/conversations/${id}`)return json(conversation)
    if(path.endsWith('/messages'))return json({...page([message('user',1)]),limit:100})
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    sessionStorage.setItem(`vibewealth.assistant.operation.v1:${id}`,JSON.stringify({version:1,userId:id,conversationId:id,key}))
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:{...auth,sessionIdentity:{generation:2}}},createElement(Harness))))
    assert.equal(current().ambiguous,true);assert.equal(current().canResubmit,false)
    await act(async()=>current().recover());await act(async()=>current().reviewHistory())
    assert.equal(current().historyReviewed,true);assert.equal(current().messages.length,1)
    assert.equal(posts,0);assert.equal(current().ambiguous,true)
    await act(async()=>current().stopTracking())
    assert.equal(posts,0);assert.equal(current().ambiguous,false)
    assert.match(document.body.textContent,/may still commit/)
  })
})

test('pre-reservation 409 clears only its refused operation; post-reservation 409 applies current_turn',async()=>{
  for(const code of ['TURN_LIMIT_REACHED','ATTEMPT_CONFLICT']){
    await mounted(async(url,options)=>{
      const path=new URL(url).pathname
      if(options.method==='POST'&&path.endsWith('/messages'))return failure(code,409,
        code==='ATTEMPT_CONFLICT'?{...turn,idempotency_key:options.headers.get('Idempotency-Key')}:null)
      if(options.method==='POST')return json(conversation)
      return json(page([]))
    },async current=>{
      await act(async()=>current().sendMessage('Show my accounts'))
      assert.equal(current().ambiguous,false)
      assert.equal(current().messages.length,code==='ATTEMPT_CONFLICT'?2:0)
      if(code==='ATTEMPT_CONFLICT')assert.equal(current().turn.status,'completed')
    })
  }
  assert.throws(()=>api.parseAssistantError({detail:api.assistantErrorDetails.ATTEMPT_CONFLICT,code:'ATTEMPT_CONFLICT',issues:[],current_turn:{...turn,status:[]}},409))
})

test('post-reservation conflict without current_turn RETAINS its key for lookup',async()=>{
  await mounted(async(url,options)=>{
    if(options.method==='POST'&&new URL(url).pathname.endsWith('/messages'))return failure('ATTEMPT_CONFLICT',409)
    if(options.method==='POST')return json(conversation)
    return json(page([]))
  },async current=>{
    await act(async()=>current().sendMessage('Show my accounts'))
    assert.equal(current().ambiguous,true);assert.equal(current().canResubmit,true)
    assert.ok(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`))
  })
})

test('a pending poll released AFTER DELETE cannot restore messages, turn or submission lock',async()=>{
  const pending=lifecycleTurn('pending');let pollCallback,resolvePoll,signal,entered
  const started=new Promise(r=>{entered=r});let submissions=0
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(options.method==='DELETE')return new Response(null,{status:204})
    if(path.includes('/turns/')){signal=options.signal;entered();return new Promise(r=>{resolvePoll=r})}
    if(options.method==='POST'&&path.endsWith('/messages')){submissions++;return json({...turn,idempotency_key:options.headers.get('Idempotency-Key')},201)}
    if(options.method==='POST')return json(conversation)
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,last_sequence_no:1,unresolved_turn:pending})
    if(path.endsWith('/messages'))return json({...page([pending.user_message]),limit:100})
    return json(page([conversation]))
  },async current=>{
    const set=globalThis.setTimeout,clear=globalThis.clearTimeout
    globalThis.setTimeout=(fn,delay,...args)=>delay===2000?(pollCallback=fn,987654):set(fn,delay,...args)
    globalThis.clearTimeout=timer=>{if(timer!==987654)clear(timer)}
    try{
      await act(async()=>current().select(id));assert.ok(pollCallback)
      await act(async()=>{pollCallback();await started})
      await act(async()=>current().clearConversation());assert.ok(signal.aborted)
      await act(async()=>resolvePoll(json(pending))) // Transport deliberately ignores abort.
      assert.equal(current().conversation,null);assert.equal(current().turn,null)
      assert.equal(current().messages.length,0);assert.equal(current().blocked,false)
      await act(async()=>current().sendMessage('Show my accounts'))
      assert.equal(submissions,1);assert.equal(current().turn.status,'completed')
    }finally{globalThis.setTimeout=set;globalThis.clearTimeout=clear}
  })
})

test('session teardown aborts a mutation but retains owner-scoped recovery metadata',async()=>{
  let resolvePost,signal,entered,operationKey
  const started=new Promise(r=>{entered=r})
  await mounted(async(url,options)=>{
    if(options.method==='POST'&&new URL(url).pathname.endsWith('/messages')){
      signal=options.signal;operationKey=options.headers.get('Idempotency-Key');entered();return new Promise(r=>{resolvePost=r})
    }
    if(options.method==='POST')return json(conversation)
    return json(page([]))
  },async(current,root,auth,Harness)=>{
    let pending
    await act(async()=>{pending=current().sendMessage('Show my accounts');await started})
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:{...auth,user:{id:key,email:'other@example.test',display_name:'Other'},sessionIdentity:{generation:2}}},createElement(Harness))))
    assert.equal(signal.aborted,true)
    assert.equal(JSON.parse(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`)).key,operationKey)
    await act(async()=>{resolvePost(json({...turn,idempotency_key:operationKey}));await pending})
    assert.equal(current().messages.length,0);assert.equal(current().isTyping,false)
  })
})

test('same-key resubmission returns to the original conversation after browsing other saved history',async()=>{
  let operationKey
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(options.method==='POST'&&path.endsWith('/messages')){
      if(!operationKey){operationKey=options.headers.get('Idempotency-Key');throw new TypeError('uncertain')}
      return json({...turn,idempotency_key:operationKey},201)
    }
    if(options.method==='POST'||path===`/api/assistant/conversations/${id}`)return json(conversation)
    if(path===`/api/assistant/conversations/${key}`)return json({...conversation,id:key,title:'Other history'})
    if(path.endsWith('/messages'))return json({...page([]),limit:100})
    return json(page([conversation,{...conversation,id:key,title:'Other history'}]))
  },async current=>{
    await act(async()=>current().sendMessage('Show my accounts'))
    await act(async()=>current().select(key))
    assert.equal(current().conversation.id,key)
    await act(async()=>current().resubmit())
    assert.equal(current().conversation.id,id);assert.equal(current().turn.conversation_id,id)
    assert.equal(current().ambiguous,false)
  })
})


const resendRefusals=[
  ['RATE_LIMITED',429],['CSRF_FAILED',403],['TURN_LIMIT_REACHED',409],
  ['PROVIDER_DISABLED',503],['INVALID_REQUEST',422],['ATTEMPT_CONFLICT',409],
]
for(const [code,status] of resendRefusals){
  test(`ambiguous resend preserves key/payload after ${code} and reconciles the original by lookup`,async()=>{
    const posts=[];let rejectOriginal,resolveResend,originalEntered,resendEntered,committed=false,lookups=0
    const originalStarted=new Promise(resolve=>{originalEntered=resolve})
    const resendStarted=new Promise(resolve=>{resendEntered=resolve})
    const payload='Show\naccounts'
    const accepted=()=>({...turn,idempotency_key:posts[0].key,
      user_message:{...turn.user_message,content:payload}})
    await mounted(async(url,options)=>{
      const path=new URL(url).pathname
      if(path.endsWith('/turns/by-key')){
        lookups++;assert.equal(options.headers.get('Idempotency-Key'),posts[0].key)
        return committed?json(accepted()):failure('TURN_NOT_FOUND',404)
      }
      if(options.method==='POST'&&path.endsWith('/messages')){
        posts.push({key:options.headers.get('Idempotency-Key'),body:options.body})
        if(posts.length===1){originalEntered();return new Promise((_,reject)=>{rejectOriginal=reject})}
        if(posts.length===2){resendEntered();return new Promise(resolve=>{resolveResend=resolve})}
        assert.fail('Unexpected automatic or replacement-key submission')
      }
      if(options.method==='POST'||path===`/api/assistant/conversations/${id}`)return json(conversation)
      if(path.endsWith('/messages'))return json({...page(committed?[accepted().user_message,accepted().assistant_message]:[]),limit:100})
      return json(page([conversation]))
    },async current=>{
      let initial,resend
      await act(async()=>{initial=current().sendMessage('  Show\r\naccounts  ');await originalStarted})
      assert.equal(current().isTyping,true)
      await act(async()=>{rejectOriginal(new TypeError('Original response lost'));await initial})
      const marker=sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`)
      assert.equal(JSON.parse(marker).key,posts[0].key)
      assert.equal(JSON.parse(posts[0].body).content,payload)
      await act(async()=>{resend=current().resubmit();await resendStarted})
      assert.equal(current().isTyping,true)
      assert.deepEqual(posts[1],posts[0])
      await act(async()=>{resolveResend(failure(code,status));await resend})
      assert.equal(current().isTyping,false)
      assert.equal(current().ambiguous,true);assert.equal(current().canResubmit,true)
      assert.equal(current().blocked,true)
      assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
      await act(async()=>{assert.equal(await current().sendMessage('A different request'),false)})
      await act(async()=>current().recover());await act(async()=>current().recover())
      assert.equal(lookups,2);assert.equal(current().ambiguous,true)
      assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
      await act(async()=>current().select(id)) // Navigation/history remain usable.
      assert.equal(current().conversation.id,id);assert.equal(current().ambiguous,true)
      committed=true // The original server-side operation completes, without another POST.
      await act(async()=>current().recover());await act(async()=>current().recover())
      assert.equal(current().ambiguous,false);assert.equal(current().isTyping,false)
      assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),null)
      assert.equal(current().turn.idempotency_key,posts[0].key)
      assert.equal(current().messages.filter(m=>m.role==='user').length,1)
      assert.equal(current().messages.filter(m=>m.role==='assistant').length,1)
      assert.equal(new Set(current().messages.map(m=>m.id)).size,2)
      assert.equal(posts.length,2)
    })
  })
}

for(const [code,status] of resendRefusals.filter(([code])=>code!=='ATTEMPT_CONFLICT')){
  test(`initial authoritative ${code} still clears its never-ambiguous operation`,async()=>{
    let posts=0
    await mounted(async(url,options)=>{
      if(options.method==='POST'&&new URL(url).pathname.endsWith('/messages')){posts++;return failure(code,status)}
      if(options.method==='POST')return json(conversation)
      return json(page([]))
    },async current=>{
      await act(async()=>current().sendMessage('Show my accounts'))
      assert.equal(current().ambiguous,false);assert.equal(current().canResubmit,false)
      assert.equal(current().isTyping,false);assert.equal(current().messages.length,0)
      assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),null)
      assert.equal(posts,1)
    })
  })
}

test('refused ambiguous resend clears only after explicit history reconciliation, never from repeated 404',async()=>{
  const posts=[]
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key'))return failure('TURN_NOT_FOUND',404)
    if(options.method==='POST'&&path.endsWith('/messages')){
      posts.push({key:options.headers.get('Idempotency-Key'),body:options.body})
      if(posts.length===1)throw new TypeError('Uncertain original transmission')
      return failure('RATE_LIMITED',429)
    }
    if(options.method==='POST'||path===`/api/assistant/conversations/${id}`)return json(conversation)
    if(path.endsWith('/messages'))return json({...page([]),limit:100})
    return json(page([conversation]))
  },async current=>{
    await act(async()=>current().sendMessage('Show my accounts'))
    await act(async()=>current().resubmit())
    const marker=sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`)
    assert.deepEqual(posts[1],posts[0]);assert.ok(marker)
    await act(async()=>current().recover());await act(async()=>current().recover())
    await act(async()=>current().stopTracking()) // No history review: no acknowledgement.
    assert.equal(current().ambiguous,true)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
    await act(async()=>current().reviewHistory())
    assert.equal(current().historyReviewed,true);assert.equal(current().ambiguous,true)
    await act(async()=>current().stopTracking()) // Existing explicit user reconciliation.
    assert.equal(current().ambiguous,false)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),null)
    assert.match(document.body.textContent,/may still commit/)
    assert.equal(posts.length,2)
  })
})


function historyRow(conversationId,n){
  return {...message(n%2?'user':'assistant',n),conversation_id:conversationId,
    id:`dddddddd-dddd-4ddd-8ddd-${n.toString(16).padStart(12,'0')}`,content:`History ${n}`,turn:null}
}
function recoveredHistoryTurn(n=1,state='completed'){
  const lifecycle=lifecycleTurn(state)
  return {...lifecycle,user_message:{...historyRow(id,n),turn:lifecycle.user_message.turn},
    assistant_message:state==='completed'?{...historyRow(id,n+1),turn:lifecycle.assistant_message.turn}:null}
}
async function restoreOperation(root,auth,Harness){
  sessionStorage.setItem(`vibewealth.assistant.operation.v1:${id}`,JSON.stringify({version:1,userId:id,conversationId:id,key}))
  await act(async()=>root.render(createElement(AuthContext.Provider,
    {value:{...auth,sessionIdentity:{generation:2}}},createElement(Harness))))
}

test('reload recovery hydrates metadata and initial history, merges an included turn once, and rebuilds pagination',async()=>{
  const recovered=recoveredHistoryTurn(3),calls=[]
  await mounted(async(url,options)=>{
    const parsed=new URL(url);calls.push({path:parsed.pathname,offset:parsed.searchParams.get('offset'),method:options.method})
    if(parsed.pathname.endsWith('/turns/by-key'))return json(recovered)
    if(parsed.pathname===`/api/assistant/conversations/${id}`)return json({...conversation,title:'Recovered A',last_sequence_no:4})
    if(parsed.pathname.endsWith('/messages'))return json({items:[historyRow(id,1),historyRow(id,2),recovered.user_message,recovered.assistant_message],total:4,offset:0,limit:100})
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    assert.equal(current().ambiguous,true)
    await act(async()=>current().recover())
    assert.equal(current().conversation.title,'Recovered A')
    assert.deepEqual(current().messages.map(m=>m.content),['History 1','History 2','History 3','History 4'])
    assert.equal(new Set(current().messages.map(m=>m.id)).size,4)
    assert.equal(current().hasMoreMessages,false);assert.equal(current().ambiguous,false)
    assert.ok(calls.some(c=>c.path===`/api/assistant/conversations/${id}/messages`&&c.offset==='0'))
    assert.ok(!calls.some(c=>c.method==='POST'))
  })
})

test('recovery from B rebuilds A cursor from paged rows even when the recovered turn lies beyond the first page',async()=>{
  const recovered=recoveredHistoryTurn(103),pages=[]
  const other={...conversation,id:key,title:'B',last_sequence_no:150}
  await mounted(async url=>{
    const parsed=new URL(url),path=parsed.pathname
    if(path.endsWith('/turns/by-key'))return json(recovered)
    if(path===`/api/assistant/conversations/${key}`)return json(other)
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,title:'A',last_sequence_no:104})
    if(path.endsWith('/messages')){
      const offset=Number(parsed.searchParams.get('offset')),otherPage=path.includes(key)
      pages.push([otherPage?'B':'A',offset])
      const total=otherPage?150:104,conversationId=otherPage?key:id
      return json({items:Array.from({length:Math.min(100,total-offset)},(_,i)=>historyRow(conversationId,offset+i+1)),total,offset,limit:100})
    }
    return json(page([conversation,other]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    await act(async()=>current().select(key))
    assert.equal(current().messages.length,100);assert.equal(current().hasMoreMessages,true)
    await act(async()=>current().recover())
    assert.equal(current().conversation.id,id)
    assert.equal(current().messages.length,102);assert.equal(current().hasMoreMessages,true)
    await act(async()=>current().loadMoreMessages())
    assert.deepEqual(pages,[['B',0],['A',0],['A',100]])
    assert.equal(current().messages.length,104);assert.equal(current().hasMoreMessages,false)
    assert.equal(new Set(current().messages.map(m=>m.id)).size,104)
    assert.deepEqual(current().messages.map(m=>m.content),Array.from({length:104},(_,i)=>`History ${i+1}`))
  })
})

test('recovered pending turn merges only its persisted user message and exposes no fabricated reply',async()=>{
  const pending=recoveredHistoryTurn(3,'pending')
  await mounted(async url=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key'))return json(pending)
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,last_sequence_no:3,unresolved_turn:pending})
    if(path.endsWith('/messages'))return json({items:[historyRow(id,1),historyRow(id,2),pending.user_message],total:3,offset:0,limit:100})
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    await act(async()=>current().recover())
    assert.equal(current().turn.status,'pending');assert.equal(current().turn.assistant_message,null)
    assert.equal(current().messages.length,3)
    assert.equal(current().messages.filter(m=>m.id===pending.user_message.id).length,1)
    assert.equal(current().messages.filter(m=>m.role==='assistant').length,1) // Existing history reply only.
    assert.equal(current().hasMoreMessages,false);assert.equal(current().blocked,true)
    assert.equal(current().ambiguous,false)
  })
})

test('a delayed B history page ignoring abort cannot overwrite recovered A history or pagination',async()=>{
  const recovered=recoveredHistoryTurn(3),pages=[];let resolveB,entered,signal
  const started=new Promise(resolve=>{entered=resolve})
  await mounted(async(url,options)=>{
    const parsed=new URL(url),path=parsed.pathname
    if(path.endsWith('/turns/by-key'))return json(recovered)
    if(path===`/api/assistant/conversations/${key}`)return json({...conversation,id:key,title:'B',last_sequence_no:150})
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,title:'A',last_sequence_no:4})
    if(path.endsWith('/messages')){
      const offset=Number(parsed.searchParams.get('offset'));pages.push([path,offset])
      if(path.includes(key)){
        if(offset===100){signal=options.signal;entered();return new Promise(resolve=>{resolveB=resolve})}
        return json({items:Array.from({length:100},(_,i)=>historyRow(key,i+1)),total:150,offset:0,limit:100})
      }
      return json({items:[historyRow(id,1),historyRow(id,2),recovered.user_message,recovered.assistant_message],total:4,offset:0,limit:100})
    }
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    await act(async()=>current().select(key))
    let outstanding
    await act(async()=>{outstanding=current().loadMoreMessages();await started})
    await act(async()=>current().recover())
    assert.equal(signal.aborted,true)
    await act(async()=>{resolveB(json({items:Array.from({length:50},(_,i)=>historyRow(key,i+101)),total:150,offset:100,limit:100}));await outstanding})
    assert.equal(current().conversation.id,id);assert.equal(current().messages.length,4)
    assert.equal(current().messages.at(-1).content,'History 4');assert.equal(current().hasMoreMessages,false)
    assert.equal(current().turn.id,recovered.id)
    assert.deepEqual(pages.map(([,offset])=>offset),[0,100,0])
  })
})

test('an earlier recovery history response cannot replace a newer session recovery generation',async()=>{
  const recovered=recoveredHistoryTurn(3);let historyCalls=0,resolveEarlier,entered,signal
  const started=new Promise(resolve=>{entered=resolve})
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(path.endsWith('/turns/by-key'))return json(recovered)
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,last_sequence_no:4})
    if(path.endsWith('/messages')){
      historyCalls++
      if(historyCalls===1){signal=options.signal;entered();return new Promise(resolve=>{resolveEarlier=resolve})}
      return json({items:[historyRow(id,1),historyRow(id,2),recovered.user_message,recovered.assistant_message],total:4,offset:0,limit:100})
    }
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    let outstanding
    await act(async()=>{outstanding=current().recover();await started})
    await act(async()=>root.render(createElement(AuthContext.Provider,
      {value:{...auth,sessionIdentity:{generation:3}}},createElement(Harness))))
    await act(async()=>current().recover())
    assert.equal(signal.aborted,true);assert.equal(current().messages.length,4)
    await act(async()=>{resolveEarlier(json({items:Array.from({length:100},(_,i)=>historyRow(id,i+1)),total:200,offset:0,limit:100}));await outstanding})
    assert.equal(current().messages.length,4);assert.equal(current().hasMoreMessages,false)
    assert.equal(current().isTyping,false);assert.equal(current().ambiguous,false)
  })
})

test('lookup 404 preserves B history and its cursor while keeping the recovery pointer',async()=>{
  const pages=[]
  await mounted(async url=>{
    const parsed=new URL(url),path=parsed.pathname
    if(path.endsWith('/turns/by-key'))return failure('TURN_NOT_FOUND',404)
    if(path===`/api/assistant/conversations/${key}`)return json({...conversation,id:key,title:'B',last_sequence_no:102})
    if(path.endsWith('/messages')){
      const offset=Number(parsed.searchParams.get('offset'));pages.push([path,offset])
      return json({items:Array.from({length:Math.min(100,102-offset)},(_,i)=>historyRow(key,offset+i+1)),total:102,offset,limit:100})
    }
    return json(page([conversation]))
  },async(current,root,auth,Harness)=>{
    await restoreOperation(root,auth,Harness)
    await act(async()=>current().select(key))
    const marker=sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`)
    await act(async()=>current().recover());await act(async()=>current().recover())
    assert.equal(current().conversation.id,key);assert.equal(current().messages.length,100)
    assert.equal(current().hasMoreMessages,true);assert.equal(current().ambiguous,true)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
    await act(async()=>current().loadMoreMessages())
    assert.equal(current().messages.length,102);assert.equal(current().hasMoreMessages,false)
    assert.deepEqual(pages.map(([,offset])=>offset),[0,100])
    assert.ok(pages.every(([path])=>path.includes(`/conversations/${key}/messages`)))
  })
})


test('late original HTTP success after a refused same-key resend is ignored until explicit lookup reconciliation',async()=>{
  const posts=[],lookups=[]
  let resolveOriginal,resolveResend,resolveLookup,originalEntered,resendEntered,lookupEntered
  let originalSignal,committed=false,originalSettled=false
  const originalStarted=new Promise(resolve=>{originalEntered=resolve})
  const resendStarted=new Promise(resolve=>{resendEntered=resolve})
  const lookupStarted=new Promise(resolve=>{lookupEntered=resolve})
  const payload='Show\naccounts'
  const other={...conversation,id:key,title:'Other conversation B',last_sequence_no:102}
  const originalTurn=()=>{
    const value=recoveredHistoryTurn(3)
    return {...value,idempotency_key:posts[0].key,user_message:{...value.user_message,content:payload}}
  }
  const otherRows=Array.from({length:100},(_,i)=>({...historyRow(key,i+1),content:`B history ${i+1}`}))
  await mounted(async(url,options)=>{
    const path=new URL(url).pathname
    if(options.method==='POST'&&path.endsWith('/messages')){
      posts.push({key:options.headers.get('Idempotency-Key'),body:options.body})
      if(posts.length===1){
        originalSignal=options.signal
        originalEntered()
        // Deliberately do NOT reject or settle when signal is aborted. This is
        // the original HTTP promise, still pending when its resend is refused.
        return new Promise(resolve=>{resolveOriginal=resolve})
      }
      if(posts.length===2){resendEntered();return new Promise(resolve=>{resolveResend=resolve})}
      assert.fail('No automatic third POST or replacement-key submission is allowed')
    }
    if(path.endsWith('/turns/by-key')){
      lookups.push(options.headers.get('Idempotency-Key'))
      lookupEntered();return new Promise(resolve=>{resolveLookup=resolve})
    }
    if(path===`/api/assistant/conversations/${key}`)return json(other)
    if(path===`/api/assistant/conversations/${id}`)return json({...conversation,title:'Original conversation A',last_sequence_no:committed?4:2})
    if(path.endsWith('/messages')){
      if(path.includes(`/conversations/${key}/`))return json({items:otherRows,total:102,offset:0,limit:100})
      const items=[historyRow(id,1),historyRow(id,2)]
      if(committed)items.push(originalTurn().user_message,originalTurn().assistant_message)
      return json({items,total:items.length,offset:0,limit:100})
    }
    return json(page([conversation,other]))
  },async(current,root,auth,Harness)=>{
    await act(async()=>current().select(id))
    let initial,resend,lookup
    await act(async()=>{
      initial=current().sendMessage('  Show\r\naccounts  ')
      void initial.then(()=>{originalSettled=true})
      await originalStarted
    })
    const marker=sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`)
    assert.equal(JSON.parse(marker).key,posts[0].key)
    assert.equal(JSON.parse(posts[0].body).content,payload)
    assert.equal(originalSettled,false)
    // The same hook stays mounted. Disabling its view performs the real
    // navigation teardown while retaining the exact payload in memory.
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:auth},createElement(Harness,{enabled:false}))))
    assert.equal(originalSignal.aborted,true);assert.equal(originalSettled,false)
    assert.equal(current().isTyping,false);assert.equal(current().ambiguous,true)
    assert.equal(current().canResubmit,true)
    await act(async()=>root.render(createElement(AuthContext.Provider,{value:auth},createElement(Harness,{enabled:true}))))
    await act(async()=>{resend=current().resubmit();await resendStarted})
    assert.deepEqual(posts[1],posts[0]);assert.equal(originalSettled,false)
    await act(async()=>{resolveResend(failure('RATE_LIMITED',429));await resend})
    assert.equal(current().isTyping,false);assert.equal(current().ambiguous,true)
    assert.equal(current().canResubmit,true);assert.equal(originalSettled,false)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
    await act(async()=>current().select(key))
    const before={conversation:current().conversation,messages:current().messages,turn:current().turn,
      hasMoreMessages:current().hasMoreMessages,error:current().error}
    assert.equal(before.conversation.id,key);assert.equal(before.messages.length,100)
    assert.equal(before.hasMoreMessages,true);assert.equal(before.turn,null)
    committed=true
    await act(async()=>{resolveOriginal(json(originalTurn(),201));assert.equal(await initial,false)})
    assert.equal(originalSettled,true) // Actual original HTTP success was delivered.
    assert.deepEqual({conversation:current().conversation,messages:current().messages,turn:current().turn,
      hasMoreMessages:current().hasMoreMessages,error:current().error},before)
    assert.equal(current().isTyping,false);assert.equal(current().ambiguous,true)
    assert.equal(current().canResubmit,true);assert.equal(current().blocked,true)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
    assert.equal(posts.length,2);assert.equal(lookups.length,0)
    await act(async()=>{assert.equal(await current().sendMessage('Replacement'),false)})
    await act(async()=>{lookup=current().recover();await lookupStarted})
    assert.deepEqual(lookups,[posts[0].key]);assert.equal(posts.length,2)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),marker)
    await act(async()=>{resolveLookup(json(originalTurn()));await lookup})
    assert.equal(current().conversation.id,id);assert.equal(current().turn.idempotency_key,posts[0].key)
    const expected=[historyRow(id,1),historyRow(id,2),originalTurn().user_message,originalTurn().assistant_message]
    assert.deepEqual(current().messages.map(m=>m.id),expected.map(m=>m.id)) // Ascending persisted sequence.
    assert.deepEqual(current().messages.map(m=>m.content),['History 1','History 2',payload,'History 4'])
    assert.equal(current().messages.filter(m=>m.id===originalTurn().user_message.id).length,1)
    assert.equal(current().messages.filter(m=>m.id===originalTurn().assistant_message.id).length,1)
    assert.equal(new Set(current().messages.map(m=>m.id)).size,4)
    assert.equal(current().ambiguous,false);assert.equal(current().canResubmit,false)
    assert.equal(sessionStorage.getItem(`vibewealth.assistant.operation.v1:${id}`),null)
    assert.equal(current().isTyping,false);assert.equal(current().hasMoreMessages,false)
    await act(async()=>current().recover()) // Already reconciled: no additional request.
    assert.equal(posts.length,2);assert.equal(lookups.length,1)
  })
})
