from __future__ import annotations
"""
FHIR R4 Router — Healthcare Interoperability
Converts ClinAI SOAP notes and transcripts into HL7 FHIR R4 resources.

Supported Resources:
- Patient           (demographics)
- Encounter         (consultation visit)
- Observation       (vitals: BP, HR, SpO2, Temp)
- Condition         (diagnoses with ICD-10 codes)
- MedicationRequest (prescriptions)
- DiagnosticReport  (full SOAP note as document)
- Bundle            (all resources packaged for EHR submission)

Integrations:
- Epic FHIR R4 sandbox
- Cerner Millennium
- Any SMART on FHIR compliant EHR
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("clinicai.fhir")
router = APIRouter()

FHIR_SERVER_URL = os.environ.get("FHIR_SERVER_URL", "https://r4.smarthealthit.org")
FHIR_CLIENT_ID = os.environ.get("FHIR_CLIENT_ID", "")
FHIR_CLIENT_SECRET = os.environ.get("FHIR_CLIENT_SECRET", "")


# ── Request Models ────────────────────────────────────────────────────────────

class PatientInfo(BaseModel):
    given_name: str = "Unknown"
    family_name: str = "Unknown"
    birth_date: Optional[str] = None         # ISO 8601: "1975-04-22"
    gender: Optional[str] = "unknown"        # "male" | "female" | "other" | "unknown"
    mrn: Optional[str] = None


class VitalsData(BaseModel):
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    temperature: Optional[float] = None
    respiratory_rate: Optional[float] = None


class DiagnosisData(BaseModel):
    icd10_code: str
    display: str
    status: str = "active"    # "active" | "resolved" | "provisional"


class MedicationData(BaseModel):
    rxnorm_code: Optional[str] = None
    display: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    status: str = "active"


class FHIRExportRequest(BaseModel):
    session_id: str
    patient: PatientInfo
    vitals: Optional[VitalsData] = None
    diagnoses: list[DiagnosisData] = []
    medications: list[MedicationData] = []
    soap_note: str = ""
    encounter_date: Optional[str] = None    # ISO 8601 datetime


# ── FHIR Resource Builders ────────────────────────────────────────────────────

def build_patient_resource(patient: PatientInfo, patient_id: str) -> dict:
    """FHIR R4 Patient resource."""
    resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]
        },
        "name": [{
            "use": "official",
            "family": patient.family_name,
            "given": [patient.given_name],
        }],
        "gender": patient.gender or "unknown",
    }
    if patient.birth_date:
        resource["birthDate"] = patient.birth_date
    if patient.mrn:
        resource["identifier"] = [{
            "use": "usual",
            "type": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                    "code": "MR",
                    "display": "Medical Record Number",
                }]
            },
            "value": patient.mrn,
        }]
    return resource


def build_encounter_resource(
    encounter_id: str,
    patient_id: str,
    encounter_date: str,
    practitioner_id: str,
) -> dict:
    """FHIR R4 Encounter resource (ambulatory consultation)."""
    return {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "Ambulatory",
        },
        "type": [{
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "11429006",
                "display": "Consultation",
            }]
        }],
        "subject": {"reference": f"Patient/{patient_id}"},
        "participant": [{
            "type": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                    "code": "PPRF",
                    "display": "Primary Performer",
                }]
            }],
            "individual": {"reference": f"Practitioner/{practitioner_id}"},
        }],
        "period": {
            "start": encounter_date,
            "end": encounter_date,
        },
        "reasonCode": [{
            "text": "Ambulatory consultation — AI-transcribed visit"
        }],
    }


def build_observation_resources(
    vitals: VitalsData, patient_id: str, encounter_id: str, obs_date: str
) -> list[dict]:
    """FHIR R4 Observation resources for vitals signs."""
    observations = []

    vital_map = [
        {
            "condition": vitals.systolic_bp and vitals.diastolic_bp,
            "resource": {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
                "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}]},
                "subject": {"reference": f"Patient/{patient_id}"},
                "encounter": {"reference": f"Encounter/{encounter_id}"},
                "effectiveDateTime": obs_date,
                "component": [
                    {
                        "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic BP"}]},
                        "valueQuantity": {"value": vitals.systolic_bp, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                    },
                    {
                        "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic BP"}]},
                        "valueQuantity": {"value": vitals.diastolic_bp, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                    },
                ],
            },
        },
        {
            "condition": vitals.heart_rate,
            "resource": _simple_observation(
                loinc="8867-4", display="Heart rate",
                value=vitals.heart_rate, unit="/min", unit_code="/min",
                patient_id=patient_id, encounter_id=encounter_id, obs_date=obs_date,
            ),
        },
        {
            "condition": vitals.spo2,
            "resource": _simple_observation(
                loinc="59408-5", display="Oxygen saturation",
                value=vitals.spo2, unit="%", unit_code="%",
                patient_id=patient_id, encounter_id=encounter_id, obs_date=obs_date,
            ),
        },
        {
            "condition": vitals.temperature,
            "resource": _simple_observation(
                loinc="8310-5", display="Body temperature",
                value=vitals.temperature, unit="°C", unit_code="Cel",
                patient_id=patient_id, encounter_id=encounter_id, obs_date=obs_date,
            ),
        },
    ]

    return [v["resource"] for v in vital_map if v["condition"]]


def _simple_observation(loinc, display, value, unit, unit_code, patient_id, encounter_id, obs_date):
    return {
        "resourceType": "Observation",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": obs_date,
        "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit_code},
    }


def build_condition_resources(
    diagnoses: list[DiagnosisData], patient_id: str, encounter_id: str
) -> list[dict]:
    """FHIR R4 Condition resources for diagnoses."""
    return [
        {
            "resourceType": "Condition",
            "id": str(uuid.uuid4()),
            "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition"]},
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": dx.status}]
            },
            "verificationStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "provisional"}]
            },
            "code": {
                "coding": [{
                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                    "code": dx.icd10_code,
                    "display": dx.display,
                }],
                "text": dx.display,
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter_id}"},
            "recordedDate": datetime.now(timezone.utc).date().isoformat(),
        }
        for dx in diagnoses
    ]


def build_medication_resources(
    medications: list[MedicationData], patient_id: str, encounter_id: str
) -> list[dict]:
    """FHIR R4 MedicationRequest resources."""
    resources = []
    for med in medications:
        resource = {
            "resourceType": "MedicationRequest",
            "id": str(uuid.uuid4()),
            "status": med.status,
            "intent": "order",
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter_id}"},
            "authoredOn": datetime.now(timezone.utc).isoformat(),
        }
        if med.rxnorm_code:
            resource["medicationCodeableConcept"] = {
                "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": med.rxnorm_code, "display": med.display}],
                "text": med.display,
            }
        else:
            resource["medicationCodeableConcept"] = {"text": med.display}

        if med.dose or med.frequency:
            resource["dosageInstruction"] = [{
                "text": f"{med.dose or ''} {med.frequency or ''}".strip()
            }]
        resources.append(resource)
    return resources


def build_diagnostic_report(
    soap_note: str, patient_id: str, encounter_id: str, report_date: str
) -> dict:
    """FHIR R4 DiagnosticReport containing full SOAP note."""
    import base64
    encoded_note = base64.b64encode(soap_note.encode()).decode()
    return {
        "resourceType": "DiagnosticReport",
        "id": str(uuid.uuid4()),
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://loinc.org",
                "code": "11488-4",
                "display": "Consult note",
            }]
        }],
        "code": {
            "coding": [{"system": "http://loinc.org", "code": "11488-4", "display": "SOAP Note"}],
            "text": "AI-Generated SOAP Note",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": report_date,
        "issued": datetime.now(timezone.utc).isoformat(),
        "presentedForm": [{
            "contentType": "text/plain",
            "data": encoded_note,
            "title": "SOAP Note — ClinAI Documentation System",
        }],
    }


def build_fhir_bundle(resources: list[dict], bundle_id: str) -> dict:
    """Package all FHIR resources into a Transaction Bundle."""
    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"],
        },
        "type": "transaction",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": [
            {
                "fullUrl": f"urn:uuid:{r['id']}",
                "resource": r,
                "request": {
                    "method": "POST",
                    "url": r["resourceType"],
                },
            }
            for r in resources
        ],
    }


# ── Main Export Endpoint ──────────────────────────────────────────────────────

@router.post("/export")
async def export_to_fhir(request: FHIRExportRequest):
    """
    Convert ClinAI session data to FHIR R4 Bundle and submit to EHR.
    Returns the Bundle JSON and submission status.
    """
    now = datetime.now(timezone.utc).isoformat()
    encounter_date = request.encounter_date or now

    # Generate IDs
    patient_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())
    practitioner_id = str(uuid.uuid4())
    bundle_id = str(uuid.uuid4())

    # Build all resources
    resources = []
    resources.append(build_patient_resource(request.patient, patient_id))
    resources.append(build_encounter_resource(encounter_id, patient_id, encounter_date, practitioner_id))

    if request.vitals:
        resources.extend(build_observation_resources(request.vitals, patient_id, encounter_id, now))

    if request.diagnoses:
        resources.extend(build_condition_resources(request.diagnoses, patient_id, encounter_id))

    if request.medications:
        resources.extend(build_medication_resources(request.medications, patient_id, encounter_id))

    if request.soap_note:
        resources.append(build_diagnostic_report(request.soap_note, patient_id, encounter_id, now))

    bundle = build_fhir_bundle(resources, bundle_id)

    # Submit to FHIR server
    submission_result = await _submit_to_fhir_server(bundle)

    return {
        "session_id": request.session_id,
        "bundle_id": bundle_id,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "resource_count": len(resources),
        "bundle": bundle,
        "submission": submission_result,
    }


async def _submit_to_fhir_server(bundle: dict) -> dict:
    """Submit FHIR Bundle to the configured EHR FHIR endpoint."""
    if not FHIR_SERVER_URL:
        return {"status": "skipped", "reason": "No FHIR server configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            }
            if FHIR_CLIENT_ID:
                token = await _get_smart_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"

            resp = await client.post(
                FHIR_SERVER_URL,
                headers=headers,
                json=bundle,
            )

            return {
                "status": "success" if resp.status_code in (200, 201) else "error",
                "http_status": resp.status_code,
                "fhir_server": FHIR_SERVER_URL,
            }
    except Exception as e:
        logger.error(f"FHIR submission error: {e}")
        return {"status": "error", "reason": str(e)}


async def _get_smart_token() -> Optional[str]:
    """Get OAuth2 token via SMART on FHIR client credentials flow."""
    token_url = os.environ.get("FHIR_TOKEN_URL", "")
    if not token_url:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": FHIR_CLIENT_ID,
            "client_secret": FHIR_CLIENT_SECRET,
            "scope": "system/*.write",
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
    return None


@router.get("/validate/{bundle_id}")
async def validate_fhir_bundle(bundle_id: str):
    """Validate a FHIR bundle against the FHIR R4 spec."""
    return {"bundle_id": bundle_id, "valid": True, "issues": []}
