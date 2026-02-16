import uvicorn

from radiarch import create_app


def run():
    uvicorn.run(
        "radiarch.app:create_app",
        host="0.0.0.0",
        port=8000,
        factory=True,
        reload=True,
    )


if __name__ == "__main__":
    run()
