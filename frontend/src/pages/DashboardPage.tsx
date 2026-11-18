import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowRight, Bot, Boxes, FileStack, MessageSquareText, Plus, Sparkles } from "lucide-react";
import { Link } from "react-router";
import { api } from "../services/api";
import type { ConversationSummary, DocumentSummary } from "../types/api";
import { formatDate, formatRelative } from "../lib/format";
import { EmptyState, LoadingBlock, Notice, PageHeading } from "../components/ui";

export function DashboardPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]); const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [ready, setReady] = useState(false);
  useEffect(() => { let active = true; Promise.all([api.listDocuments(), api.listConversations(), api.getReadiness()]).then(([d,c]) => { if(active){setDocs(d.documents);setConversations(c);setReady(true);} }).catch(e=>{if(active)setError(e instanceof Error?e.message:"Could not load workspace data.");}).finally(()=>{if(active)setLoading(false);}); return ()=>{active=false;}; }, []);
  const chunks = docs.reduce((sum, doc) => sum + doc.chunk_count, 0);
  return <>
    <PageHeading eyebrow="WORKSPACE OVERVIEW" title="Good to have you back." description="A clear view of the knowledge and conversations in your workspace." action={<Link className="button button-primary" to="/documents"><Plus size={17}/> Add documents</Link>} />
    {error && <Notice tone="error">{error}</Notice>}
    <section className="welcome-banner"><div className="welcome-copy"><div className="welcome-tag"><Sparkles size={14}/> YOUR KNOWLEDGE, IN CONTEXT</div><h2>Turn documents into<br/><span>confident answers.</span></h2><p>Ask questions across your private knowledge base. Answers include references to the source material.</p><Link className="button button-secondary" to="/assistant">Open AI assistant <ArrowRight size={16}/></Link></div><div className="welcome-art" aria-hidden="true"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="art-core"><Bot size={34}/></div><div className="art-chip chip-one"><FileStack size={15}/></div><div className="art-chip chip-two"><MessageSquareText size={15}/></div><div className="art-chip chip-three"><Sparkles size={15}/></div></div></section>
    <section className="stat-grid" aria-label="Workspace statistics">
      <Stat icon={FileStack} label="Documents" value={loading ? "—" : docs.length.toString()} note="Indexed in your workspace" color="blue"/>
      <Stat icon={Boxes} label="Knowledge chunks" value={loading ? "—" : chunks.toLocaleString()} note="Searchable passages" color="violet"/>
      <Stat icon={MessageSquareText} label="Conversations" value={loading ? "—" : conversations.length.toString()} note="Saved to your account" color="green"/>
      <Stat icon={ArrowDownRight} label="API status" value={loading ? "Checking" : ready ? "Ready" : "Unavailable"} note="Database readiness check" color={ready ? "green" : "amber"}/>
    </section>
    <section className="dashboard-bottom">
      <div className="panel recent-panel"><div className="panel-heading"><div><div className="eyebrow">YOUR KNOWLEDGE</div><h3>Recently added</h3></div><Link className="text-link" to="/documents">View all <ArrowRight size={15}/></Link></div>
        {loading ? <LoadingBlock label="Loading documents"/> : docs.length ? <div className="recent-list">{[...docs].sort((a,b)=>b.ingested_at.localeCompare(a.ingested_at)).slice(0,5).map(doc=><div key={doc.document_id} className="recent-row"><div className="file-tile">{doc.filename.toLowerCase().endsWith(".pdf")?"PDF":"TXT"}</div><div className="recent-copy"><strong title={doc.filename}>{doc.filename}</strong><span>{doc.chunk_count} chunks · {formatRelative(doc.ingested_at)}</span></div><span className="status-dot-label"><i/> Ready</span></div>)}</div> : <EmptyState icon={FileStack} title="Your knowledge base is ready" description="Add a PDF or text file to make it searchable." action={<Link className="button button-secondary" to="/documents">Upload a document <ArrowRight size={15}/></Link>}/>}</div>
      <div className="panel quick-panel"><div className="eyebrow">QUICK ACCESS</div><h3>Continue your work</h3><p>Pick up a thread or start a fresh question against your documents.</p>
        {conversations.slice(0,3).map(c=><Link key={c.conversation_id} to={`/assistant?conversation=${c.conversation_id}`} className="quick-conversation"><span className="quick-icon"><MessageSquareText size={16}/></span><span><b>{c.title}</b><small>{formatDate(c.updated_at)}</small></span><ArrowRight size={15}/></Link>)}
        <Link to="/assistant" className="quick-new"><span className="quick-icon"><Plus size={16}/></span><span><b>Start a new conversation</b><small>Ask a question about your knowledge base</small></span><ArrowRight size={15}/></Link>
      </div>
    </section>
  </>;
}

function Stat({ icon: Icon, label, value, note, color }: {icon: typeof FileStack; label:string; value:string; note:string; color:string}) {
  return <div className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon stat-${color}`}><Icon size={17}/></span></div><div className="stat-value">{value}</div><div className="stat-note">{note}</div></div>;
}
