from fastapi.encoders import jsonable_encoder


def success_response(message: str = "success", data=None) -> dict:
    return {
        "code": 200,
        "message": message,
        "data": jsonable_encoder(data),
    }