from pydantic import BaseModel


class RemoteUserMessage(BaseModel):
    msg: str
    rid: str  
    user_type: str 
    phone: str
    employee_name: str 