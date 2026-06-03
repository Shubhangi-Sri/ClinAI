import React, { useState } from "react";

export default function RegisterPatient() {
  const [form, setForm] = useState({
    patient_id: "",
    name: "",
    age: "",
    sex: ""
  });

  const submit = async () => {
    await fetch("http://localhost:8000/api/patient/create", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(form)
    });

    window.location.href = "/";
  };

  return (
    <div>
      <h2>Register Patient</h2>

      <input placeholder="ID" onChange={e=>setForm({...form, patient_id:e.target.value})}/>
      <input placeholder="Name" onChange={e=>setForm({...form, name:e.target.value})}/>
      <input placeholder="Age" onChange={e=>setForm({...form, age:parseInt(e.target.value)})}/>
      <input placeholder="Sex" onChange={e=>setForm({...form, sex:e.target.value})}/>

      <button onClick={submit}>Register</button>
    </div>
  );
}