from typing import Optional

from pydantic import BaseModel, ConfigDict


class ExtractedFieldCorrection(BaseModel):
    normalized_value: str


class DocumentQueryRequest(BaseModel):
    """Petición de consulta RAG documental (RF-RAG-02)."""

    question: str
    serial_number: Optional[str] = None
    document_id: Optional[int] = None
    top_k: int = 4
    use_llm: bool = True


class DocumentSourceEvidence(BaseModel):
    """Evidencia verificable recuperada de PostgreSQL para fundamentar la respuesta."""

    document_id: int
    original_filename: str
    sha256_hash: str
    source_type: Optional[str] = None
    processing_status: Optional[str] = None
    score: float = 0.0
    matched_fields: dict = {}
    snippet: str = ""


class DocumentQueryResponse(BaseModel):
    """Respuesta del endpoint de consulta RAG (RF-RAG-02 / RF-RAG-03)."""

    # `model_used` choca con el espacio de nombres protegido `model_` de Pydantic.
    model_config = ConfigDict(protected_namespaces=())

    question: str
    serial_number: Optional[str] = None
    answer: Optional[str] = None
    llm_status: str
    model_used: Optional[str] = None
    sources: list[DocumentSourceEvidence] = []
    context_chunks: list[str] = []
