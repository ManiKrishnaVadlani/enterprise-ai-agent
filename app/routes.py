from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class AskResponse(BaseModel):
    question: str
    answer: str


@router.get("/")
def read_root():
    return {
        "message": "Enterprise AI Knowledge & Workflow Agent",
        "status": "running",
    }


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "Enterprise AI Knowledge & Workflow Agent",
    }


@router.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    return {
        "question": request.question,
        "answer": (
            "Your question has been received. AI answering functionality "
            "will be added in a later stage."
        ),
    }
