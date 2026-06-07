# External Libraries

Add external folder paths and the system will scan images in those folders. Images in external folders will not be moved or modified; generated thumbnails will be stored in the main directory.

Check the `docker-compose.yml` file to confirm the mount path of the photos folder.

```yml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos/
```

The part before the colon is the folder path on your computer; the part after the colon is the path inside the container. The directory to add as an external library is the path after the colon, i.e. `/app/Photos/`.

You can also mount multiple folders by adding multiple mount paths in the `volumes` section. After modifying, restart the Docker container for the changes to take effect.

```yml
      - D:\TrailSnap\photos1:/app/Photos1/
      - E:\TrailSnap\photos2:/app/Photos2/
```

You can also add a subfolder of an external folder. For example, if you only want to add images from `D:\TrailSnap\photos1\2025\`, the external library path would be `/app/Photos1/2025/`.
