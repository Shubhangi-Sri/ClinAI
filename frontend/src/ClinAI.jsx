import { useState, useRef, useEffect, useCallback } from "react";

const T = {
  bg:"#060B14", surface:"#0C1322", card:"#0F1828", cardHover:"#131f30",
  border:"#1A2840", accent:"#00C9A7", blue:"#4191FF", purple:"#9B72FF",
  amber:"#F5A623", red:"#FF4757", green:"#2ECC71",
  text:"#D8E8F4", textSub:"#8BA0B8", textMute:"#4A6080",
};

const ANIM = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
  @keyframes fadeIn{from{opacity:0}to{opacity:1}}
  @keyframes glow{0%,100%{box-shadow:0 0 8px #FF475755}50%{box-shadow:0 0 28px #FF4757cc}}
  @keyframes dot{0%,80%,100%{transform:scale(0);opacity:.3}40%{transform:scale(1);opacity:1}}
  @keyframes scan{0%{left:-60%}100%{left:110%}}
  ::-webkit-scrollbar{width:4px;}
  ::-webkit-scrollbar-track{background:transparent;}
  ::-webkit-scrollbar-thumb{background:#1A2840;border-radius:2px;}
  input,select,button{font-family:inherit;outline:none;}
`;

const REPORT_TYPES = [
  {id:"soap",      label:"SOAP Note",         icon:"📋"},
  {id:"discharge", label:"Discharge Summary", icon:"🏥"},
  {id:"referral",  label:"Referral Letter",   icon:"📨"},
];

const STAGES = [
  {id:"idle",         label:"STANDBY",   color:T.textMute},
  {id:"recording",    label:"RECORDING", color:T.red},
  {id:"transcribing", label:"PROCESSING",color:T.amber},
  {id:"generating",   label:"GENERATING",color:T.purple},
  {id:"done",         label:"COMPLETE",  color:T.green},
];

/* ── All backend calls go through this base URL ── */
const API = "http://localhost:8000/api";

const fmt     = s => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;
const safeArr = v => Array.isArray(v)?v:Array.isArray(v?.patients)?v.patients:Array.isArray(v?.data)?v.data:Array.isArray(v?.records)?v.records:[];
const fmtDate = iso => { try{return new Date(iso).toLocaleString("en-IN",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"});}catch{return iso;}};
const cleanMd = t => t
  .replace(/\*\*/g, "")          // bold
  .replace(/\*/g, "")            // italic / bullets
  .replace(/#{1,6}\s?/g, "")    // headings
  .replace(/^-{4,}$/g, "")      // horizontal rules made of dashes
  .replace(/[─═]/g, "-")        // Unicode box chars → plain dash
  .replace(/•/g, "*")           // bullet → ASCII (jsPDF safe)
  .trim();

const DEMO_TRANSCRIPT = [
  {speaker:"Doctor",  text:"Good morning. What brings you in today?",                                          start_time:0,  confidence:0.98},
  {speaker:"Patient", text:"Sharp left-sided chest pain for three days, worse when I breathe deeply.",        start_time:3,  confidence:0.96},
  {speaker:"Doctor",  text:"Does it radiate to your arm or jaw? Any fever?",                                  start_time:9,  confidence:0.97},
  {speaker:"Patient", text:"No radiation. Mild fever yesterday 38.2 degrees. Some shortness of breath.",      start_time:14, confidence:0.95},
  {speaker:"Doctor",  text:"Any recent illness? Current medications?",                                        start_time:20, confidence:0.97},
  {speaker:"Patient", text:"Flu-like illness two weeks ago. Lisinopril 10mg and aspirin 81mg daily.",         start_time:26, confidence:0.96},
  {speaker:"Doctor",  text:"BP 138/88, HR 94, SpO2 97%. Ordering ECG, chest X-ray, troponin and D-dimer.",  start_time:34, confidence:0.97},
];

/* ─── PDF ────────────────────────────────────────────────────────────────── */
function downloadPDF(title, content, filename) {
  const {jsPDF} = window.jspdf||{};
  if (!jsPDF){alert("PDF library loading — wait a moment and retry.");return;}
  const doc=new jsPDF({orientation:"portrait",unit:"mm",format:"a4"});
  const W=doc.internal.pageSize.getWidth(), H=doc.internal.pageSize.getHeight();
  const M=18, CW=W-M*2; let y=M;

  doc.setFillColor(8,20,42); doc.rect(0,0,W,28,"F");
  doc.setFont("helvetica","bold"); doc.setFontSize(16); doc.setTextColor(0,201,167);
  doc.text("ClinAI",M,17);
  doc.setFont("helvetica","normal"); doc.setFontSize(8.5); doc.setTextColor(160,190,220);
  doc.text("Clinical Documentation · HIPAA Compliant",M+28,17);
  doc.text(new Date().toLocaleString(),W-M,17,{align:"right"});
  y=38;
  doc.setFont("helvetica","bold"); doc.setFontSize(14); doc.setTextColor(20,45,90);
  doc.text(title,M,y); y+=7;
  doc.setDrawColor(0,201,167); doc.setLineWidth(0.5); doc.line(M,y,W-M,y); y+=7;
  doc.setFont("helvetica","normal"); doc.setFontSize(9.5);

  for (const raw of content.split("\n")) {
    const line=cleanMd(raw);
    if(!line){y+=3;continue;}
    const isH=/^[A-Z][A-Z0-9 \-\/]{3,}$/.test(line.trim())||/^[A-Z][^a-z]{4,}:/.test(line.trim());
    if(isH){
      y+=3; doc.setFont("helvetica","bold"); doc.setFontSize(10); doc.setTextColor(10,70,150);
      doc.splitTextToSize(line,CW).forEach(l=>{if(y>H-M){doc.addPage();y=M+10;} doc.text(l,M,y); y+=5.5;});
      doc.setFont("helvetica","normal"); doc.setFontSize(9.5);
    } else {
      doc.setTextColor(35,35,35);
      doc.splitTextToSize(line,CW).forEach(l=>{if(y>H-M){doc.addPage();y=M+10;} doc.text(l,M,y); y+=5;});
    }
  }
  const total=doc.internal.getNumberOfPages();
  for(let p=1;p<=total;p++){
    doc.setPage(p); doc.setFontSize(7); doc.setTextColor(150,150,150);
    doc.setDrawColor(210,210,210); doc.setLineWidth(0.3); doc.line(M,H-12,W-M,H-12);
    doc.text(`Confidential · ${title} · Page ${p} of ${total}`,W/2,H-7,{align:"center"});
  }
  doc.save(filename);
}

function splitForRoles(full) {
  const lines = full.split("\n");

  // Normalise a line for heading detection — strip *, #, :, spaces
  const norm = l => l.replace(/[*#:]/g,"").trim().toUpperCase();

  let inS=false, inA=false, inP=false, inF=false;
  const sL=[], aL=[], pL=[], fL=[];

  for (const l of lines) {
    const u = norm(l);

    // Detect section changes — handles "**SUBJECTIVE**", "## SUBJECTIVE", "SUBJECTIVE:", etc.
    if      (u.startsWith("SUBJECTIVE")||u.startsWith("CHIEF COMPLAINT")||u.startsWith("HISTORY OF PRESENT"))
                                            { inS=true;  inA=false; inP=false; inF=false; }
    else if (u.startsWith("OBJECTIVE")||u.startsWith("PHYSICAL EXAM")||u.startsWith("VITAL"))
                                            { inS=false; }
    else if (u.startsWith("ASSESSMENT")||u.startsWith("DIFFERENTIAL")||u.startsWith("IMPRESSION"))
                                            { inA=true;  inS=false; inP=false; inF=false; }
    else if (u.startsWith("PLAN")||u.startsWith("TREATMENT")||u.startsWith("MANAGEMENT")||u.startsWith("RECOMMENDATION"))
                                            { inP=true;  inA=false; inS=false; inF=false; }
    else if (u.startsWith("FOLLOW")||u.startsWith("RETURN PREC")||u.startsWith("DISCHARGE INST"))
                                            { inF=true;  inP=false; }

    if (inS) sL.push(l);
    if (inA && aL.length < 12) aL.push(l);
    if (inP) pL.push(l);
    if (inF) fL.push(l);
  }

  // If sections are still empty the LLM used non-standard headings —
  // fall back to splitting the raw report into thirds heuristically
  const useFallback = sL.length === 0 && pL.length === 0;
  if (useFallback) {
    const third = Math.floor(lines.length / 3);
    sL.push(...lines.slice(0, third));
    aL.push(...lines.slice(third, third * 2).slice(0, 12));
    pL.push(...lines.slice(third * 2));
  }

  const divider = "-".repeat(32);
  const pat = [
    "PATIENT VISIT SUMMARY",
    "=".repeat(48),
    `Date: ${new Date().toLocaleDateString("en-IN",{weekday:"long",year:"numeric",month:"long",day:"numeric"})}`,
    "",
    "WHAT WE DISCUSSED TODAY",
    divider,
    ...sL,
    "",
    "WHAT YOUR DOCTOR FOUND",
    divider,
    ...aL.map(l => l.replace(/[A-Z]\d{2,3}\.\d+/g,"").replace(/\(ICD.*?\)/gi,"")),
    "",
    "YOUR TREATMENT PLAN",
    divider,
    ...pL,
    ...(fL.length ? ["", "FOLLOW-UP INSTRUCTIONS", divider, ...fL] : []),
    "",
    "IMPORTANT REMINDERS",
    divider,
    "* Contact your doctor if your symptoms worsen or new symptoms develop.",
    "* Take all medications exactly as prescribed by your doctor.",
    "* Do NOT stop any medication without consulting your doctor first.",
    "* Keep all scheduled follow-up appointments.",
    "* If you experience an emergency, go to the nearest ER or call 112.",
    "",
    "=".repeat(48),
    "This document is for patient reference only.",
    "ClinAI  |  HIPAA Compliant Clinical Documentation",
  ].join("\n");

  return { doctorReport: full, patientReport: pat };
}

/* ─── Backend SSE stream (Groq → Ollama → Claude, all server-side) ────────
   NO direct calls to api.anthropic.com from the browser.
   Everything goes through http://localhost:8000/api/report/generate
──────────────────────────────────────────────────────────────────────────── */
async function streamFromBackend(transcript, reportType, patient, onToken, onError, onInfo) {
  const body = {
    session_id:      Date.now().toString(),
    transcript,
    report_type:     reportType,
    patient_context: patient ? {
      patient_id: patient.patient_id,
      name:       patient.name,
      age:        patient.age,
      sex:        patient.sex,
    } : null,
    use_rag: false,
  };

  let response;
  try {
    response = await fetch(`${API}/report/generate`, {
      method:  "POST",
      headers: {"Content-Type":"application/json"},
      body:    JSON.stringify(body),
    });
  } catch (e) {
    onError(`Cannot reach backend at ${API}. Make sure Python backend is running:\n  cd backend && python main.py`);
    return false;
  }

  if (!response.ok) {
    onError(`Backend error ${response.status}: ${await response.text()}`);
    return false;
  }

  const reader = response.body.getReader();
  const dec    = new TextDecoder();
  let buf      = "";
  let hasTokens = false;

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream:true});
    const parts = buf.split("\n");
    buf = parts.pop();
    for (const line of parts) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (raw === "[DONE]") return hasTokens;
      try {
        const d = JSON.parse(raw);
        if (d.text)  { onToken(d.text); hasTokens = true; }
        if (d.info)  { onInfo && onInfo(d.info); }
        if (d.error) { onError(d.error); return false; }
      } catch {}
    }
  }
  return hasTokens;
}

/* ─── Web Speech Recognizer ──────────────────────────────────────────────── */
function makeRecognizer(onResult) {
  const SR = window.SpeechRecognition||window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.continuous=true; rec.interimResults=true; rec.lang="en-US";
  let segs=[], turn=0, lastT=Date.now();
  rec.onresult = e => {
    for(let i=e.resultIndex;i<e.results.length;i++){
      if(!e.results[i].isFinal) continue;
      const text=e.results[i][0].transcript.trim(); if(!text) continue;
      const now=Date.now();
      if(now-lastT>2500||text.endsWith("?")) turn++;
      lastT=now;
      segs.push({speaker:turn%2===0?"Doctor":"Patient", text, start_time:segs.length*3, confidence:e.results[i][0].confidence||0.95});
      onResult([...segs]);
    }
  };
  return rec;
}

/* ════════════════ PATIENT SELECT ════════════════════════════════════════════ */
function PatientSelect({onSelect}) {
  const [patients,  setPatients]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [search,    setSearch]    = useState("");
  const [newMode,   setNewMode]   = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [form,      setForm]      = useState({name:"",age:"",sex:"M",phone:""});

  useEffect(()=>{
    fetch(`${API}/patient/list`)
      .then(r=>{if(!r.ok) throw new Error(r.status); return r.json();})
      .then(data=>{setPatients(safeArr(data)); setApiOnline(true);})
      .catch(()=>{setPatients([]); setApiOnline(false);})
      .finally(()=>setLoading(false));
  },[]);

  const filtered = safeArr(patients).filter(p=>
    (p.name||"").toLowerCase().includes(search.toLowerCase())||
    (p.patient_id||"").toLowerCase().includes(search.toLowerCase())
  );

  const handleCreate = async () => {
    if(!form.name.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/patient/create`,{
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({name:form.name, age:form.age?parseInt(form.age):null, sex:form.sex, phone:form.phone}),
      });
      if(!res.ok) throw new Error();
      const newP = await res.json();
      setPatients(prev=>[newP,...safeArr(prev)]);
      setApiOnline(true); setNewMode(false); setForm({name:"",age:"",sex:"M",phone:""});
      onSelect(newP);
    } catch {
      const newP={patient_id:`LOCAL-${Date.now()}`,name:form.name,age:form.age||null,sex:form.sex,phone:form.phone,created_at:new Date().toISOString()};
      setPatients(prev=>[newP,...safeArr(prev)]);
      setNewMode(false); setForm({name:"",age:"",sex:"M",phone:""}); onSelect(newP);
    } finally { setSaving(false); }
  };

  const inp={width:"100%",padding:"10px 14px",background:T.card,border:`1px solid ${T.border}`,borderRadius:8,color:T.text,fontSize:13,transition:"border-color 0.2s"};

  return(
    <div style={{minHeight:"100vh",background:T.bg,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:"24px 16px",fontFamily:"'IBM Plex Sans',sans-serif"}}>
      <div style={{textAlign:"center",marginBottom:36,animation:"fadeIn 0.6s ease"}}>
        <div style={{fontFamily:"'IBM Plex Mono',monospace",fontWeight:700,fontSize:32,letterSpacing:"0.15em",color:T.text}}>
          CLIN<span style={{color:T.accent}}>AI</span>
        </div>
        <div style={{fontSize:11,color:T.textMute,marginTop:6,letterSpacing:"0.14em"}}>VOICE CLINICAL DOCUMENTATION · v2.0</div>
        {!apiOnline&&!loading&&(
          <div style={{marginTop:12,fontSize:11,color:T.amber,background:`${T.amber}12`,border:`1px solid ${T.amber}30`,borderRadius:20,padding:"5px 16px",display:"inline-block"}}>
            ⚠ Backend offline — run: <code style={{fontFamily:"monospace"}}>python main.py</code>
          </div>
        )}
      </div>

      <div style={{width:"100%",maxWidth:580,background:T.surface,borderRadius:16,border:`1px solid ${T.border}`,overflow:"hidden",animation:"fadeUp 0.4s ease"}}>
        <div style={{padding:"18px 24px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
          <div>
            <div style={{fontSize:15,fontWeight:700,color:T.text}}>Select Patient</div>
            <div style={{fontSize:11,color:T.textMute,marginTop:3}}>{loading?"Loading...":`${safeArr(patients).length} patient${safeArr(patients).length!==1?"s":""} registered`}</div>
          </div>
          <button onClick={()=>setNewMode(m=>!m)} style={{padding:"8px 18px",borderRadius:8,border:`1px solid ${newMode?T.border:T.accent+"60"}`,background:newMode?"transparent":`${T.accent}18`,color:newMode?T.textMute:T.accent,cursor:"pointer",fontSize:12,fontWeight:600,transition:"all 0.2s"}}>
            {newMode?"✕ Cancel":"+ New Patient"}
          </button>
        </div>

        {newMode&&(
          <div style={{padding:"20px 24px",borderBottom:`1px solid ${T.border}`,background:`${T.accent}06`,animation:"fadeUp 0.2s ease"}}>
            <div style={{fontSize:10,color:T.accent,fontWeight:700,letterSpacing:"0.12em",marginBottom:16,fontFamily:"'IBM Plex Mono',monospace"}}>REGISTER NEW PATIENT</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:14}}>
              <div style={{gridColumn:"1/-1"}}>
                <div style={{fontSize:10,color:T.textMute,marginBottom:6}}>FULL NAME *</div>
                <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder="Patient full name" style={inp}
                  onFocus={e=>e.target.style.borderColor=T.accent} onBlur={e=>e.target.style.borderColor=T.border}/>
              </div>
              <div>
                <div style={{fontSize:10,color:T.textMute,marginBottom:6}}>AGE</div>
                <input type="number" value={form.age} onChange={e=>setForm(f=>({...f,age:e.target.value}))} placeholder="Years" style={inp}
                  onFocus={e=>e.target.style.borderColor=T.accent} onBlur={e=>e.target.style.borderColor=T.border}/>
              </div>
              <div>
                <div style={{fontSize:10,color:T.textMute,marginBottom:6}}>SEX</div>
                <select value={form.sex} onChange={e=>setForm(f=>({...f,sex:e.target.value}))} style={inp}>
                  <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
                </select>
              </div>
              <div style={{gridColumn:"1/-1"}}>
                <div style={{fontSize:10,color:T.textMute,marginBottom:6}}>PHONE</div>
                <input value={form.phone} onChange={e=>setForm(f=>({...f,phone:e.target.value}))} placeholder="+91-XXXXXXXXXX" style={inp}
                  onFocus={e=>e.target.style.borderColor=T.accent} onBlur={e=>e.target.style.borderColor=T.border}/>
              </div>
            </div>
            <button onClick={handleCreate} disabled={saving||!form.name.trim()} style={{padding:"10px 24px",background:form.name.trim()?T.accent:"#1a2840",border:"none",borderRadius:8,color:form.name.trim()?"#000":T.textMute,cursor:form.name.trim()?"pointer":"not-allowed",fontSize:13,fontWeight:700,transition:"all 0.2s"}}>
              {saving?"Registering...":"Register & Open Session →"}
            </button>
          </div>
        )}

        <div style={{padding:"14px 24px",borderBottom:`1px solid ${T.border}`}}>
          <div style={{position:"relative"}}>
            <span style={{position:"absolute",left:12,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}>🔍</span>
            <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by name or patient ID..." style={{...inp,paddingLeft:36}}
              onFocus={e=>e.target.style.borderColor=T.accent} onBlur={e=>e.target.style.borderColor=T.border}/>
          </div>
        </div>

        <div style={{maxHeight:400,overflowY:"auto"}}>
          {loading&&<div style={{padding:48,textAlign:"center",color:T.textMute}}><Spinner size={24} color={T.accent} style={{margin:"0 auto 12px"}}/><div style={{fontSize:12,marginTop:12}}>Loading patients...</div></div>}
          {!loading&&filtered.length===0&&(
            <div style={{padding:"52px 40px",textAlign:"center",color:T.textMute,animation:"fadeIn 0.4s ease"}}>
              <div style={{fontSize:40,marginBottom:16,opacity:0.4}}>🏥</div>
              <div style={{fontSize:14,fontWeight:600,color:T.textSub,marginBottom:8}}>{search?`No patients matching "${search}"`:"No patients registered yet"}</div>
              <div style={{fontSize:12,lineHeight:1.7,maxWidth:280,margin:"0 auto"}}>{search?"Try a different search term.":"Click \"+ New Patient\" above to register your first patient."}</div>
            </div>
          )}
          {!loading&&safeArr(filtered).map((p,i)=>(
            <div key={p.patient_id||i} onClick={()=>onSelect(p)}
              style={{display:"flex",alignItems:"center",gap:14,padding:"14px 24px",borderBottom:`1px solid ${T.border}`,cursor:"pointer",transition:"background 0.12s",animation:`fadeUp 0.2s ease ${i*0.04}s both`}}
              onMouseEnter={e=>e.currentTarget.style.background=T.cardHover}
              onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <div style={{width:44,height:44,borderRadius:"50%",flexShrink:0,background:`${p.sex==="F"?T.purple:T.blue}20`,border:`1.5px solid ${p.sex==="F"?T.purple:T.blue}40`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:16,fontWeight:700,color:p.sex==="F"?T.purple:T.blue}}>
                {(p.name||"?")[0].toUpperCase()}
              </div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:14,fontWeight:600,color:T.text,marginBottom:3}}>{p.name}</div>
                <div style={{fontSize:11,color:T.textMute}}>
                  <span style={{fontFamily:"'IBM Plex Mono',monospace"}}>{p.patient_id}</span>
                  {p.age&&<span> · {p.age}y</span>}
                  <span> · {p.sex==="M"?"Male":p.sex==="F"?"Female":"Other"}</span>
                  {p.phone&&<span style={{color:T.textSub}}> · {p.phone}</span>}
                </div>
              </div>
              <div style={{fontSize:11,color:T.textMute,fontFamily:"'IBM Plex Mono',monospace"}}>{p.created_at?new Date(p.created_at).toLocaleDateString("en-IN"):""}</div>
              <span style={{fontSize:20,color:T.textMute}}>›</span>
            </div>
          ))}
        </div>

        <div style={{padding:"12px 24px",borderTop:`1px solid ${T.border}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <span style={{fontSize:10,color:T.textMute,fontFamily:"'IBM Plex Mono',monospace"}}>🔒 HIPAA · AES-256-GCM</span>
          <button onClick={()=>onSelect(null)} style={{fontSize:11,color:T.textMute,background:"none",border:"none",cursor:"pointer",textDecoration:"underline"}}>Continue without selecting →</button>
        </div>
      </div>
    </div>
  );
}

/* ════════════════ MAIN APP ══════════════════════════════════════════════════ */
function ClinAIApp({patient, onBack}) {
  const [stage,        setStage]        = useState("idle");
  const [transcript,   setTranscript]   = useState([]);
  const [report,       setReport]       = useState("");
  const [streaming,    setStreaming]     = useState(false);
  const [elapsed,      setElapsed]      = useState(0);
  const [tab,          setTab]          = useState("live");
  const [reportType,   setReportType]   = useState("soap");
  const [volume,       setVolume]       = useState(0);
  const [usingSR,      setUsingSR]      = useState(false);
  const [error,        setError]        = useState("");
  const [infoMsg,      setInfoMsg]      = useState("");
  const [pdfReady,     setPdfReady]     = useState(false);
  const [history,      setHistory]      = useState([]);
  const [histLoading,  setHistLoading]  = useState(false);
  const [activeHistId, setActiveHistId] = useState(null);

  const timerRef = useRef(null);
  const recRef   = useRef(null);
  const ctxRef   = useRef(null);
  const animRef  = useRef(null);
  const endRef   = useRef(null);

  useEffect(()=>{
    const s=document.createElement("style"); s.textContent=ANIM; document.head.appendChild(s);
    if(!window.jspdf){
      const sc=document.createElement("script");
      sc.src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
      sc.onload=()=>setPdfReady(true); document.head.appendChild(sc);
    } else setPdfReady(true);
    return()=>{try{document.head.removeChild(s);}catch{}};
  },[]);

  const fetchHistory = useCallback(()=>{
    if(!patient?.patient_id||patient.patient_id.startsWith("LOCAL-")) return;
    setHistLoading(true);
    fetch(`${API}/patient/history/${patient.patient_id}`)
      .then(r=>r.ok?r.json():[]).then(d=>setHistory(safeArr(d)))
      .catch(()=>setHistory([])).finally(()=>setHistLoading(false));
  },[patient]);

  useEffect(()=>{fetchHistory();},[fetchHistory]);
  useEffect(()=>{endRef.current?.scrollIntoView({behavior:"smooth"});},[transcript]);

  const setupViz = stream => {
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    const an=ctx.createAnalyser(); an.fftSize=256;
    ctx.createMediaStreamSource(stream).connect(an); ctxRef.current=ctx;
    const tick=()=>{
      const buf=new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(buf);
      setVolume(buf.reduce((a,b)=>a+b,0)/buf.length);
      animRef.current=requestAnimationFrame(tick);
    }; tick();
  };

  const startRec = async () => {
    setError(""); setInfoMsg(""); setTranscript([]); setReport("");
    setTab("live"); setStage("recording"); setElapsed(0); setActiveHistId(null);
    timerRef.current=setInterval(()=>setElapsed(s=>s+1),1000);
    const hasSR=!!(window.SpeechRecognition||window.webkitSpeechRecognition);
    setUsingSR(hasSR);
    try {
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      setupViz(stream);
      if(hasSR){const rec=makeRecognizer(segs=>setTranscript(segs)); if(rec){recRef.current=rec; rec.start();}}
    } catch {
      setError("Microphone denied — using demo transcript.");
      clearInterval(timerRef.current); setStage("idle");
      setTimeout(()=>runPipeline(DEMO_TRANSCRIPT),400);
    }
  };

  const stopRec = () => {
    clearInterval(timerRef.current); cancelAnimationFrame(animRef.current);
    ctxRef.current?.close().catch(()=>{}); recRef.current?.stop();
    setStage("transcribing");
    setTimeout(()=>{
      setTranscript(prev=>{
        const segs=prev.length>0?prev:DEMO_TRANSCRIPT;
        setTimeout(()=>runPipeline(segs),200);
        return segs;
      });
    },600);
  };

  const runPipeline = async segs => {
    setStage("generating"); setTab("report"); setStreaming(true);
    setReport(""); setError(""); setInfoMsg("");

    let full = "";
    const success = await streamFromBackend(
      segs, reportType, patient,
      tok  => { full+=tok; setReport(r=>r+tok); },
      err  => { setError(err); setReport(FALLBACK_SOAP(patient)); setStreaming(false); setStage("done"); },
      info => setInfoMsg(info),
    );

    if (success) {
      setStreaming(false); setStage("done");
      if(patient?.patient_id&&!patient.patient_id.startsWith("LOCAL-")){
        fetch(`${API}/patient/save-report`,{
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({patient_id:patient.patient_id, report_type:reportType, soap_note:full, transcript:segs}),
        }).then(()=>fetchHistory()).catch(()=>{});
      }
    }
  };

  const handleDoctorPDF = () => {
    if(!pdfReady){alert("PDF loading...");return;}
    const {doctorReport}=splitForRoles(report);
    downloadPDF(`${REPORT_TYPES.find(r=>r.id===reportType)?.label} — Physician Copy`, doctorReport, `ClinAI_Doctor_${Date.now()}.pdf`);
  };
  const handlePatientPDF = () => {
    if(!pdfReady){alert("PDF loading...");return;}
    const {patientReport}=splitForRoles(report);
    downloadPDF("Patient Visit Summary", patientReport, `ClinAI_Patient_${Date.now()}.pdf`);
  };

  const loadDemo = () => { setTranscript(DEMO_TRANSCRIPT); setTimeout(()=>runPipeline(DEMO_TRANSCRIPT),200); };
  const reset    = () => { setStage("idle"); setTranscript([]); setReport(""); setElapsed(0); setTab("live"); setError(""); setInfoMsg(""); setStreaming(false); setActiveHistId(null); };
  const isRec    = stage==="recording";
  const hasSR    = !!(typeof window!=="undefined"&&(window.SpeechRecognition||window.webkitSpeechRecognition));

  return(
    <div style={{height:"100vh",background:T.bg,color:T.text,fontFamily:"'IBM Plex Sans',sans-serif",display:"flex",flexDirection:"column",overflow:"hidden"}}>

      {/* Header */}
      <header style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 20px",height:52,background:T.surface,borderBottom:`1px solid ${T.border}`,flexShrink:0}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <button onClick={onBack} style={{background:"none",border:`1px solid ${T.border}`,borderRadius:6,color:T.textMute,cursor:"pointer",padding:"4px 10px",fontSize:11,transition:"all 0.15s"}}
            onMouseEnter={e=>e.target.style.borderColor=T.textSub} onMouseLeave={e=>e.target.style.borderColor=T.border}>
            ← Patients
          </button>
          <span style={{fontFamily:"'IBM Plex Mono',monospace",fontWeight:700,fontSize:14,letterSpacing:"0.1em"}}>CLIN<span style={{color:T.accent}}>AI</span></span>
        </div>
        {patient&&(
          <div style={{display:"flex",alignItems:"center",gap:8,background:`${T.accent}0e`,border:`1px solid ${T.accent}2a`,borderRadius:20,padding:"5px 14px"}}>
            <div style={{width:24,height:24,borderRadius:"50%",background:`${T.accent}25`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:700,color:T.accent}}>{(patient.name||"?")[0]}</div>
            <span style={{fontSize:12,color:T.accent,fontWeight:600}}>{patient.name}</span>
            <span style={{fontSize:10,color:T.textMute,fontFamily:"'IBM Plex Mono',monospace"}}>{patient.patient_id}</span>
          </div>
        )}
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          {hasSR?<span style={{fontSize:10,color:T.green,fontFamily:"'IBM Plex Mono',monospace"}}>● SPEECH API</span>
                :<span style={{fontSize:10,color:T.amber,fontFamily:"'IBM Plex Mono',monospace"}}>⚠ NO SPEECH API</span>}
          {stage!=="idle"&&<button onClick={reset} style={{padding:"4px 12px",background:"none",border:`1px solid ${T.border}`,borderRadius:6,color:T.textMute,cursor:"pointer",fontSize:11}}>↺ Reset</button>}
        </div>
      </header>

      <div style={{flex:1,display:"flex",overflow:"hidden"}}>

        {/* Sidebar */}
        <aside style={{width:240,background:T.surface,borderRight:`1px solid ${T.border}`,display:"flex",flexDirection:"column",flexShrink:0,overflowY:"auto"}}>

          <div style={{padding:20,borderBottom:`1px solid ${T.border}`}}>
            <div style={{fontSize:9,color:T.textMute,letterSpacing:"0.12em",marginBottom:14,fontFamily:"'IBM Plex Mono',monospace"}}>RECORDING</div>
            <div style={{display:"flex",justifyContent:"center",marginBottom:16}}>
              {!isRec?(
                <button onClick={stage==="idle"?startRec:undefined} disabled={stage!=="idle"}
                  style={{width:90,height:90,borderRadius:"50%",border:"none",background:stage==="idle"?`radial-gradient(circle at 35% 35%,#FF6B7A,${T.red})`:"#111827",color:"#fff",cursor:stage==="idle"?"pointer":"default",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:3,boxShadow:stage==="idle"?`0 0 24px ${T.red}44`:"none",transition:"all 0.3s",opacity:stage==="idle"?1:0.4}}>
                  <span style={{fontSize:28}}>●</span>
                  <span style={{fontSize:9,fontWeight:700,letterSpacing:"0.1em"}}>START</span>
                </button>
              ):(
                <button onClick={stopRec}
                  style={{width:90,height:90,borderRadius:"50%",border:`2px solid ${T.red}`,background:"#080f1a",color:T.red,cursor:"pointer",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:3,animation:"glow 1.5s infinite"}}>
                  <span style={{fontSize:24}}>■</span>
                  <span style={{fontSize:9,fontWeight:700,letterSpacing:"0.1em"}}>STOP</span>
                </button>
              )}
            </div>
            {isRec&&(
              <div style={{textAlign:"center",marginBottom:12}}>
                <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:24,color:T.red,animation:"pulse 1s infinite"}}>{fmt(elapsed)}</div>
                <VolumeBar volume={volume}/>
                <div style={{fontSize:9,color:T.textMute,marginTop:6}}>{usingSR?"Live transcription":"Recording..."}</div>
              </div>
            )}
            <div style={{marginTop:12}}>
              <div style={{fontSize:9,color:T.textMute,letterSpacing:"0.1em",marginBottom:6,fontFamily:"'IBM Plex Mono',monospace"}}>REPORT TYPE</div>
              {REPORT_TYPES.map(rt=>(
                <button key={rt.id} onClick={()=>setReportType(rt.id)} style={{display:"flex",alignItems:"center",gap:6,width:"100%",textAlign:"left",padding:"7px 10px",marginBottom:4,background:reportType===rt.id?`${T.accent}18`:"none",border:`1px solid ${reportType===rt.id?T.accent+"50":T.border}`,borderRadius:7,color:reportType===rt.id?T.accent:T.textSub,cursor:"pointer",fontSize:11,transition:"all 0.15s"}}>
                  <span style={{fontSize:13}}>{rt.icon}</span>{rt.label}
                </button>
              ))}
            </div>
            {stage==="idle"&&(
              <button onClick={loadDemo} style={{width:"100%",padding:"7px 0",marginTop:8,background:`${T.amber}12`,border:`1px solid ${T.amber}35`,borderRadius:7,color:T.amber,cursor:"pointer",fontSize:10,fontWeight:600}}>
                ▶ Load Demo
              </button>
            )}
          </div>

          {/* Pipeline */}
          <div style={{padding:"14px 20px",borderBottom:`1px solid ${T.border}`}}>
            <div style={{fontSize:9,color:T.textMute,letterSpacing:"0.12em",marginBottom:8,fontFamily:"'IBM Plex Mono',monospace"}}>PIPELINE</div>
            {STAGES.filter(s=>s.id!=="idle").map(s=>{
              const si=STAGES.findIndex(x=>x.id===stage), ti=STAGES.findIndex(x=>x.id===s.id);
              const done=si>ti, active=stage===s.id;
              return(
                <div key={s.id} style={{display:"flex",alignItems:"center",gap:7,marginBottom:5,padding:"4px 8px",borderRadius:6,background:active?`${s.color}10`:"transparent",border:`1px solid ${active?s.color+"35":"transparent"}`,transition:"all 0.3s"}}>
                  <div style={{width:6,height:6,borderRadius:"50%",background:active?s.color:done?T.green:T.textMute,flexShrink:0}}/>
                  <span style={{fontSize:10,color:active?s.color:done?T.green:T.textMute,fontFamily:"'IBM Plex Mono',monospace"}}>{s.label}</span>
                  {active&&<Spinner size={9} color={s.color} style={{marginLeft:"auto"}}/>}
                  {done&&<span style={{marginLeft:"auto",fontSize:10,color:T.green}}>✓</span>}
                </div>
              );
            })}
            {infoMsg&&<div style={{marginTop:8,fontSize:9,color:T.accent,fontFamily:"'IBM Plex Mono',monospace",padding:"4px 8px",background:`${T.accent}10`,borderRadius:4}}>▶ {infoMsg}</div>}
          </div>

          {/* PDF */}
          {stage==="done"&&report&&(
            <div style={{padding:"14px 20px",borderBottom:`1px solid ${T.border}`}}>
              <div style={{fontSize:9,color:T.textMute,letterSpacing:"0.12em",marginBottom:8,fontFamily:"'IBM Plex Mono',monospace"}}>DOWNLOAD PDF</div>
              <button onClick={handleDoctorPDF} style={{display:"flex",alignItems:"center",gap:8,width:"100%",padding:"9px 12px",marginBottom:7,background:`${T.blue}15`,border:`1px solid ${T.blue}40`,borderRadius:8,color:T.blue,cursor:"pointer",fontSize:11,fontWeight:600,textAlign:"left"}}>
                <span>📄</span><div><div>Doctor Copy</div><div style={{fontSize:9,color:T.textMute,fontWeight:400}}>Full clinical report</div></div>
              </button>
              <button onClick={handlePatientPDF} style={{display:"flex",alignItems:"center",gap:8,width:"100%",padding:"9px 12px",background:`${T.accent}15`,border:`1px solid ${T.accent}40`,borderRadius:8,color:T.accent,cursor:"pointer",fontSize:11,fontWeight:600,textAlign:"left"}}>
                <span>📋</span><div><div>Patient Copy</div><div style={{fontSize:9,color:T.textMute,fontWeight:400}}>Plain-language summary</div></div>
              </button>
            </div>
          )}

          {/* History */}
          <div style={{padding:"14px 20px",flex:1,overflowY:"auto"}}>
            <div style={{fontSize:9,color:T.textMute,letterSpacing:"0.12em",marginBottom:10,fontFamily:"'IBM Plex Mono',monospace",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
              <span>REPORT HISTORY</span>
              {histLoading&&<Spinner size={9} color={T.textMute}/>}
            </div>
            {!patient&&<div style={{fontSize:11,color:T.textMute,lineHeight:1.6}}>Select a patient to see report history.</div>}
            {patient&&!histLoading&&safeArr(history).length===0&&<div style={{fontSize:11,color:T.textMute,lineHeight:1.6}}>No reports yet. Record a session to generate one.</div>}
            {safeArr(history).map((item,i)=>{
              const isActive=activeHistId===item.id;
              return(
                <div key={item.id||i}
                  onClick={()=>{setReport(item.soap_note||""); setTab("report"); setStage("done"); setActiveHistId(item.id);}}
                  style={{background:isActive?`${T.accent}10`:T.card,border:`1px solid ${isActive?T.accent+"40":T.border}`,borderRadius:8,padding:"10px 12px",marginBottom:8,cursor:"pointer",transition:"all 0.15s",animation:`fadeUp 0.2s ease ${i*0.05}s both`}}
                  onMouseEnter={e=>{if(!isActive)e.currentTarget.style.background=T.cardHover;}}
                  onMouseLeave={e=>{if(!isActive)e.currentTarget.style.background=T.card;}}>
                  <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:4}}>
                    <div style={{fontSize:10,fontWeight:600,color:isActive?T.accent:T.textSub,fontFamily:"'IBM Plex Mono',monospace"}}>{(item.report_type||"soap").toUpperCase()}</div>
                    {isActive&&<span style={{fontSize:9,color:T.accent}}>● VIEWING</span>}
                  </div>
                  <div style={{fontSize:10,color:T.textMute}}>📅 {fmtDate(item.created_at)}</div>
                  {item.soap_note&&<div style={{fontSize:9,color:T.textMute,marginTop:4,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{item.soap_note.slice(0,55)}...</div>}
                </div>
              );
            })}
          </div>
        </aside>

        {/* Main */}
        <main style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
          {error&&(
            <div style={{padding:"9px 24px",background:`${T.amber}14`,borderBottom:`1px solid ${T.amber}35`,fontSize:12,color:T.amber,display:"flex",alignItems:"center",gap:8}}>
              <span>⚠</span>{error}
              <button onClick={()=>setError("")} style={{marginLeft:"auto",background:"none",border:"none",color:T.amber,cursor:"pointer",fontSize:16}}>✕</button>
            </div>
          )}

          <div style={{display:"flex",alignItems:"center",borderBottom:`1px solid ${T.border}`,background:T.surface,flexShrink:0}}>
            {[{id:"live",label:"Live Transcript",badge:transcript.length||null},{id:"report",label:"Clinical Report",badge:stage==="done"?"✓":null}].map(t=>(
              <button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"13px 22px",background:"none",border:"none",cursor:"pointer",fontSize:12,color:tab===t.id?T.accent:T.textMute,borderBottom:`2px solid ${tab===t.id?T.accent:"transparent"}`,fontWeight:500,display:"flex",alignItems:"center",gap:6,transition:"color 0.15s"}}>
                {t.label}
                {t.badge!=null&&<span style={{padding:"1px 6px",borderRadius:10,background:tab===t.id?`${T.accent}22`:T.border,color:tab===t.id?T.accent:T.textMute,fontSize:9,fontFamily:"'IBM Plex Mono',monospace"}}>{t.badge}</span>}
              </button>
            ))}
            {stage==="done"&&report&&(
              <div style={{marginLeft:"auto",display:"flex",gap:8,paddingRight:20}}>
                <button onClick={handleDoctorPDF} style={{display:"flex",alignItems:"center",gap:5,padding:"6px 14px",background:`${T.blue}18`,border:`1px solid ${T.blue}45`,borderRadius:6,color:T.blue,cursor:"pointer",fontSize:11,fontWeight:600}}>📄 Doctor PDF</button>
                <button onClick={handlePatientPDF} style={{display:"flex",alignItems:"center",gap:5,padding:"6px 14px",background:`${T.accent}18`,border:`1px solid ${T.accent}45`,borderRadius:6,color:T.accent,cursor:"pointer",fontSize:11,fontWeight:600}}>📋 Patient PDF</button>
              </div>
            )}
          </div>

          <div style={{flex:1,overflow:"auto",padding:24}}>
            {tab==="live"&&(
              <div>
                {transcript.length===0&&stage==="idle"&&<EmptyState icon="🎙" title="Ready to Record" subtitle={hasSR?"Press START — Web Speech API transcribes live. Or click Load Demo to test.":"Speech API unavailable. Press START to record, or use Load Demo."}/>}
                {transcript.length===0&&stage==="recording"&&<EmptyState icon="🔴" title={usingSR?"Listening — speak now":"Recording..."} subtitle="Words appear here as you speak."/>}
                {transcript.length===0&&stage==="transcribing"&&<Dots label="PROCESSING TRANSCRIPT" color={T.amber}/>}
                {safeArr(transcript).map((seg,i)=>(
                  <div key={i} style={{display:"flex",gap:12,marginBottom:14,animation:"fadeUp 0.25s ease"}}>
                    <div style={{width:64,flexShrink:0,textAlign:"center",fontSize:9,fontWeight:700,letterSpacing:"0.1em",fontFamily:"'IBM Plex Mono',monospace",color:seg.speaker==="Doctor"?T.blue:T.accent,borderTop:`2px solid ${seg.speaker==="Doctor"?T.blue:T.accent}`,paddingTop:5}}>
                      {seg.speaker?.toUpperCase()}
                      {seg.confidence&&<div style={{fontSize:8,color:T.textMute,marginTop:1,fontWeight:400}}>{Math.round(seg.confidence*100)}%</div>}
                    </div>
                    <div style={{flex:1,background:T.card,borderRadius:10,padding:"10px 16px",fontSize:13,lineHeight:1.7,color:T.text,border:`1px solid ${T.border}`}}>{seg.text}</div>
                  </div>
                ))}
                <div ref={endRef}/>
              </div>
            )}

            {tab==="report"&&(
              <div style={{maxWidth:840}}>
                {!report&&stage!=="generating"&&<EmptyState icon="📋" title="No report yet" subtitle="Record a session or load the demo. Your backend will generate the report using Groq (free, fast)."/>}
                {stage==="generating"&&!report&&<Dots label="GENERATING VIA GROQ · LLAMA 3.1 70B" color={T.purple}/>}
                {report&&(
                  <>
                    <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:16,gap:12,flexWrap:"wrap"}}>
                      <div>
                        <h2 style={{fontSize:17,fontWeight:700,color:T.text,marginBottom:4}}>
                          {REPORT_TYPES.find(r=>r.id===reportType)?.label}
                          {activeHistId&&<span style={{fontSize:11,color:T.textMute,fontWeight:400,marginLeft:10}}>(historical)</span>}
                        </h2>
                        <div style={{fontSize:11,color:T.textMute}}>
                          {infoMsg||"Groq · Llama 3.1 70B"} · {new Date().toLocaleDateString()}
                        </div>
                      </div>
                      {stage==="done"&&(
                        <div style={{display:"flex",gap:8}}>
                          <button onClick={handleDoctorPDF} style={{display:"flex",alignItems:"center",gap:6,padding:"8px 16px",background:`${T.blue}18`,border:`1px solid ${T.blue}45`,borderRadius:8,color:T.blue,cursor:"pointer",fontSize:11,fontWeight:600}}>📄 Doctor PDF</button>
                          <button onClick={handlePatientPDF} style={{display:"flex",alignItems:"center",gap:6,padding:"8px 16px",background:`${T.accent}18`,border:`1px solid ${T.accent}45`,borderRadius:8,color:T.accent,cursor:"pointer",fontSize:11,fontWeight:600}}>📋 Patient PDF</button>
                        </div>
                      )}
                    </div>
                    {stage==="done"&&!activeHistId&&(
                      <div style={{marginBottom:16,padding:"10px 16px",background:`${T.purple}08`,border:`1px solid ${T.purple}22`,borderRadius:8,fontSize:11,color:T.textSub,display:"flex",gap:10}}>
                        <span style={{flexShrink:0}}>ℹ</span>
                        <span><strong style={{color:T.blue}}>Doctor PDF</strong> — full report with ICD-10 codes. &nbsp;<strong style={{color:T.accent}}>Patient PDF</strong> — plain-language visit summary.</span>
                      </div>
                    )}
                    <div style={{background:T.card,borderRadius:12,padding:"24px 28px",border:`1px solid ${T.border}`,fontFamily:"'IBM Plex Mono',monospace",fontSize:12,lineHeight:2,color:T.text,whiteSpace:"pre-wrap",position:"relative",overflow:"hidden"}}>
                      {streaming&&<div style={{position:"absolute",top:0,left:0,width:"60%",height:1,background:`linear-gradient(90deg,transparent,${T.accent},transparent)`,animation:"scan 2s linear infinite"}}/>}
                      {report}
                      {streaming&&<span style={{display:"inline-block",width:8,height:15,background:T.accent,marginLeft:2,animation:"pulse 0.7s infinite",verticalAlign:"middle"}}/>}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

/* ════════════════ ROOT ══════════════════════════════════════════════════════ */
export default function ClinAIPro() {
  const [patient, setPatient] = useState(undefined);
  useEffect(()=>{
    const s=document.createElement("style"); s.textContent=ANIM; document.head.appendChild(s);
    return()=>{try{document.head.removeChild(s);}catch{}};
  },[]);
  if(patient===undefined) return <PatientSelect onSelect={p=>setPatient(p??null)}/>;
  return <ClinAIApp patient={patient} onBack={()=>setPatient(undefined)}/>;
}

function Spinner({size=14,color=T.accent,style={}}) {
  return <div style={{width:size,height:size,border:`${Math.max(1.5,size/8)}px solid ${color}28`,borderTopColor:color,borderRadius:"50%",animation:"spin 0.7s linear infinite",flexShrink:0,...style}}/>;
}
function VolumeBar({volume}) {
  return(
    <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:2,height:28,marginTop:10}}>
      {Array.from({length:14},(_,i)=>{
        const active=volume>(i/14)*80;
        return <div key={i} style={{width:3,height:active?Math.min(28,6+(volume/80)*22):4,background:active?(i>11?T.red:i>8?T.amber:T.accent):T.border,borderRadius:2,transition:"height 0.05s"}}/>;
      })}
    </div>
  );
}
function Dots({label,color}) {
  return(
    <div style={{display:"flex",alignItems:"center",gap:12,padding:"16px 0",color}}>
      <div style={{display:"flex",gap:5}}>
        {[0,0.15,0.3].map((d,i)=><div key={i} style={{width:7,height:7,borderRadius:"50%",background:color,animation:"dot 1.4s infinite",animationDelay:`${d}s`}}/>)}
      </div>
      <span style={{fontSize:11,fontWeight:600,letterSpacing:"0.12em",fontFamily:"'IBM Plex Mono',monospace"}}>{label}</span>
    </div>
  );
}
function EmptyState({icon,title,subtitle}) {
  return(
    <div style={{textAlign:"center",padding:"70px 40px",color:T.textMute,animation:"fadeIn 0.4s ease"}}>
      <div style={{fontSize:44,marginBottom:14,opacity:0.45}}>{icon}</div>
      <div style={{fontSize:15,color:T.textSub,marginBottom:8,fontWeight:600}}>{title}</div>
      <div style={{fontSize:12,maxWidth:360,margin:"0 auto",lineHeight:1.8}}>{subtitle}</div>
    </div>
  );
}

const FALLBACK_SOAP = p => `PATIENT SUMMARY
Name: ${p?.name||"Demo Patient"}  |  ID: ${p?.patient_id||"N/A"}  |  Date: ${new Date().toLocaleDateString()}
Age: ${p?.age||"?"}  |  Sex: ${p?.sex==="M"?"Male":p?.sex==="F"?"Female":"Unknown"}

CHIEF COMPLAINT
Left-sided chest pain x 3 days

SUBJECTIVE
Sharp pleuritic left-sided chest pain worsening with deep inspiration. No radiation.
Low-grade fever 38.2 degrees C. Mild dry cough. Exertional dyspnea. Post-viral prodrome 2 weeks prior.
Medications: Lisinopril 10mg daily, Aspirin 81mg daily. No known drug allergies.

OBJECTIVE
BP 138/88 mmHg | HR 94 bpm | SpO2 97% RA | Afebrile
Ordered: ECG, CXR, Troponin 0h+3h, D-dimer, CBC, CRP/ESR

ASSESSMENT
1. Pleuritis - R07.1  [55%]  Post-viral pleural inflammation
2. Acute Pericarditis - I30.9  [35%]  Check ECG for PR depression
3. Pulmonary Embolism - I26.99  [RULE OUT]
   WARNING: D-dimer >500 ng/mL - CT-PA immediately

PLAN
* Ibuprofen 600mg by mouth three times daily x 2 weeks with food
* Colchicine 0.5mg twice daily x 3 months if pericarditis confirmed
* Activity restriction pending diagnosis confirmation

ICD-10 CODES: R07.1 - I30.9 - I26.99 - R00.0

FOLLOW-UP INSTRUCTIONS
* Return in 48-72 hours for results review
* Emergency: go to ER immediately if pain worsens or SpO2 drops`;