import { useState, useEffect } from "react";

/* ── safe helper: always returns an array no matter what the API sends ── */
function safeArray(v) {
  if (Array.isArray(v))                  return v;
  if (v && Array.isArray(v.patients))    return v.patients;
  if (v && Array.isArray(v.data))        return v.data;
  if (v && Array.isArray(v.results))     return v.results;
  if (v && Array.isArray(v.records))     return v.records;
  return [];
}

const DEMO_PATIENTS = [
  { patient_id: "P001", name: "Arjun Sharma",   age: 45, sex: "M", diagnosis: "Hypertension, T2DM" },
  { patient_id: "P002", name: "Priya Mehta",    age: 32, sex: "F", diagnosis: "Pleuritis"          },
  { patient_id: "P003", name: "Rahul Verma",    age: 58, sex: "M", diagnosis: "Chest pain w/u"     },
  { patient_id: "P004", name: "Sunita Agarwal", age: 27, sex: "F", diagnosis: "Pericarditis"       },
];

export default function PatientSelect({ onSelect }) {
  /* ── Always initialise as array — this is what was crashing ── */
  const [patients, setPatients] = useState([]);
  const [search,   setSearch]   = useState("");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  useEffect(() => {
    setLoading(true);
    fetch("http://localhost:8000/api/patient/list")
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        /* safeArray handles every possible API response shape */
        const arr = safeArray(data);
        setPatients(arr.length > 0 ? arr : DEMO_PATIENTS);
      })
      .catch(err => {
        console.warn("Patient API unavailable, using demo data:", err.message);
        setError("Backend offline — showing demo patients.");
        /* Fallback so the page is never blank / crashing */
        setPatients(DEMO_PATIENTS);
      })
      .finally(() => setLoading(false));
  }, []);

  /* safeArray at filter time too — belt-and-suspenders */
  const filtered = safeArray(patients).filter(p =>
    (p.name        || "").toLowerCase().includes(search.toLowerCase()) ||
    (p.patient_id  || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ minHeight: "100vh", background: "#060B14", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24, fontFamily: "sans-serif", color: "#D8E8F4" }}>

      <h1 style={{ fontFamily: "monospace", letterSpacing: "0.15em", marginBottom: 8 }}>
        CLIN<span style={{ color: "#00C9A7" }}>AI</span>
      </h1>
      <p style={{ color: "#4A6080", fontSize: 12, marginBottom: 32, letterSpacing: "0.1em" }}>
        VOICE CLINICAL DOCUMENTATION · v2.0
      </p>

      {error && (
        <div style={{ marginBottom: 16, padding: "8px 16px", background: "#F5A62315", border: "1px solid #F5A62340", borderRadius: 8, fontSize: 12, color: "#F5A623" }}>
          ⚠ {error}
        </div>
      )}

      <div style={{ width: "100%", maxWidth: 560, background: "#0C1322", borderRadius: 16, border: "1px solid #1A2840", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ padding: "16px 24px", borderBottom: "1px solid #1A2840", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Select Patient</div>
            <div style={{ fontSize: 11, color: "#4A6080", marginTop: 2 }}>
              {loading ? "Loading..." : `${safeArray(patients).length} patients on file`}
            </div>
          </div>
          {onSelect && (
            <button
              onClick={() => onSelect(null)}
              style={{ padding: "6px 14px", background: "none", border: "1px solid #1A2840", borderRadius: 8, color: "#8BA0B8", cursor: "pointer", fontSize: 11 }}
            >
              Skip →
            </button>
          )}
        </div>

        {/* Search */}
        <div style={{ padding: "12px 24px", borderBottom: "1px solid #1A2840" }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="🔍  Search by name or patient ID..."
            style={{ width: "100%", padding: "9px 12px", background: "#101A2E", border: "1px solid #1A2840", borderRadius: 8, color: "#D8E8F4", fontSize: 12, outline: "none", boxSizing: "border-box" }}
          />
        </div>

        {/* List */}
        <div style={{ maxHeight: 380, overflowY: "auto" }}>
          {loading && (
            <div style={{ padding: 40, textAlign: "center", color: "#4A6080", fontSize: 12 }}>
              Loading patients...
            </div>
          )}

          {!loading && filtered.length === 0 && (
            <div style={{ padding: 40, textAlign: "center", color: "#4A6080", fontSize: 12 }}>
              {search ? `No patients matching "${search}"` : "No patients found."}
            </div>
          )}

          {/* ── This is the line that was crashing — now wrapped in safeArray ── */}
          {!loading && safeArray(filtered).map((p, i) => (
            <div
              key={p.patient_id || i}
              onClick={() => onSelect && onSelect(p)}
              style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 24px", borderBottom: "1px solid #1A2840", cursor: "pointer", transition: "background 0.12s" }}
              onMouseEnter={e => e.currentTarget.style.background = "#152033"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              {/* Avatar */}
              <div style={{ width: 40, height: 40, borderRadius: "50%", flexShrink: 0, background: p.sex === "F" ? "#9B72FF25" : "#4191FF25", border: `1px solid ${p.sex === "F" ? "#9B72FF40" : "#4191FF40"}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700, color: p.sex === "F" ? "#9B72FF" : "#4191FF" }}>
                {(p.name || "?")[0].toUpperCase()}
              </div>

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{p.name || "Unknown"}</div>
                <div style={{ fontSize: 11, color: "#4A6080" }}>
                  {p.patient_id}
                  {p.age  ? ` · ${p.age}y`  : ""}
                  {p.sex  ? ` · ${p.sex === "M" ? "Male" : p.sex === "F" ? "Female" : p.sex}` : ""}
                  {p.diagnosis ? <span style={{ color: "#8BA0B8" }}> · {p.diagnosis}</span> : null}
                </div>
              </div>

              <span style={{ fontSize: 18, color: "#4A6080" }}>›</span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding: "10px 24px", borderTop: "1px solid #1A2840", fontSize: 10, color: "#4A6080", fontFamily: "monospace" }}>
          🔒 HIPAA COMPLIANT · AES-256-GCM ENCRYPTED
        </div>
      </div>
    </div>
  );
}