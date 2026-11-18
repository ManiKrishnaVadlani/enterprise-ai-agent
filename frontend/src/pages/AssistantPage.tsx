import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router";
import { ArrowUp, Bot, Check, Clock3, FileText, LoaderCircle, MessageSquarePlus, Plus, Sparkles, UserRound } from "lucide-react";
import { api, ApiError } from "../services/api";
import type { ConversationSummary, SourceReference } from "../types/api";
import { formatRelative } from "../lib/format";
import { Button, Notice } from "../components/ui";

interface ChatMessage { id: string; role: "user"|"assistant"; content: string; createdAt: string; sources?: SourceReference[]; historical?: boolean }
const suggestions=["What are the key points in my documents?","Summarize the most important policy guidance.","What should I know before getting started?"];

export function AssistantPage(){
  const [params,setParams]=useSearchParams(); const conversationId=params.get("conversation");
  const [messages,setMessages]=useState<ChatMessage[]>([]); const [conversations,setConversations]=useState<ConversationSummary[]>([]); const [draft,setDraft]=useState(""); const [loadingHistory,setLoadingHistory]=useState(false); const [sending,setSending]=useState(false); const [error,setError]=useState("");
  const scrollRef=useRef<HTMLDivElement>(null); const inputRef=useRef<HTMLTextAreaElement>(null); const skipNextLoad=useRef<string|null>(null);
  const refreshConversations=useCallback(()=>api.listConversations().then(setConversations).catch(()=>{}),[]);
  useEffect(()=>{void refreshConversations();},[refreshConversations]);
  useEffect(()=>{let active=true;setError("");if(!conversationId){setMessages([]);setLoadingHistory(false);return;}if(skipNextLoad.current===conversationId){skipNextLoad.current=null;return;}setMessages([]);setLoadingHistory(true);api.getConversation(conversationId).then(detail=>{if(active)setMessages(detail.messages.map(message=>({id:message.message_id,role:message.role,content:message.content,createdAt:message.created_at,historical:true})));}).catch(e=>{if(active)setError(e instanceof ApiError&&e.status===404?"This conversation is unavailable or you do not have access to it.":e instanceof Error?e.message:"Could not load conversation.");}).finally(()=>{if(active)setLoadingHistory(false);});return()=>{active=false;};},[conversationId]);
  useEffect(()=>{scrollRef.current?.scrollTo({top:scrollRef.current.scrollHeight,behavior:"smooth"});},[messages,sending]);
  function startNew(){setParams({});setMessages([]);setDraft("");setError("");inputRef.current?.focus();}
  async function send(event?:FormEvent, suggested?:string){event?.preventDefault();const question=(suggested??draft).trim();if(!question||sending)return;setError("");setDraft("");setSending(true);
    const userMessage:ChatMessage={id:crypto.randomUUID(),role:"user",content:question,createdAt:new Date().toISOString()};setMessages(current=>[...current,userMessage]);
    try{let id=conversationId;if(!id){const created=await api.createConversation(question.slice(0,72));id=created.conversation_id;skipNextLoad.current=id;setParams({conversation:id});}
      const result=await api.runAgent({question,conversation_id:id});
      setMessages(current=>[...current,{id:crypto.randomUUID(),role:"assistant",content:result.answer,createdAt:new Date().toISOString(),sources:result.sources}]);void refreshConversations();
    }catch(e){setError(e instanceof Error?e.message:"The assistant could not complete this request.");}finally{setSending(false);inputRef.current?.focus();}}
  function onKeyDown(event:KeyboardEvent<HTMLTextAreaElement>){if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();void send();}}
  return <div className="assistant-page">
    <aside className="conversation-rail"><div className="rail-header"><div className="eyebrow">YOUR WORKSPACE</div><Button variant="secondary" className="new-chat-button" onClick={startNew}><Plus size={16}/> New conversation</Button></div>
      <div className="rail-section-label">RECENT</div><div className="rail-conversation-list">{conversations.length?conversations.slice(0,30).map(item=><button key={item.conversation_id} className={`rail-conversation ${item.conversation_id===conversationId?"rail-conversation-active":""}`} onClick={()=>setParams({conversation:item.conversation_id})}><MessageSquarePlus size={16}/><span>{item.title||"New conversation"}<small><Clock3 size={11}/>{formatRelative(item.updated_at)}</small></span></button>):<div className="rail-empty">Your saved conversations will appear here.</div>}</div>
      <div className="rail-footnote"><span className="secure-mini"><Check size={12}/></span> Conversations are private to your account</div>
    </aside>
    <section className="chat-workspace"><div className="chat-topline"><div className="chat-assistant-id"><span className="assistant-avatar"><Bot size={18}/></span><div><b>Knowledge assistant</b><small><span className="online-indicator"/> Grounded in your documents</small></div></div><Button variant="secondary" className="chat-new-mobile" onClick={startNew}><Plus size={15}/> New</Button></div>
      <div className="chat-messages" ref={scrollRef}>
        {loadingHistory?<div className="chat-loading"><LoaderCircle className="spin" size={19}/> Loading conversation…</div>:messages.length===0?<div className="chat-welcome"><div className="chat-welcome-icon"><Sparkles size={23}/></div><div className="eyebrow">PRIVATE KNOWLEDGE, READY</div><h1>What would you like<br/>to <span>understand?</span></h1><p>Ask a question about your indexed documents. Responses are grounded in retrieved passages and include source references when available.</p><div className="suggestion-grid">{suggestions.map((s,i)=><button key={s} className="suggestion-card" onClick={()=>void send(undefined,s)}><span>0{i+1}</span>{s}<ArrowUp size={15}/></button>)}</div></div>:<div className="message-list">{messages.map((message,index)=><article className={`message-row message-${message.role}`} key={message.id}><div className={`message-avatar ${message.role}`} aria-hidden="true">{message.role==="user"?<UserRound size={17}/>:<Bot size={18}/>}</div><div className="message-body"><div className="message-meta"><b>{message.role==="user"?"You":"Knowledge assistant"}</b><span>{formatRelative(message.createdAt)}</span></div><div className="message-text">{message.content}</div>{message.sources&&message.sources.length>0&&<SourceList sources={message.sources} />}{message.role==="assistant"&&message.historical&&index===messages.length-1&&<div className="historical-note">Source references are shown for new answers; the API stores historical message text only.</div>}</div></article>)}{sending&&<article className="message-row message-assistant"><div className="message-avatar assistant"><Bot size={18}/></div><div className="typing-indicator"><i/><i/><i/></div></article>}</div>}
        {error&&<div className="chat-inline-error"><Notice tone="error">{error}</Notice></div>}
      </div>
      <div className="composer-area"><form className="composer" onSubmit={send}><textarea ref={inputRef} value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={onKeyDown} placeholder="Ask a question about your documents…" rows={1} maxLength={4000} aria-label="Your question" disabled={sending}/><div className="composer-tools"><span>Enter to send · Shift + Enter for a new line</span><div><small>{draft.length}/4000</small><button className="send-button" type="submit" disabled={!draft.trim()||sending} aria-label="Send message"><ArrowUp size={19}/></button></div></div></form><div className="composer-disclaimer"><Sparkles size={12}/> Answers may be incomplete. Verify important details against the cited sources.</div></div>
    </section>
  </div>;
}

function SourceList({sources}:{sources:SourceReference[]}){return <div className="source-list"><div className="source-heading"><FileText size={14}/> SOURCES <span>{sources.length}</span></div><div className="source-cards">{sources.map(source=><div className="source-card" key={`${source.document_id}:${source.chunk_id}`}><div className="source-file-icon"><FileText size={15}/></div><div className="source-copy"><b title={source.filename}>{source.filename}</b><span>{source.page_number?`Page ${source.page_number} · `:""}Passage {source.chunk_id}</span></div><span className="source-score">{Math.round(source.relevance_score*100)}% match</span></div>)}</div></div>;}
