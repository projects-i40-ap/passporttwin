from pydantic import BaseModel


class ExtractedFieldCorrection(BaseModel):
    normalized_value: str