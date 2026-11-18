import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Check, CloudUpload, FileText, FileUp, Filter, LoaderCircle, Search, Trash2, Upload, X } from "lucide-react";
import { api, ApiError, MAX_UPLOAD_BYTES } from "../services/api";
import type { DocumentSummary } from "../types/api";
import { formatDateTime } from "../lib/format";
import { Button, EmptyState, LoadingBlock, Notice, PageHeading } from "../components/ui";

interface UploadItem { id: string; file: File; progress: number; state: "uploading" | "done" | "error"; message?: string }
const sizeLabel = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function DocumentsPage() {
  const [documents,setDocuments]=useState<DocumentSummary[]>([]); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const [query,setQuery]=useState(""); const [uploads,setUploads]=useState<UploadItem[]>([]); const [dragging,setDragging]=useState(false); const [deleting,setDeleting]=useState<string | null>(null);
  const fileRef=useRef<HTMLInputElement>(null);
  const refresh=useCallback(async()=>{try{const result=await api.listDocuments();setDocuments(result.documents);setError("");}catch(e){setError(e instanceof Error?e.message:"Unable to load documents.");}finally{setLoading(false);}},[]);
  useEffect(()=>{void refresh();},[refresh]);
  const filtered=useMemo(()=>documents.filter(d=>d.filename.toLowerCase().includes(query.trim().toLowerCase())),[documents,query]);
  const upload=useCallback(async(files: FileList | File[])=>{
    for(const file of Array.from(files)){
      const id=crypto.randomUUID();
      if(!/\.(pdf|txt)$/i.test(file.name)){setUploads(current=>[{id,file,progress:0,state:"error",message:"Only PDF and TXT files are supported."},...current]);continue;}
      if(file.size===0){setUploads(current=>[{id,file,progress:0,state:"error",message:"This file is empty."},...current]);continue;}
      if(file.size>MAX_UPLOAD_BYTES){setUploads(current=>[{id,file,progress:0,state:"error",message:`File exceeds the ${sizeLabel(MAX_UPLOAD_BYTES)} upload limit.`},...current]);continue;}
      setUploads(current=>[{id,file,progress:0,state:"uploading"},...current]);
      try{await api.uploadDocument(file,p=>setUploads(current=>current.map(item=>item.id===id?{...item,progress:p}:item)));setUploads(current=>current.map(item=>item.id===id?{...item,state:"done",progress:100}:item));await refresh();}
      catch(e){setUploads(current=>current.map(item=>item.id===id?{...item,state:"error",message:e instanceof Error?e.message:"Upload failed."}:item));}
    }
  },[refresh]);
  function drop(event:DragEvent){event.preventDefault();setDragging(false);if(event.dataTransfer.files.length)void upload(event.dataTransfer.files);}
  async function remove(doc:DocumentSummary){if(!window.confirm(`Delete “${doc.filename}” and its indexed content? This cannot be undone.`))return;setDeleting(doc.document_id);setError("");try{await api.deleteDocument(doc.document_id);setDocuments(items=>items.filter(item=>item.document_id!==doc.document_id));}catch(e){setError(e instanceof ApiError&&e.status===404?"This document is no longer available.":e instanceof Error?e.message:"Could not delete document.");}finally{setDeleting(null);}}
  const dismissUpload=(id:string)=>setUploads(items=>items.filter(item=>item.id!==id));
  return <>
    <PageHeading eyebrow="KNOWLEDGE MANAGEMENT" title="Your knowledge base" description="Manage the documents your assistant can search and cite." action={<Button onClick={()=>fileRef.current?.click()}><Upload size={16}/> Upload files</Button>} />
    <input ref={fileRef} className="sr-only" type="file" accept=".pdf,.txt,application/pdf,text/plain" multiple onChange={e=>{if(e.target.files)void upload(e.target.files);e.target.value="";}} aria-label="Choose PDF or text files" />
    {error&&<Notice tone="error">{error}</Notice>}
    <section className={`upload-zone ${dragging?"upload-zone-active":""}`} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={drop}>
      <div className="upload-art"><CloudUpload size={23}/></div><div className="upload-main"><h3>Drop documents here to add knowledge</h3><p>Upload PDF or UTF-8 text files. Your files are processed and indexed for retrieval.</p></div><Button variant="secondary" onClick={()=>fileRef.current?.click()}><FileUp size={16}/> Browse files</Button>
      <div className="upload-foot"><span><Check size={13}/> Private to your account</span><span>PDF, TXT</span><span>Up to {sizeLabel(MAX_UPLOAD_BYTES)}</span></div>
    </section>
    {uploads.length>0&&<section className="upload-queue"><div className="section-title-row"><h2>Recent uploads</h2><button className="quiet-button" onClick={()=>setUploads([])}>Clear list</button></div>{uploads.slice(0,5).map(item=><div className="upload-row" key={item.id}><div className="file-tile">{item.file.name.toLowerCase().endsWith(".pdf")?"PDF":"TXT"}</div><div className="upload-copy"><b>{item.file.name}</b><small>{item.state==="uploading"?`${item.progress}% · ${sizeLabel(item.file.size)}`:item.state==="done"?`Added · ${sizeLabel(item.file.size)}`:item.message}</small>{item.state==="uploading"&&<div className="progress-track"><span style={{width:`${item.progress}%`}}/></div>}</div><span className={`upload-result upload-result-${item.state}`}>{item.state==="uploading"?<LoaderCircle className="spin" size={17}/>:item.state==="done"?<Check size={17}/>:<X size={17}/>}</span><button className="icon-button tiny" onClick={()=>dismissUpload(item.id)} aria-label={`Dismiss ${item.file.name}`}><X size={15}/></button></div>)}</section>}
    <section className="panel document-panel"><div className="panel-heading document-heading"><div><div className="eyebrow">INDEXED CONTENT</div><h3>Documents <span className="count-pill">{loading?"…":documents.length}</span></h3></div><div className="search-box"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Filter by filename" aria-label="Filter documents by filename"/><Filter size={14} className="search-trailing"/></div></div>
      {loading?<LoadingBlock label="Loading documents"/>:filtered.length? <div className="document-table-wrap"><table className="document-table"><thead><tr><th>DOCUMENT</th><th>INDEXED</th><th>CHUNKS</th><th>STATUS</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map(doc=><tr key={doc.document_id}><td><div className="table-file"><div className="file-tile">{doc.filename.toLowerCase().endsWith(".pdf")?"PDF":"TXT"}</div><div><b title={doc.filename}>{doc.filename}</b><small>{doc.document_id.slice(0,8)}…</small></div></div></td><td className="muted-cell">{formatDateTime(doc.ingested_at)}</td><td>{doc.chunk_count.toLocaleString()}</td><td><span className="table-status"><i/> Indexed</span></td><td><button className="icon-button delete-button" onClick={()=>void remove(doc)} disabled={deleting===doc.document_id} aria-label={`Delete ${doc.filename}`}>{deleting===doc.document_id?<LoaderCircle size={17} className="spin"/>:<Trash2 size={17}/>}</button></td></tr>)}</tbody></table></div>:<EmptyState icon={FileText} title={query?"No matching documents":"No documents yet"} description={query?"Try another filename or clear the filter.":"Upload a PDF or text document to build your searchable knowledge base."} action={query?undefined:<Button variant="secondary" onClick={()=>fileRef.current?.click()}><Upload size={15}/> Upload first document</Button>}/>}
      {!loading&&documents.length>0&&<div className="table-footer">Showing {filtered.length} of {documents.length} documents <span>Search runs locally in this list</span></div>}
    </section>
  </>;
}
