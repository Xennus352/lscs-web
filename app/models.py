"""SQLAlchemy ORM models mapped to existing LBVD MySQL tables.

Keep the physical MySQL column/table names exact (including case) because
this project may run on a case-sensitive MySQL/MariaDB host.
"""
from sqlalchemy import CheckConstraint, Column, Integer, String
from app.database import Base


class PersonCV(Base):
    __tablename__ = "personcv"
    __table_args__ = (CheckConstraint("status IN (0, 1)", name="ck_personcv_status"),)

    status = Column(Integer, nullable=False, default=0, server_default="0")
    formID = Column(String(50), primary_key=True, index=True)
    stateID = Column(String(100), nullable=False)
    districtID = Column(String(100), nullable=False)
    townshipID = Column(String(100), nullable=False)
    QVID = Column("QVID", String(100), nullable=False)
    WardName = Column(String(100), nullable=False)
    householdNo = Column(String(200), nullable=False)
    interviewDate = Column(String(100), nullable=False)
    name = Column(String(150), nullable=False)
    gender = Column(String(100), nullable=False)
    eduStatus = Column(String(100), nullable=False)
    phoneNo = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    headName = Column(String(100), nullable=False)
    headEduStatus = Column(String(100), nullable=False)
    headGender = Column(String(100), nullable=False)
    headPhoneNo = Column(String(100), nullable=False)
    headAge = Column(String(100), nullable=False)
    Interviewer = Column(String(100), nullable=False)
    interviewerPhoneNo = Column(String(100), nullable=False)


class State(Base):
    __tablename__ = "state"

    stateID = Column(String(100), primary_key=True, index=True)
    stateName = Column(String(100), nullable=False)


class District(Base):
    __tablename__ = "district"

    districtID = Column(String(100), primary_key=True, index=True)
    districtName = Column(String(100), nullable=False)
    stateID = Column(String(100), nullable=False)


class Township(Base):
    __tablename__ = "township"

    townshipID = Column(String(100), primary_key=True, index=True)
    townshipName = Column(String(100), nullable=False)
    stateID = Column(String(100), nullable=False)
    districtID = Column(String(100), nullable=False)


class QV(Base):
    __tablename__ = "qv"

    QVID = Column(String(100), primary_key=True, index=True)
    QVName = Column(String(200), nullable=False)
    stateID = Column(String(100), nullable=False)
    districtID = Column(String(100), nullable=False)
    townshipID = Column(String(100), nullable=False)
