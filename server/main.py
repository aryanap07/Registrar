import os
from contextlib import asynccontextmanager
from datetime import date
from enum import Enum
from typing import Annotated, List
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field as SQLField, Relationship, Session, SQLModel, create_engine, select

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


class Gender(str, Enum):
    male = "male"
    female = "female"


class Branch(str, Enum):
    AI = "AI"
    CS = "CS"
    IT = "IT"
    EC = "EC"
    EE = "EE"
    CE = "CE"
    ME = "ME"
    MT = "MT"
    IP = "IP"


class Level(str, Enum):
    Beginner = "Beginner"
    Intermediate = "Intermediate"


class Skill(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    skill: str
    level: Level
    registration_id: int | None = SQLField(default=None, foreign_key="registration.id")
    registration: "Registration" = Relationship(back_populates="skills")


class Registration(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    first_name: str
    last_name: str
    dob: date
    gender: Gender
    email: str = SQLField(unique=True, index=True)
    phone: str = SQLField(unique=True, index=True)
    branch: Branch
    confirmation_code: str | None = SQLField(default=None, unique=True, index=True)
    skills: List[Skill] = Relationship(back_populates="registration")


class SkillIn(BaseModel):
    skill: str
    level: Level


class RegistrationIn(BaseModel):
    firstName: str = Field(min_length=1)
    lastName: str = Field(min_length=1)
    dob: date
    gender: Gender
    email: EmailStr
    phone: str
    branch: Branch
    skills: List[SkillIn] = []

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 10:
            raise ValueError("phone must be exactly 10 digits")
        return v


class SkillOut(BaseModel):
    skill: str
    level: Level


class RegistrationOut(BaseModel):
    id: int
    firstName: str
    lastName: str
    dob: date
    gender: Gender
    email: str
    phone: str
    branch: Branch
    confirmationCode: str
    skills: List[SkillOut]


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="JEC Registration API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health():
    return {"status": "ok", "service": "JEC Registration API"}


def to_out(reg: Registration) -> RegistrationOut:
    return RegistrationOut(
        id=reg.id,
        firstName=reg.first_name,
        lastName=reg.last_name,
        dob=reg.dob,
        gender=reg.gender,
        email=reg.email,
        phone=reg.phone,
        branch=reg.branch,
        confirmationCode=reg.confirmation_code,
        skills=[SkillOut(skill=s.skill, level=s.level) for s in reg.skills],
    )


@app.post("/api/register", response_model=RegistrationOut, status_code=201)
def create_registration(payload: RegistrationIn, session: SessionDep):
    duplicate = session.exec(
        select(Registration).where(
            (Registration.email == payload.email) | (Registration.phone == payload.phone)
        )
    ).first()
    if duplicate:
        raise HTTPException(409, "You have already registered")

    reg = Registration(
        first_name=payload.firstName,
        last_name=payload.lastName,
        dob=payload.dob,
        gender=payload.gender,
        email=payload.email,
        phone=payload.phone,
        branch=payload.branch,
        skills=[Skill(skill=s.skill, level=s.level) for s in payload.skills],
    )
    session.add(reg)
    try:
        session.flush()
        reg.confirmation_code = f"JEC-{reg.id:06d}"
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "You have already registered")
    session.refresh(reg)
    return to_out(reg)


BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_DIR = BASE_DIR / "client"

app.mount(
    "/",
    StaticFiles(directory=CLIENT_DIR, html=True),
    name="client",
)