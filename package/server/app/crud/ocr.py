from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.ocr import OCR
from app.schemas import ocr as schemas

def get_ocr_by_photo_id(db: Session, photo_id: UUID) -> List[OCR]:
    return db.query(OCR).filter(OCR.photo_id == photo_id).all()

def delete_ocr_by_photo_id(db: Session, photo_id: UUID, *, commit: bool = True) -> int:
    result = db.query(OCR).filter(OCR.photo_id == photo_id).delete()
    if commit:
        db.commit()
    return result

def create_ocr(db: Session, ocr: schemas.OCRCreate, *, commit: bool = True) -> OCR:
    db_ocr = OCR(**ocr.model_dump())
    db.add(db_ocr)
    if commit:
        db.commit()
        db.refresh(db_ocr)
    return db_ocr
