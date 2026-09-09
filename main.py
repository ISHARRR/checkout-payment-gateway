import uvicorn


def main():
    """Run the local demo in one process because payment storage is in memory."""
    uvicorn.run(
        app="payment_gateway_api.app:app",
        host="127.0.0.1",
        port=8000,
        workers=1,
    )


if __name__ == "__main__":
    main()
