from pydantic import BaseModel


class DistrictResponse(BaseModel):
    districtName: str
    districtID: str

    model_config = {"from_attributes": True}    # ⭐ Pydantic v2


class TownshipResponse(BaseModel):
    townshipName: str
    townshipID: str

    model_config = {"from_attributes": True}


class StateResponse(BaseModel):
    stateName: str
    stateID: str

    model_config = {"from_attributes": True}


class QVResponse(BaseModel):
    QVName: str
    QVID: str

    model_config = {"from_attributes": True}