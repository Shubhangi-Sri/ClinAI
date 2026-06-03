import React, { useState } from "react";
import ClinAIPro from "./ClinAI";
import PatientSelect from "./PatientSelect";
import RegisterPatient from "./RegisterPatient";

export default function App() {
  const [patientId, setPatientId] = useState(null);
  const path = window.location.pathname;

  if (path === "/register") return <RegisterPatient />;

  if (!patientId) {
    return <PatientSelect onSelect={(id) => setPatientId(id)} />;
  }

  return <ClinAIPro patientId={patientId} />;
}
