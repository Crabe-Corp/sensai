FROM ghcr.io/open-webui/open-webui:main

COPY entrypoint.py /app/entrypoint.py

ENTRYPOINT ["bash", "-c", "python3 /app/entrypoint.py && exec bash start.sh"]
