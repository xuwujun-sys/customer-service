import uvicorn

from app.config.config import settings


def main():
    uvicorn.run(
        app='app.api.app:app',
        host=settings.app_host,
        port=settings.app_port,
        reload=True
    )

if __name__ == "__main__":
    main()