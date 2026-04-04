from fastapi import APIRouter

router = APIRouter()

@router.get("/privacy")
def privacy():
    return {"message": "Privacy Policy coming soon"}

@router.get("/terms")
def terms():
    return {"message": "Terms of Service coming soon"}
